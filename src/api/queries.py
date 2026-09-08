"""Read-only queries backing the web app. Deliberately thin: a view over
data the pipeline already writes (audit_log, discount_proposal,
workflow_event) — no decision logic here, just rendering what's true in
Postgres. Network model (company can be seller on one invoice, buyer on
another) — see BRAIN.md decisions log, 2026-08-24.
"""

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn
from src.orchestration.events import publish_event


def list_recent_workflows(limit: int = 25) -> list[dict]:
    """One row per workflow_id: its latest audit_log entry, which shows
    where the workflow currently stands (proposed / escalated / executed)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (workflow_id)
                workflow_id, step, agent, decision, reason, occurred_at
            FROM audit_log
            ORDER BY workflow_id, occurred_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    rows.sort(key=lambda r: r["occurred_at"], reverse=True)
    return rows


def get_workflow_trace(workflow_id: str) -> list[dict]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT step, agent, model, decision, reason, tool_calls, occurred_at "
            "FROM audit_log WHERE workflow_id = %s ORDER BY occurred_at",
            (workflow_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_companies() -> list[dict]:
    """Network overview: every company, with counts of invoices where it's
    the seller vs the buyer — this is what makes it visible that the same
    company plays both roles, not a fixed one-directional relationship."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.name,
                   (SELECT count(*) FROM invoice i WHERE i.seller_company_id = c.id) AS invoices_as_seller,
                   (SELECT count(*) FROM invoice i WHERE i.buyer_company_id = c.id) AS invoices_as_buyer,
                   (SELECT count(*) FROM discount_proposal dp JOIN invoice i ON i.id = dp.invoice_id
                    WHERE i.seller_company_id = c.id AND dp.status = 'proposed') AS pending_as_seller,
                   COALESCE((SELECT SUM(i2.amount) FROM invoice i2
                    WHERE i2.seller_company_id = c.id AND i2.status != 'paid'), 0) AS receivable,
                   COALESCE((SELECT SUM(i2.amount) FROM invoice i2
                    WHERE i2.buyer_company_id = c.id AND i2.status != 'paid'), 0) AS payable
            FROM company c
            ORDER BY c.name
            """
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_company(company_id: str) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, email_domain FROM company WHERE id = %s", (company_id,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [c.name for c in cur.description]
        return dict(zip(cols, row))


def list_company_invoices(company_id: str) -> list[dict]:
    """The actual invoice tracker a company's page was missing — every
    invoice touching this company, either role, with its current discount
    status attached. Closes the gap where the summary cards said '1
    issued / 1 received' with no way to see which invoice that even was."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id AS invoice_id, i.invoice_number, i.amount,
                   CASE WHEN i.seller_company_id = %(cid)s THEN 'issued' ELSE 'received' END AS role,
                   other.name AS counterparty,
                   ct.status AS contract_status,
                   latest.status AS discount_status, latest.claimed_rate, latest.approved_rate,
                   latest.workflow_id,
                   i.raw_extraction->>'emailed_to' AS emailed_to
            FROM invoice i
            JOIN company other ON other.id = (CASE WHEN i.seller_company_id = %(cid)s THEN i.buyer_company_id ELSE i.seller_company_id END)
            LEFT JOIN contract ct ON ct.id = i.contract_id
            LEFT JOIN LATERAL (
                SELECT dp.status, dp.claimed_rate, dp.approved_rate, dp.workflow_id
                FROM discount_proposal dp WHERE dp.invoice_id = i.id ORDER BY dp.created_at DESC LIMIT 1
            ) latest ON true
            WHERE i.seller_company_id = %(cid)s OR i.buyer_company_id = %(cid)s
            ORDER BY i.invoice_number
            """,
            {"cid": company_id},
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def create_invoice_record(
    seller_company_id: str, buyer_company_id: str, invoice_number: str,
    amount: float, currency: str, due_date: str,
) -> str:
    """Records a locally-generated invoice (via the Scribo invoice-generator
    feature — src/tools/scribo_client.py) so it shows up in the same
    invoice tracker as seeded/emailed invoices, not a separate silo."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO invoice (seller_company_id, buyer_company_id, invoice_number, amount, currency, issued_date, due_date)
            VALUES (%s, %s, %s, %s, %s, CURRENT_DATE, %s)
            RETURNING id
            """,
            (seller_company_id, buyer_company_id, invoice_number, amount, currency, due_date),
        )
        return str(cur.fetchone()[0])


def mark_invoice_emailed(invoice_number: str, sent_to: str) -> None:
    """Persists proof-of-send so the invoice tracker can show '📧 emailed'
    after the one-time result banner is gone — reuses raw_extraction
    (already on the invoice table, JSONB, otherwise only used by the
    document-extraction agent) instead of a schema migration for one flag."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE invoice SET raw_extraction = %s WHERE invoice_number = %s",
            (json.dumps({"emailed_to": sent_to}), invoice_number),
        )


def _reason_subqueries() -> str:
    """Shared SQL fragment: pull the actual grounding/risk explanation out
    of audit_log for a proposal's workflow_id, so a human sees WHY without
    clicking into the technical trace. NULL for seed rows (no workflow_id)."""
    return """
        (SELECT a.reason FROM audit_log a WHERE a.workflow_id = dp.workflow_id AND a.step = 'ground_decision' LIMIT 1) AS grounding_reason,
        (SELECT a.reason FROM audit_log a WHERE a.workflow_id = dp.workflow_id AND a.step = 'risk_score' LIMIT 1) AS risk_reason
    """


def list_invoices_where_buyer(company_id: str) -> list[dict]:
    """Invoices THIS company received — the ones it could plausibly send a
    discount request about. Powers the 'send a request' form on a
    company's page."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id AS invoice_id, i.invoice_number, i.amount, s.name AS seller_name,
                   ct.status AS contract_status
            FROM invoice i
            JOIN company s ON s.id = i.seller_company_id
            LEFT JOIN contract ct ON ct.id = i.contract_id
            WHERE i.buyer_company_id = %s
            ORDER BY i.invoice_number
            """,
            (company_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_pending_proposals_for_seller(company_id: str) -> list[dict]:
    """Requests THIS company (as seller) needs to review — its finance
    team's inbox. Includes the actual grounding/risk reasoning so a human
    can see WHY this needs a decision without clicking into a technical
    trace first."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT dp.id AS proposal_id, dp.invoice_id, dp.workflow_id, i.invoice_number,
                   b.name AS buyer_name, dp.claimed_rate, dp.approval_level, dp.status,
                   dp.justification, dp.created_at, {_reason_subqueries()}
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            JOIN company b ON b.id = i.buyer_company_id
            WHERE dp.status = 'proposed' AND i.seller_company_id = %s
            ORDER BY dp.created_at DESC
            """,
            (company_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_pending_proposals(seller_company_id: str | None = None) -> list[dict]:
    """Pending list for /proposals and /api/proposals. Pass the signed-in
    approver's company so they see only proposals their side must decide
    (PRD R8); None is the unscoped ops view. Carries invoice
    amount/due_date/contract_status and risk_score too, so the master-detail
    panel has everything it needs without a second query per selection."""
    scope = "AND i.seller_company_id = %s" if seller_company_id else ""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT dp.id AS proposal_id, dp.invoice_id, dp.workflow_id, i.invoice_number,
                   s.name AS seller_name, b.name AS buyer_name,
                   dp.claimed_rate, dp.approval_level, dp.status, dp.justification, dp.created_at,
                   i.amount, i.due_date, ct.status AS contract_status, dp.risk_score,
                   {_reason_subqueries()}
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            JOIN company s ON s.id = i.seller_company_id
            JOIN company b ON b.id = i.buyer_company_id
            LEFT JOIN contract ct ON ct.id = i.contract_id
            WHERE dp.status = 'proposed' {scope}
            ORDER BY dp.created_at DESC
            """,
            (seller_company_id,) if seller_company_id else (),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def count_pending_proposals() -> int:
    """Cheap count for the nav badge — no point fetching full rows just to
    len() them."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM discount_proposal WHERE status = 'proposed'")
        return cur.fetchone()[0]


def list_auto_rejected_for_seller(company_id: str, limit: int = 25) -> list[dict]:
    """Requests auto-declined by the risk gate before ever reaching this
    company's to-do list — informational, not actionable (there's no
    approve button here on purpose, see nodes.auto_reject). Distinguished
    from other 'rejected' rows (e.g. a grounded contract-expiry rejection)
    by having a workflow_id — only a live risk-gated run sets that on a
    'rejected' row; escalate()'s grounded-rejection path updates a
    pre-existing row in place and never touches workflow_id. Also excludes
    rows with approved_by set: a human decline (decline_proposal, below)
    sets workflow_id too but always records who declined it, which
    auto_reject() never does for its own rows — that's what keeps a human
    decline from showing up here misclassified as an auto-rejection."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT dp.id AS proposal_id, dp.workflow_id, i.invoice_number,
                   b.name AS buyer_name, dp.claimed_rate, dp.risk_score, dp.created_at, {_reason_subqueries()}
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            JOIN company b ON b.id = i.buyer_company_id
            WHERE dp.status = 'rejected' AND dp.workflow_id IS NOT NULL AND dp.approved_by IS NULL
                  AND i.seller_company_id = %s
            ORDER BY dp.created_at DESC
            LIMIT %s
            """,
            (company_id, limit),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_executed_for_company(company_id: str, limit: int = 25) -> list[dict]:
    """Execution history touching this company, either side."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT dp.id AS proposal_id, dp.workflow_id, i.invoice_number,
                   s.name AS seller_name, b.name AS buyer_name,
                   dp.claimed_rate, dp.approved_rate, dp.approval_level, dp.approved_by, dp.decided_at
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            JOIN company s ON s.id = i.seller_company_id
            JOIN company b ON b.id = i.buyer_company_id
            WHERE dp.status = 'executed' AND (i.seller_company_id = %s OR i.buyer_company_id = %s)
            ORDER BY dp.decided_at DESC
            LIMIT %s
            """,
            (company_id, company_id, limit),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_executed_proposals(limit: int = 25) -> list[dict]:
    """Network-wide execution history — used by the technical/ops view."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT dp.id AS proposal_id, dp.workflow_id, i.invoice_number,
                   s.name AS seller_name, b.name AS buyer_name,
                   dp.claimed_rate, dp.approved_rate, dp.approval_level, dp.approved_by, dp.decided_at
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            JOIN company s ON s.id = i.seller_company_id
            JOIN company b ON b.id = i.buyer_company_id
            WHERE dp.status = 'executed'
            ORDER BY dp.decided_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def decline_proposal(proposal_id: str, approver_name: str, approver_company_id: str) -> str | None:
    """Declines a pending proposal in place: sets status='rejected',
    approved_by to the signed-in approver, decided_at now. Conditioned on
    status = 'proposed', same atomic check-and-set as execute_discount's
    UPDATE (src/tools/execution.py) — guards against a stale click racing
    another decision on the same row. Returns None on success, or the row's
    actual current status (or 'not_found') if the guard didn't match."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE discount_proposal SET status = 'rejected', approved_by = %s, "
            "decided_at = now() WHERE id = %s AND status = 'proposed' "
            "AND invoice_id IN (SELECT id FROM invoice WHERE seller_company_id = %s) "
            "RETURNING workflow_id, invoice_id",
            (approver_name, proposal_id, approver_company_id),
        )
        row = cur.fetchone()
        if row is not None:
            workflow_id, invoice_id = row
            # workflow_id is nullable (schema.sql) — pre-seeded/legacy proposal
            # rows with no real workflow have nothing to key an event on, so
            # there's nothing to publish for them.
            if workflow_id is not None:
                publish_event(uuid.UUID(str(workflow_id)), "workflow.declined", {
                    "invoice_id": str(invoice_id), "declined_by": approver_name,
                })
            return None
        cur.execute("SELECT status FROM discount_proposal WHERE id = %s", (proposal_id,))
        row = cur.fetchone()
        return row[0] if row else "not_found"


# approved_by set by auto_execute() (src/orchestration/nodes.py) always
# starts with this — the one signal that distinguishes an agent's own
# execution from a real human's, since both set approved_by. Not a separate
# column because this predates auto_execute existing; a real column
# (e.g. decided_by_kind) would be cleaner if this grows more cases.
_AUTO_EXECUTE_APPROVER_PREFIX = "AI Agent (auto-execute"


def count_decisions_in_window(days: int = 30) -> dict:
    """Automation summary for the agents page: how many discount_proposal
    decisions in the last `days` were made by the pipeline alone, either
    declining (auto-declined — same discriminator as
    list_auto_rejected_for_seller) or executing (auto_executed —
    approved_by set by the agent, not a human), vs by an actual human
    (approved_by set, and not the agent's signature) vs still awaiting one.
    `%s * interval '1 day'` keeps `days` a bound parameter instead of
    string-formatting it into the SQL."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE status = 'rejected' AND workflow_id IS NOT NULL AND approved_by IS NULL),
                   count(*) FILTER (WHERE approved_by LIKE %s),
                   count(*) FILTER (WHERE approved_by IS NOT NULL AND approved_by NOT LIKE %s),
                   count(*) FILTER (WHERE status = 'proposed')
            FROM discount_proposal
            WHERE created_at >= now() - (%s * interval '1 day')
            """,
            (_AUTO_EXECUTE_APPROVER_PREFIX + "%", _AUTO_EXECUTE_APPROVER_PREFIX + "%", days),
        )
        total, auto_declined, auto_executed, human_decided, still_pending = cur.fetchone()
    return {
        "total": total, "auto_declined": auto_declined, "auto_executed": auto_executed,
        "human_decided": human_decided, "still_pending": still_pending,
    }


def weekly_decision_trend(days: int = 30) -> list[dict]:
    """Same three-way split as count_decisions_in_window, bucketed by ISO
    week, oldest first, for the agents page's weekly bars."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT date_trunc('week', created_at) AS week,
                   count(*) FILTER (WHERE status = 'rejected' AND workflow_id IS NOT NULL AND approved_by IS NULL) AS auto_declined,
                   count(*) FILTER (WHERE approved_by LIKE %s) AS auto_executed,
                   count(*) FILTER (WHERE approved_by IS NOT NULL AND approved_by NOT LIKE %s) AS human_decided
            FROM discount_proposal
            WHERE created_at >= now() - (%s * interval '1 day')
            GROUP BY week
            ORDER BY week
            """,
            (_AUTO_EXECUTE_APPROVER_PREFIX + "%", _AUTO_EXECUTE_APPROVER_PREFIX + "%", days),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_decisions_in_window(days: int = 30, limit: int = 50) -> list[dict]:
    """The actual rows behind count_decisions_in_window's numbers — every
    proposal in the window that was decided one way or another (declined by
    the pipeline, executed by the agent, or decided by a human), newest
    first. Exists so the agents page's stat tiles have something concrete
    to point at instead of being just numbers."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.invoice_number, s.name AS seller_name, b.name AS buyer_name,
                   dp.claimed_rate, dp.approved_rate, dp.approved_by,
                   COALESCE(dp.decided_at, dp.created_at) AS decided_at,
                   CASE
                       WHEN dp.status = 'rejected' AND dp.workflow_id IS NOT NULL AND dp.approved_by IS NULL
                           THEN 'auto_declined'
                       WHEN dp.approved_by LIKE %s THEN 'auto_executed'
                       ELSE 'human_decided'
                   END AS outcome
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            JOIN company s ON s.id = i.seller_company_id
            JOIN company b ON b.id = i.buyer_company_id
            WHERE dp.created_at >= now() - (%s * interval '1 day')
              AND (dp.approved_by IS NOT NULL
                   OR (dp.status = 'rejected' AND dp.workflow_id IS NOT NULL))
            ORDER BY COALESCE(dp.decided_at, dp.created_at) DESC
            LIMIT %s
            """,
            (_AUTO_EXECUTE_APPROVER_PREFIX + "%", days, limit),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def model_usage_summary(days: int = 30) -> list[dict]:
    """Per-model call/token/cost totals from llm_call_cost for the window —
    no latency or agreement_rate columns, they don't exist on this table
    (see docs/design/lovable/10-agents-page-plan.md Phase 0)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT model, count(*) AS calls,
                   COALESCE(SUM(input_tokens), 0) AS tokens_in,
                   COALESCE(SUM(output_tokens), 0) AS tokens_out,
                   COALESCE(SUM(estimated_cost_usd), 0) AS cost_usd
            FROM llm_call_cost
            WHERE occurred_at >= now() - (%s * interval '1 day')
            GROUP BY model
            ORDER BY model
            """,
            (days,),
        )
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    for r in rows:
        r["cost_usd"] = float(r["cost_usd"])
    return rows


def list_all_invoices(pdf_stems: set[str] | None = None) -> list[dict]:
    """Network-wide invoice list — used by /invoices (document viewer) and
    the ops view. Not company-scoped; that's list_invoices_where_buyer's job.
    `pdf_stems` (invoice numbers with a real PDF on disk) is optional so
    callers that don't care about has_pdf don't pay for the glob."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id AS invoice_id, i.invoice_number, i.amount,
                   s.name AS seller_name, b.name AS buyer_name,
                   ct.status AS contract_status
            FROM invoice i
            JOIN company s ON s.id = i.seller_company_id
            JOIN company b ON b.id = i.buyer_company_id
            LEFT JOIN contract ct ON ct.id = i.contract_id
            ORDER BY i.invoice_number
            """
        )
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        if pdf_stems is not None:
            for row in rows:
                row["has_pdf"] = row["invoice_number"] in pdf_stems
        return rows
