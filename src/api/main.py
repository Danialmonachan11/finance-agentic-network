"""Demo web app for the finance agentic NETWORK (not a fixed "us vs
customers" setup — see BRAIN.md decisions log, 2026-08-24). Every company
is a seller on some invoices and a buyer on others; `/companies/{id}`
shows both sides for whichever company you're viewing. `/ops` keeps the
raw technical view for anyone who wants the underlying audit trail.

Security notes (BRAIN.md, 2026-08-25 audit): approver identity comes from
a server-verified session (src/api/auth.py), never from client-submitted
form fields — see approve_proposal. The session cookie is SameSite=lax,
which blocks the cross-site POST CSRF depends on, for free, without a
separate token scheme. LLM-triggering endpoints are rate-limited
in-process (see check_rate_limit) — sufficient for a single-process demo,
not a distributed-production answer (that's a Redis-backed concern for a
different scale than this).

Run with: uvicorn src.api.main:app --reload
"""

import json
import os
import queue
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import requests as http_requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.api import auth
from src.guardrails.cost_tracker import get_network_cost_summary, get_workflow_cost
from googleapiclient.errors import HttpError as GmailHttpError

from src.api.queries import (
    count_decisions_in_window,
    count_pending_proposals,
    create_invoice_record,
    decline_proposal,
    get_company,
    get_workflow_trace,
    list_all_invoices,
    list_auto_rejected_for_seller,
    list_companies,
    list_company_invoices,
    list_decisions_in_window,
    list_executed_for_company,
    list_executed_proposals,
    list_invoices_where_buyer,
    list_pending_proposals,
    list_pending_proposals_for_seller,
    list_pairs_for_company,
    invite_pair,
    accept_pair,
    set_pair_auto_reply,
    list_recent_workflows,
    mark_invoice_emailed,
    model_usage_summary,
    weekly_decision_trend,
)
from src.ingestion.document_extraction import extract_invoice
from src.ingestion.gmail_intake import poll_and_process
from src.ingestion.gmail_oauth import send_gmail_message_with_attachment
from src.ontology.db import get_conn
from src.orchestration.events import listen, replay_events
from src.orchestration.graph import run_workflow
from src.tools.execution import ExecutionError, execute_discount
from src.tools.scribo_client import ScriboError, create_invoice, get_sender_email, is_seller_supported

load_dotenv()

INVOICE_PDF_DIR = Path(__file__).resolve().parents[2] / "data" / "seed" / "invoices"

# invoice_number goes straight into a filesystem path below. Starlette's
# default {invoice_number} path converter happens to reject a literal "/"
# in that segment, which blocks the obvious "../../etc/passwd" traversal —
# but that's an accident of routing, not a control this code asserts.
# Validating explicitly here means the safety doesn't depend on staying
# lucky about how the framework's default converter behaves.
INVOICE_NUMBER_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _resolve_invoice_pdf_path(invoice_number: str) -> Path:
    if not INVOICE_NUMBER_RE.match(invoice_number):
        raise HTTPException(400, "invalid invoice number")
    pdf_path = INVOICE_PDF_DIR / f"{invoice_number}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, f"no PDF on file for {invoice_number}")
    return pdf_path


# In-process fixed-window rate limiter for endpoints that trigger a real
# LLM call. A dict is enough for a single-process demo — a distributed
# deployment would need a shared store (Redis), a different scale problem
# than this one.
_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, max_requests: int = 5, window_seconds: int = 60) -> None:
    now = time.monotonic()
    bucket = _rate_limit_buckets[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.pop(0)
    if len(bucket) >= max_requests:
        raise HTTPException(429, f"Rate limit: max {max_requests} requests per {window_seconds}s — try again shortly")
    bucket.append(now)


app = FastAPI(title="Finance Agentic Network — demo")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET_KEY"],
    same_site="lax",  # blocks the cross-site POST CSRF depends on, without a separate token scheme
    https_only=False,  # local http demo; flip to True the moment this sits behind real TLS
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # Vite dev server origin, observed in Phase 1
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals["pending_count"] = count_pending_proposals
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")

# Maps a technical audit_log step to friendly, human-facing narration.
STEP_NARRATION = {
    "intake_triage": ("📨", "Message received", lambda s: f"Classified as: {s['decision']}"),
    "extract_claim": ("🔍", "Request parsed", lambda s: s["reason"]),
    "ground_decision": ("📑", "Checked against the contract on file", lambda s: s["reason"]),
    "risk_score": ("🛡️", "Risk assessed", lambda s: s["reason"]),
    "propose": ("📝", "Response drafted", lambda s: s["reason"]),
    "auto_reject": ("🚫", "Auto-declined — too risky to route to a human as routine", lambda s: s["reason"]),
    "escalate": ("🚩", "Sent for review", lambda s: s["reason"]),
}


def friendly_execution_error(raw: str) -> str:
    """Translates execute_discount's ExecutionError text (written for logs/
    audit, not for a finance-team user) into something a human can act on
    without reading Python exception strings."""
    if "revalidation failed" in raw:
        reason = raw.split("—", 1)[-1].strip() if "—" in raw else raw
        return f"Can't approve this — we re-checked it against the current contract and it's no longer eligible ({reason})."
    if "cannot approve a" in raw:
        return f"You don't have the authority to approve this request. ({raw})"
    if "changed to" in raw and "concurrently" in raw:
        return "This request was just updated by someone else. Refresh the page and try again."
    if "not 'proposed'" in raw:
        return "This request is no longer awaiting approval — someone (or something) already resolved it. Refresh the page."
    return raw


def narrate_trace(trace: list[dict]) -> list[dict]:
    narrated = []
    for step in trace:
        icon, title, detail_fn = STEP_NARRATION.get(step["step"], ("⚙️", step["step"], lambda s: s["reason"]))
        narrated.append({"icon": icon, "title": title, "detail": detail_fn(step)})
    return narrated


def current_approver(request: Request) -> dict | None:
    approver = request.session.get("approver")
    # Sessions from before approvers were pair-scoped carry no company; treat
    # them as signed out so nothing runs unscoped.
    return approver if approver and "company_id" in approver else None


@app.get("/login")
def login_form(request: Request, next: str = "/proposals", error: str = "", company: str = ""):
    company_name = (get_company(company) or {}).get("name") if company else None
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": error, "company_name": company_name})


@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/proposals")):
    approver = auth.authenticate(username, password)
    if approver is None:
        return RedirectResponse(url=f"/login?next={quote(next)}&error=Invalid+username+or+password", status_code=303)
    request.session["approver"] = approver
    return RedirectResponse(url=next, status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/companies", status_code=303)


@app.get("/")
def landing(request: Request):
    return RedirectResponse(url="/companies")


@app.get("/companies")
def companies(request: Request):
    return templates.TemplateResponse(request, "companies.html", {"companies": list_companies()})


def _cached_sender_email_or_placeholder() -> str:
    try:
        return get_sender_email()
    except Exception:
        return "the connected Gmail account"


def _company_page_context(request: Request, company_id: str, result: dict | None = None, invoice_result: dict | None = None) -> dict:
    company = get_company(company_id)
    if company is None:
        raise HTTPException(404, "no such company")
    invoices = list_company_invoices(company_id)
    return {
        "company": company,
        "invoices": invoices,
        "invoices_as_seller_count": sum(1 for inv in invoices if inv["role"] == "issued"),
        "invoices_as_buyer": list_invoices_where_buyer(company_id),
        "other_companies": [c for c in list_companies() if c["id"] != company["id"]],
        "pending": list_pending_proposals_for_seller(company_id),
        "auto_rejected": list_auto_rejected_for_seller(company_id),
        "executed": list_executed_for_company(company_id),
        "result": result,
        "invoice_result": invoice_result,
        "approver": current_approver(request),
        # Browsing a company page must never hard-fail on a Gmail hiccup —
        # this is just informational copy on the invoice-generator form.
        "scribo_sender_email": _cached_sender_email_or_placeholder(),
        "scribo_seller_supported": is_seller_supported(company["name"]),
    }


@app.get("/companies/{company_id}")
def company_detail(request: Request, company_id: str):
    return templates.TemplateResponse(request, "company_detail.html", _company_page_context(request, company_id))


@app.post("/companies/{company_id}/request")
def company_submit_request(request: Request, company_id: str, invoice_id: str = Form(...), message: str = Form(...)):
    check_rate_limit(f"submit:{request.client.host}")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT invoice_number FROM invoice WHERE id = %s", (invoice_id,))
        invoice_number = cur.fetchone()[0]

    final_state = run_workflow(invoice_id, invoice_number, message)
    result = {
        "workflow_id": final_state["workflow_id"],
        "outcome": final_state["proposal_status"],
        "approved_rate": final_state.get("eligibility_approved_rate"),
        "approval_level": final_state.get("eligibility_approval_level"),
        "terminal_reason": final_state.get("terminal_reason"),
        "risk_score": final_state.get("risk_score"),
        "narrated_steps": narrate_trace(get_workflow_trace(final_state["workflow_id"])),
    }

    return templates.TemplateResponse(request, "company_detail.html", _company_page_context(request, company_id, result))


@app.post("/companies/{company_id}/invoice")
def company_generate_invoice(
    request: Request, company_id: str, buyer_company_id: str = Form(...),
    description: str = Form(...), quantity: str = Form(...), unit_price: str = Form(...),
    tax_rate: str = Form("19"), due_date: str = Form(...),
):
    check_rate_limit(f"invoice:{request.client.host}", max_requests=3, window_seconds=300)

    seller = get_company(company_id)
    buyer = get_company(buyer_company_id)
    if seller is None or buyer is None:
        raise HTTPException(404, "no such company")

    try:
        scribo_result = create_invoice(
            seller_name=seller["name"], buyer_name=buyer["name"],
            line_items=[{"description": description, "quantity": quantity, "unit_price": unit_price, "tax_rate": tax_rate}],
            due_date=due_date,
        )

        invoice_number = f"INV-GEN-{uuid.uuid4().hex[:8].upper()}"
        pdf_resp = http_requests.get(scribo_result["download_url"], timeout=30)
        pdf_resp.raise_for_status()
        pdf_path = INVOICE_PDF_DIR / f"{invoice_number}.pdf"
        pdf_path.write_bytes(pdf_resp.content)

        amount = float(quantity) * float(unit_price)
        create_invoice_record(company_id, buyer_company_id, invoice_number, amount, "EUR", due_date)

        sender_email = get_sender_email()
        send_gmail_message_with_attachment(
            to=sender_email,
            subject=f"Invoice {invoice_number} — {seller['name']} to {buyer['name']}",
            body=(
                f"Invoice {invoice_number}, generated via Scribo, from {seller['name']} to {buyer['name']}.\n\n"
                f"{description} — {quantity} x {unit_price} {'EUR'} + {tax_rate}% tax\n\n"
                "This demo network's companies don't have real inboxes, so every generated invoice "
                f"is delivered to {sender_email} regardless of who the buyer is. See BRAIN.md."
            ),
            attachment_path=pdf_path, attachment_name=f"{invoice_number}.pdf",
        )
        mark_invoice_emailed(invoice_number, sender_email)

        invoice_result = {
            "invoice_number": invoice_number, "buyer_name": buyer["name"], "amount": amount,
            "sent_to": sender_email,
        }
        context = _company_page_context(request, company_id, invoice_result=invoice_result)
    except (ScriboError, http_requests.RequestException, GmailHttpError) as e:
        context = _company_page_context(request, company_id)
        context["error"] = f"Couldn't generate the invoice: {e}"
    return templates.TemplateResponse(request, "company_detail.html", context)


@app.get("/ops")
def ops_dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {
        "workflows": list_recent_workflows(), "network_cost": get_network_cost_summary(),
    })


@app.post("/intake/poll")
def poll_gmail(request: Request):
    check_rate_limit(f"poll:{request.client.host}")
    results = poll_and_process()
    poll_result = f"processed {len(results)} new email(s)" if results else "nothing new"
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"workflows": list_recent_workflows(), "poll_result": poll_result, "network_cost": get_network_cost_summary()},
    )


@app.get("/workflow/{workflow_id}")
def workflow_detail(request: Request, workflow_id: str):
    return templates.TemplateResponse(
        request, "workflow_detail.html",
        {"workflow_id": workflow_id, "trace": get_workflow_trace(workflow_id), "cost": get_workflow_cost(workflow_id)},
    )


@app.get("/proposals")
def proposals(request: Request, selected: str = ""):
    approver = current_approver(request)
    if approver is None:
        return RedirectResponse(url="/login?next=/proposals", status_code=303)
    proposal_list = list_pending_proposals(approver["company_id"])
    selected_proposal = next((p for p in proposal_list if str(p["proposal_id"]) == selected), None)
    if selected_proposal is None and proposal_list:
        selected_proposal = proposal_list[0]
    return templates.TemplateResponse(request, "proposals.html", {
        "proposals": proposal_list, "approver": approver,
        "selected_proposal": selected_proposal,
    })


@app.post("/proposals/{proposal_id}/approve")
def approve_proposal(request: Request, proposal_id: str, return_to: str = Form("/proposals")):
    approver = current_approver(request)
    if approver is None:
        return RedirectResponse(url=f"/login?next={quote(return_to)}", status_code=303)

    try:
        execute_discount(proposal_id, approver_name=approver["display_name"], approver_role=approver["role"], approver_company_id=approver["company_id"])
    except ExecutionError as e:
        error = friendly_execution_error(str(e))
        # Render back to wherever the approve was actually clicked from —
        # this used to always fall back to the generic network-wide
        # /proposals page, silently dropping a user out of a specific
        # company's page on failure.
        if return_to.startswith("/companies/"):
            company_id = return_to.removeprefix("/companies/")
            context = _company_page_context(request, company_id)
            context["error"] = error
            return templates.TemplateResponse(request, "company_detail.html", context)
        return templates.TemplateResponse(
            request, "proposals.html",
            {"proposals": list_pending_proposals(approver["company_id"]), "approver": approver, "error": error},
        )
    return RedirectResponse(url=return_to, status_code=303)


@app.post("/proposals/{proposal_id}/decline")
def decline_proposal_route(request: Request, proposal_id: str, return_to: str = Form("/proposals")):
    approver = current_approver(request)
    if approver is None:
        return RedirectResponse(url=f"/login?next={quote(return_to)}", status_code=303)

    conflict_status = decline_proposal(proposal_id, approver_name=approver["display_name"], approver_company_id=approver["company_id"])
    if conflict_status is not None:
        error = (
            f"no such discount_proposal: {proposal_id}" if conflict_status == "not_found"
            else "This request is no longer awaiting approval — someone (or something) already resolved it. Refresh the page."
        )
        # Same "render back to wherever this was clicked from" behavior as
        # approve_proposal — see its comment above.
        if return_to.startswith("/companies/"):
            company_id = return_to.removeprefix("/companies/")
            context = _company_page_context(request, company_id)
            context["error"] = error
            return templates.TemplateResponse(request, "company_detail.html", context)
        return templates.TemplateResponse(
            request, "proposals.html",
            {"proposals": list_pending_proposals(approver["company_id"]), "approver": approver, "error": error},
        )
    return RedirectResponse(url=return_to, status_code=303)


@app.get("/executed")
def executed(request: Request):
    return templates.TemplateResponse(request, "executed.html", {"proposals": list_executed_proposals()})


@app.get("/invoices")
def invoices(request: Request):
    all_invoices = list_all_invoices()
    has_pdf = {p.stem for p in INVOICE_PDF_DIR.glob("*.pdf")}
    return templates.TemplateResponse(request, "invoices.html", {"invoices": all_invoices, "has_pdf": has_pdf})


@app.get("/invoices/{invoice_number}")
def invoice_detail(request: Request, invoice_number: str):
    _resolve_invoice_pdf_path(invoice_number)  # raises 400/404 before rendering
    return templates.TemplateResponse(request, "invoice_detail.html", {"invoice_number": invoice_number, "extraction": None})


@app.get("/invoices/{invoice_number}/pdf")
def invoice_pdf(invoice_number: str):
    pdf_path = _resolve_invoice_pdf_path(invoice_number)
    return FileResponse(pdf_path, media_type="application/pdf")


@app.post("/invoices/{invoice_number}/extract")
def invoice_extract(request: Request, invoice_number: str):
    pdf_path = _resolve_invoice_pdf_path(invoice_number)
    extraction = extract_invoice(str(pdf_path))
    return templates.TemplateResponse(request, "invoice_detail.html", {
        "invoice_number": invoice_number, "extraction": extraction,
    })


# --- JSON API (Phase 1, read-only) ---------------------------------------
# Each route wraps the same query function/context its HTML counterpart
# already calls, zero new business logic. See docs/design/lovable/09-*.md.

@app.get("/api/companies")
def api_companies():
    return list_companies()


@app.get("/api/companies/{company_id}")
def api_company_detail(request: Request, company_id: str):
    context = _company_page_context(request, company_id)
    # result/invoice_result are POST-flash fields (always None on a GET);
    # approver is covered separately by /api/me.
    for key in ("result", "invoice_result", "approver"):
        context.pop(key, None)
    return context


@app.get("/api/proposals")
def api_proposals(request: Request):
    # Scoped to the signed-in approver's side of their pair (PRD R8).
    # Signed out means an empty queue, not the network's queue.
    approver = current_approver(request)
    if approver is None:
        return []
    # created_at -> requested_at: the only key renamed here, to match the
    # frontend's PendingRequest type (frontend/src/lib/fan-data.ts).
    # The underlying query/column name is untouched.
    rows = []
    for p in list_pending_proposals(approver["company_id"]):
        created_at = p.pop("created_at")
        rows.append({**p, "requested_at": created_at})
    return rows


@app.get("/api/invoices")
def api_invoices():
    pdf_stems = {p.stem for p in INVOICE_PDF_DIR.glob("*.pdf")}
    return list_all_invoices(pdf_stems)


@app.get("/api/executed")
def api_executed():
    return list_executed_proposals()


@app.get("/api/audit")
def api_audit():
    # decision -> status, occurred_at -> timestamp: renamed here to match the
    # frontend's AuditRow type (frontend/src/lib/fan-data.ts).
    # The underlying audit_log column names are untouched.
    workflows = []
    for w in list_recent_workflows():
        decision = w.pop("decision")
        occurred_at = w.pop("occurred_at")
        workflows.append({**w, "status": decision, "timestamp": occurred_at})
    return {"workflows": workflows, "network_cost": get_network_cost_summary()}


@app.get("/api/automation")
def api_automation(days: int = 30):
    return {
        "decided_or_pending": count_decisions_in_window(days),
        "weekly": weekly_decision_trend(days),
        "models": model_usage_summary(days),
        "network_cost": get_network_cost_summary(),
        "decisions": list_decisions_in_window(days),
    }


@app.get("/api/me")
def api_me(request: Request):
    return current_approver(request)


# --- JSON API (Phase 2, mutating routes) ----------------------------------
# Each route mirrors its HTML counterpart's exact auth check and underlying
# call (see main.py's HTML routes above), JSON body/response instead of a
# form redirect. Auth failures return 401/409 (HTTPException), not a
# redirect — a redirect is an HTML-route concept.


class LoginBody(BaseModel):
    username: str
    password: str


class DiscountRequestBody(BaseModel):
    invoice_id: str
    message: str


class InvoiceBody(BaseModel):
    buyer_company_id: str
    description: str
    quantity: str
    unit_price: str
    tax_rate: str = "19"
    due_date: str


@app.post("/api/proposals/{proposal_id}/approve")
def api_approve_proposal(request: Request, proposal_id: str):
    approver = current_approver(request)
    if approver is None:
        raise HTTPException(401, "not signed in")
    try:
        result = execute_discount(proposal_id, approver_name=approver["display_name"], approver_role=approver["role"], approver_company_id=approver["company_id"])
    except ExecutionError as e:
        raise HTTPException(409, friendly_execution_error(str(e)))
    return {"ok": True, **result}


@app.post("/api/proposals/{proposal_id}/decline")
def api_decline_proposal(request: Request, proposal_id: str):
    approver = current_approver(request)
    if approver is None:
        raise HTTPException(401, "not signed in")
    conflict_status = decline_proposal(proposal_id, approver_name=approver["display_name"], approver_company_id=approver["company_id"])
    if conflict_status is not None:
        if conflict_status == "not_found":
            raise HTTPException(404, f"no such discount_proposal: {proposal_id}")
        raise HTTPException(409, "This request is no longer awaiting approval — someone (or something) already resolved it.")
    return {"ok": True, "proposal_id": proposal_id, "status": "rejected"}


@app.post("/api/companies/{company_id}/request")
def api_company_submit_request(request: Request, company_id: str, body: DiscountRequestBody):
    check_rate_limit(f"submit:{request.client.host}")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT invoice_number FROM invoice WHERE id = %s", (body.invoice_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, "no such invoice")
        invoice_number = row[0]

    # Blocking, same as the HTML route above — run_workflow can involve real
    # LLM calls and take real wall-clock time. Not made async here; a live-
    # tracking frontend follows progress via Phase 3's SSE stream instead.
    final_state = run_workflow(body.invoice_id, invoice_number, body.message)
    return {
        "workflow_id": final_state["workflow_id"],
        "outcome": final_state["proposal_status"],
        "approved_rate": final_state.get("eligibility_approved_rate"),
        "approval_level": final_state.get("eligibility_approval_level"),
        "terminal_reason": final_state.get("terminal_reason"),
        "risk_score": final_state.get("risk_score"),
    }


@app.post("/api/companies/{company_id}/invoice")
def api_company_generate_invoice(request: Request, company_id: str, body: InvoiceBody):
    check_rate_limit(f"invoice:{request.client.host}", max_requests=3, window_seconds=300)

    seller = get_company(company_id)
    buyer = get_company(body.buyer_company_id)
    if seller is None or buyer is None:
        raise HTTPException(404, "no such company")

    try:
        scribo_result = create_invoice(
            seller_name=seller["name"], buyer_name=buyer["name"],
            line_items=[{
                "description": body.description, "quantity": body.quantity,
                "unit_price": body.unit_price, "tax_rate": body.tax_rate,
            }],
            due_date=body.due_date,
        )

        invoice_number = f"INV-GEN-{uuid.uuid4().hex[:8].upper()}"
        pdf_resp = http_requests.get(scribo_result["download_url"], timeout=30)
        pdf_resp.raise_for_status()
        pdf_path = INVOICE_PDF_DIR / f"{invoice_number}.pdf"
        pdf_path.write_bytes(pdf_resp.content)

        amount = float(body.quantity) * float(body.unit_price)
        create_invoice_record(company_id, body.buyer_company_id, invoice_number, amount, "EUR", body.due_date)

        sender_email = get_sender_email()
        send_gmail_message_with_attachment(
            to=sender_email,
            subject=f"Invoice {invoice_number} — {seller['name']} to {buyer['name']}",
            body=(
                f"Invoice {invoice_number}, generated via Scribo, from {seller['name']} to {buyer['name']}.\n\n"
                f"{body.description} — {body.quantity} x {body.unit_price} EUR + {body.tax_rate}% tax\n\n"
                "This demo network's companies don't have real inboxes, so every generated invoice "
                f"is delivered to {sender_email} regardless of who the buyer is. See BRAIN.md."
            ),
            attachment_path=pdf_path, attachment_name=f"{invoice_number}.pdf",
        )
        mark_invoice_emailed(invoice_number, sender_email)
    except (ScriboError, http_requests.RequestException, GmailHttpError) as e:
        raise HTTPException(502, f"Couldn't generate the invoice: {e}")

    return {
        "ok": True, "invoice_number": invoice_number, "buyer_name": buyer["name"],
        "amount": amount, "sent_to": sender_email,
    }


# --- Pairs (PRD 2a, R19..R21) ------------------------------------------------
# Everything here is scoped to the signed-in approver's company. The SQL
# guards repeat the check, so a wrong pair id changes nothing.

class InviteBody(BaseModel):
    counterparty_company_id: str


class PairSettingsBody(BaseModel):
    auto_reply_status_inquiry: bool


def _require_approver(request: Request) -> dict:
    approver = current_approver(request)
    if approver is None:
        raise HTTPException(401, "not signed in")
    return approver


@app.get("/api/pairs")
def api_pairs(request: Request):
    approver = _require_approver(request)
    return list_pairs_for_company(approver["company_id"])


@app.post("/api/pairs")
def api_invite_pair(request: Request, body: InviteBody):
    approver = _require_approver(request)
    pair_id = invite_pair(approver["company_id"], body.counterparty_company_id)
    if pair_id is None:
        raise HTTPException(409, "A pair with that company already exists, or it is your own company.")
    return {"ok": True, "pair_id": pair_id}


@app.post("/api/pairs/{pair_id}/accept")
def api_accept_pair(request: Request, pair_id: str):
    approver = _require_approver(request)
    if not accept_pair(pair_id, approver["company_id"]):
        raise HTTPException(409, "Nothing to accept: not an open invite to your company, or you sent it.")
    return {"ok": True}


@app.post("/api/pairs/{pair_id}/settings")
def api_pair_settings(request: Request, pair_id: str, body: PairSettingsBody):
    approver = _require_approver(request)
    if not set_pair_auto_reply(pair_id, approver["company_id"], body.auto_reply_status_inquiry):
        raise HTTPException(409, "Pair is not active or is not yours.")
    return {"ok": True}


@app.post("/api/login")
def api_login(request: Request, body: LoginBody):
    approver = auth.authenticate(body.username, body.password)
    if approver is None:
        raise HTTPException(401, "Invalid username or password")
    request.session["approver"] = approver
    return approver


@app.post("/api/logout")
def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.post("/api/intake/poll")
def api_poll_gmail(request: Request):
    check_rate_limit(f"poll:{request.client.host}")
    results = poll_and_process()
    return {"ok": True, "processed": len(results)}


# --- JSON API (Phase 3, SSE live events) ----------------------------------

@app.get("/api/events/stream")
def api_events_stream(since_id: int = 0):
    """Bridges events.listen() (a blocking, thread-based consumer) into an
    SSE stream: a plain sync generator, run in Starlette's threadpool same
    as every other sync route handler here — no asyncio needed. listen()
    runs on its own daemon thread (same lifecycle events.demo() already
    uses) and pushes each live event into a queue.Queue; this generator
    drains that queue and yields SSE lines. Catch-up first: replay_events()
    is exhausted before the live thread even starts, so nothing published
    between replay and LISTEN registering is missed."""
    def gen():
        for row in replay_events(since_id):
            yield f"data: {json.dumps(row, default=str)}\n\n"

        q: queue.Queue = queue.Queue()
        stop_event = threading.Event()
        threading.Thread(target=listen, args=(q.put, stop_event), daemon=True).start()
        try:
            while True:
                yield f"data: {json.dumps(q.get())}\n\n"
        finally:
            stop_event.set()

    return StreamingResponse(gen(), media_type="text/event-stream")
