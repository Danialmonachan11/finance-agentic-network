"""Gmail intake (docs/architecture.md §3.8 email-first architecture).

Gmail READ is real: gmail_oauth.py wires the actual Gmail API (OAuth2,
read + compose scopes only — no send) — see BRAIN.md's decisions log
(2026-08-24) for the earlier stub this replaced and why it was a documented
gap rather than a fake success, until real OAuth credentials were available.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion.gmail_oauth import create_gmail_draft, fetch_unread_emails
from src.ontology.db import get_conn
from src.orchestration.graph import run_workflow
from src.orchestration.state import WorkflowState

INVOICE_NUMBER_PATTERN = re.compile(r"\bINV-\d+\b")


def extract_invoice_number(email_text: str) -> str | None:
    match = INVOICE_NUMBER_PATTERN.search(email_text)
    return match.group(0) if match else None


def resolve_invoice_id(invoice_number: str) -> str | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM invoice WHERE invoice_number = %s", (invoice_number,))
        row = cur.fetchone()
        return str(row[0]) if row else None


def run_intake(subject: str, body: str, sender: str) -> WorkflowState | None:
    """Intake/Triage agent's non-LLM half: resolve which invoice (if any)
    this email is about, before handing off to the LangGraph workflow.
    Returns None if no invoice number is found — that's a routing decision
    made here (deterministic), not something worth spending an LLM call on."""
    invoice_number = extract_invoice_number(body) or extract_invoice_number(subject)
    if invoice_number is None:
        return None

    invoice_id = resolve_invoice_id(invoice_number)
    if invoice_id is None:
        return None  # mentions an invoice number we don't have on file — a real system would escalate this, not silently drop it

    return run_workflow(invoice_id, invoice_number, email_text=body)


def _already_processed(message_id: str) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM processed_email WHERE message_id = %s", (message_id,))
        return cur.fetchone() is not None


def _record_processed(message_id: str, workflow_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO processed_email (message_id, workflow_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (message_id, workflow_id),
        )


def poll_and_process(query: str = "in:inbox -in:draft subject:INV-1002") -> list[WorkflowState]:
    """The real end-to-end loop: fetch matching emails via the actual Gmail
    API, skip ones already processed (tracked in our own Postgres, not via
    Gmail's UNREAD label — see module docstring), run the rest through the
    workflow, and create a reply draft (never send) for anything that
    reaches a proposal. The Tier 2 boundary from §3.7 is enforced
    structurally — create_gmail_draft is the only Gmail write this module
    calls; there is no send path, and OAuth scopes don't grant one either."""
    results = []
    for email in fetch_unread_emails(query=query):
        if _already_processed(email["id"]):
            continue

        final_state = run_intake(email["subject"], email["body"], email["sender"])
        if final_state is None:
            continue
        results.append(final_state)
        if final_state.get("proposal_status") in ("proposed", "auto_executed"):
            create_gmail_draft(
                to=email["sender"],
                subject=f"Re: {email['subject']}",
                body=final_state["draft_response"],
                thread_id=email["threadId"],
            )
        _record_processed(email["id"], final_state["workflow_id"])
    return results


def demo() -> None:
    # Idempotent by design (see poll_and_process's mark_as_read): the first
    # run against a fresh unread email processes it; every re-run after
    # that correctly finds nothing left to do rather than reprocessing.
    results = poll_and_process()

    if not results:
        print("gmail_intake.demo(): no unread matching email found — "
              "either none exists yet, or it was already processed on a prior run (idempotent, expected)")
        return

    final_state = results[0]
    assert final_state["proposal_status"] == "proposed", final_state
    assert final_state["eligibility_approval_level"] == "manager", final_state

    print(f"gmail_intake.demo(): processed {len(results)} real email(s) via the live Gmail API")
    print(f"  invoice_id={final_state['invoice_id']}, "
          f"proposal_status={final_state['proposal_status']}, "
          f"approval_level={final_state['eligibility_approval_level']}")
    print(f"  draft: {final_state['draft_response'][:120]}...")


if __name__ == "__main__":
    demo()
