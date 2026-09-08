"""Gmail intake (docs/reference/architecture.md §3.8 email-first architecture).

Gmail READ is real: gmail_oauth.py wires the actual Gmail API (OAuth2,
read + compose scopes only — no send) — see BRAIN.md's decisions log
(2026-08-24) for the earlier stub this replaced and why it was a documented
gap rather than a fake success, until real OAuth credentials were available.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.guardrails.audit import log_audit
from src.api.queries import pair_settings_for_invoice
from src.ingestion.gmail_oauth import create_gmail_draft, fetch_unread_emails, send_gmail_message
from src.ontology.db import get_conn
from src.orchestration.graph import run_workflow
from src.orchestration.state import WorkflowState
from src.tools.resolver import resolve_invoice


def run_intake(subject: str, body: str, sender: str) -> WorkflowState | None:
    """Intake's non-LLM half: resolve which invoice this email is about
    (sender's company plus quoted number or amount, PRD R2) before any
    model call. Unresolvable mail is logged for a human with the reason
    (R3) and returns None: never silently dropped, never guessed."""
    hit = resolve_invoice(sender, f"{subject}\n{body}")
    if hit is None:
        log_audit(uuid.uuid4(), step="intake_resolve", agent="intake_gateway",
                   decision="needs_human", reason=f"no unambiguous invoice for sender {sender!r}")
        return None
    invoice_id, invoice_number = hit
    return run_workflow(invoice_id, invoice_number, email_text=body)


def deliver_reply(final_state: WorkflowState, email: dict) -> str:
    """Draft or send (PRD R5). Default is a draft. A status-inquiry reply is
    sent only when the pair between the two companies is active and has the
    switch on. Claim replies stay drafts: a human reads them before they go.
    Returns 'sent' or 'drafted'."""
    settings = pair_settings_for_invoice(final_state["invoice_id"])
    may_send = (
        final_state.get("proposal_status") == "status_answered"
        and settings is not None
        and settings["status"] == "active"
        and settings["auto_reply_status_inquiry"]
    )
    if may_send:
        send_gmail_message(to=email["sender"], subject=f"Re: {email['subject']}", body=final_state["draft_response"])
        return "sent"
    create_gmail_draft(
        to=email["sender"], subject=f"Re: {email['subject']}",
        body=final_state["draft_response"], thread_id=email["threadId"],
    )
    return "drafted"


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
        if final_state.get("proposal_status") in ("proposed", "auto_executed", "status_answered"):
            deliver_reply(final_state, email)
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
