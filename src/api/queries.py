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


# Which workflow ids touch a company (PRD 2a: a company sees its own cases
# only). A workflow is the company's if its proposal is on one of the
# company's invoices, or if any of its events names one of them. Used as a
# subquery with a %(cid)s parameter.
MY_WORKFLOWS_SQL = """
    SELECT dp.workflow_id FROM discount_proposal dp
    JOIN invoice i ON i.id = dp.invoice_id
    WHERE dp.workflow_id IS NOT NULL AND %(cid)s IN (i.seller_company_id, i.buyer_company_id)
    UNION
    SELECT we.workflow_id FROM workflow_event we
    JOIN invoice i ON i.invoice_number = we.payload->>'invoice_number' OR i.id::text = we.payload->>'invoice_id'
    WHERE %(cid)s IN (i.seller_company_id, i.buyer_company_id)
"""


def list_recent_workflows(company_id: str, limit: int = 25) -> list[dict]:
    """One row per workflow_id: its latest audit_log entry, which shows
    where the workflow currently stands (proposed / escalated / executed)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (workflow_id)
                workflow_id, step, agent, decision, reason, occurred_at
            FROM audit_log
            WHERE workflow_id IN ({MY})
            ORDER BY workflow_id, occurred_at DESC
            LIMIT %(limit)s
            """.replace("{MY}", MY_WORKFLOWS_SQL),
            {"cid": company_id, "limit": limit},
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


def list_companies(company_id: str) -> list[dict]:
    """The signed-in company and its counterparties (the other side of each
    of its pairs), nothing else (PRD R21). Every count is relative to the
    signed-in company: a counterparty's 'invoices as seller' means invoices
    it sold to us, not everything it ever sold to anyone."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH me AS (SELECT %(cid)s::uuid AS id)
            SELECT c.id, c.name,
                   (SELECT count(*) FROM invoice i, me WHERE i.seller_company_id = c.id
                      AND (c.id = me.id OR i.buyer_company_id = me.id)) AS invoices_as_seller,
                   (SELECT count(*) FROM invoice i, me WHERE i.buyer_company_id = c.id
                      AND (c.id = me.id OR i.seller_company_id = me.id)) AS invoices_as_buyer,
                   (SELECT count(*) FROM discount_proposal dp JOIN invoice i ON i.id = dp.invoice_id, me
                    WHERE i.seller_company_id = c.id AND dp.status = 'proposed'
                      AND (c.id = me.id OR i.buyer_company_id = me.id)) AS pending_as_seller,
                   COALESCE((SELECT SUM(i2.amount) FROM invoice i2, me
                    WHERE i2.seller_company_id = c.id AND i2.status != 'paid'
                      AND (c.id = me.id OR i2.buyer_company_id = me.id)), 0) AS receivable,
                   COALESCE((SELECT SUM(i2.amount) FROM invoice i2, me
                    WHERE i2.buyer_company_id = c.id AND i2.status != 'paid'
                      AND (c.id = me.id OR i2.seller_company_id = me.id)), 0) AS payable
            FROM company c, me
            WHERE c.id = me.id
               OR EXISTS (SELECT 1 FROM pair p WHERE me.id IN (p.company_a_id, p.company_b_id)
                                                 AND c.id IN (p.company_a_id, p.company_b_id))
            ORDER BY (c.id = me.id) DESC, c.name
            """,
            {"cid": company_id},
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


def count_decisions_in_window(company_id: str, days: int = 30) -> dict:
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
                   count(*) FILTER (WHERE dp.status = 'rejected' AND dp.workflow_id IS NOT NULL AND dp.approved_by IS NULL),
                   count(*) FILTER (WHERE dp.approved_by LIKE %s),
                   count(*) FILTER (WHERE dp.approved_by IS NOT NULL AND dp.approved_by NOT LIKE %s),
                   count(*) FILTER (WHERE dp.status = 'proposed')
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            WHERE dp.created_at >= now() - (%s * interval '1 day')
              AND %s IN (i.seller_company_id, i.buyer_company_id)
            """,
            (_AUTO_EXECUTE_APPROVER_PREFIX + "%", _AUTO_EXECUTE_APPROVER_PREFIX + "%", days, company_id),
        )
        total, auto_declined, auto_executed, human_decided, still_pending = cur.fetchone()
    return {
        "total": total, "auto_declined": auto_declined, "auto_executed": auto_executed,
        "human_decided": human_decided, "still_pending": still_pending,
    }


def weekly_decision_trend(company_id: str, days: int = 30) -> list[dict]:
    """Same three-way split as count_decisions_in_window, bucketed by ISO
    week, oldest first, for the agents page's weekly bars."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT date_trunc('week', dp.created_at) AS week,
                   count(*) FILTER (WHERE dp.status = 'rejected' AND dp.workflow_id IS NOT NULL AND dp.approved_by IS NULL) AS auto_declined,
                   count(*) FILTER (WHERE dp.approved_by LIKE %s) AS auto_executed,
                   count(*) FILTER (WHERE dp.approved_by IS NOT NULL AND dp.approved_by NOT LIKE %s) AS human_decided
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            WHERE dp.created_at >= now() - (%s * interval '1 day')
              AND %s IN (i.seller_company_id, i.buyer_company_id)
            GROUP BY week
            ORDER BY week
            """,
            (_AUTO_EXECUTE_APPROVER_PREFIX + "%", _AUTO_EXECUTE_APPROVER_PREFIX + "%", days, company_id),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_decisions_in_window(company_id: str, days: int = 30, limit: int = 50) -> list[dict]:
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
              AND %s IN (i.seller_company_id, i.buyer_company_id)
              AND (dp.approved_by IS NOT NULL
                   OR (dp.status = 'rejected' AND dp.workflow_id IS NOT NULL))
            ORDER BY COALESCE(dp.decided_at, dp.created_at) DESC
            LIMIT %s
            """,
            (_AUTO_EXECUTE_APPROVER_PREFIX + "%", days, company_id, limit),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def model_usage_summary(company_id: str, days: int = 30) -> list[dict]:
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
            WHERE occurred_at >= now() - (%(days)s * interval '1 day')
              AND workflow_id IN ({MY})
            GROUP BY model
            ORDER BY model
            """.replace("{MY}", MY_WORKFLOWS_SQL),
            {"days": days, "cid": company_id},
        )
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    for r in rows:
        r["cost_usd"] = float(r["cost_usd"])
    return rows


def list_all_invoices(company_id: str, pdf_stems: set[str] | None = None) -> list[dict]:
    """The signed-in company's invoices, both directions: 'payable' when it
    is the buyer, 'receivable' when it is the seller. Invoices between two
    other companies never appear (PRD 2a). `pdf_stems` (invoice numbers with
    a real PDF on disk) is optional so callers that don't care about has_pdf
    don't pay for the glob."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id AS invoice_id, i.invoice_number, i.amount,
                   s.name AS seller_name, b.name AS buyer_name,
                   ct.status AS contract_status,
                   CASE WHEN i.buyer_company_id = %(cid)s THEN 'payable' ELSE 'receivable' END AS direction
            FROM invoice i
            JOIN company s ON s.id = i.seller_company_id
            JOIN company b ON b.id = i.buyer_company_id
            LEFT JOIN contract ct ON ct.id = i.contract_id
            WHERE %(cid)s IN (i.seller_company_id, i.buyer_company_id)
            ORDER BY i.invoice_number
            """,
            {"cid": company_id},
        )
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        if pdf_stems is not None:
            for row in rows:
                row["has_pdf"] = row["invoice_number"] in pdf_stems
        return rows


# --- Pairs (PRD 2a, R19..R21) -------------------------------------------------
# A pair is one A-to-B relationship. These are the only reads and writes on
# the pair table. Every write is guarded by "the caller's company is on this
# pair", inside the SQL, so a wrong company id changes zero rows.

def list_pairs_for_company(company_id: str) -> list[dict]:
    """The company home screen (R21): its own pairs, each with counterparty,
    status, who invited, the contracts between the two, approvers per side,
    and the pair's switches. Nothing about any other company's pairs."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.status, p.accepted_at, p.auto_reply_status_inquiry,
                   inv.name AS invited_by, (p.invited_by_company_id = %s) AS invited_by_me,
                   o.id AS counterparty_id, o.name AS counterparty
            FROM pair p
            JOIN company inv ON inv.id = p.invited_by_company_id
            JOIN company o ON o.id = CASE WHEN p.company_a_id = %s THEN p.company_b_id ELSE p.company_a_id END
            WHERE %s IN (p.company_a_id, p.company_b_id)
            ORDER BY p.created_at
            """,
            (company_id, company_id, company_id),
        )
        cols = [c.name for c in cur.description]
        pairs = [dict(zip(cols, row)) for row in cur.fetchall()]
        for pair in pairs:
            cur.execute(
                """
                SELECT s.name AS seller, b.name AS buyer, ct.status, ct.effective_date, ct.expiry_date,
                       dp.max_rate, dp.auto_approve_rate, dp.period_budget
                FROM contract ct
                JOIN company s ON s.id = ct.seller_company_id
                JOIN company b ON b.id = ct.buyer_company_id
                LEFT JOIN discount_policy dp ON dp.contract_id = ct.id
                WHERE (ct.seller_company_id, ct.buyer_company_id) IN ((%s, %s), (%s, %s))
                ORDER BY ct.effective_date DESC
                """,
                (company_id, pair["counterparty_id"], pair["counterparty_id"], company_id),
            )
            ccols = [c.name for c in cur.description]
            pair["contracts"] = [dict(zip(ccols, r)) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT a.display_name, a.role, c.name AS company
                FROM approver a JOIN company c ON c.id = a.company_id
                WHERE a.company_id IN (%s, %s) AND (a.pair_id = %s OR a.pair_id IS NULL)
                ORDER BY c.name, a.role
                """,
                (company_id, pair["counterparty_id"], pair["id"]),
            )
            acols = [c.name for c in cur.description]
            pair["approvers"] = [dict(zip(acols, r)) for r in cur.fetchall()]
        return pairs


def invite_pair(my_company_id: str, counterparty_id: str) -> str | None:
    """A invites B (R19). Returns the pair id, or None if one already exists
    in either direction or the two ids are the same company."""
    if my_company_id == counterparty_id:
        return None
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pair (company_a_id, company_b_id, status, invited_by_company_id) "
            "VALUES (LEAST(%s::uuid, %s::uuid), GREATEST(%s::uuid, %s::uuid), 'invited', %s) "
            "ON CONFLICT (company_a_id, company_b_id) DO NOTHING RETURNING id",
            (my_company_id, counterparty_id, my_company_id, counterparty_id, my_company_id),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None


def accept_pair(pair_id: str, my_company_id: str) -> bool:
    """B accepts (R19). Only the side that did not send the invite can
    accept, and only while it is still an invite. Returns whether a row
    changed."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE pair SET status = 'active', accepted_at = now() "
            "WHERE id = %s AND status = 'invited' AND invited_by_company_id <> %s "
            "AND %s IN (company_a_id, company_b_id)",
            (pair_id, my_company_id, my_company_id),
        )
        return cur.rowcount == 1


def set_pair_auto_reply(pair_id: str, my_company_id: str, enabled: bool) -> bool:
    """The R5 switch. Either side of an active pair may flip it; it applies
    to replies sent from this instance. Returns whether a row changed."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE pair SET auto_reply_status_inquiry = %s "
            "WHERE id = %s AND status = 'active' AND %s IN (company_a_id, company_b_id)",
            (enabled, pair_id, my_company_id),
        )
        return cur.rowcount == 1


def company_cost_summary(company_id: str) -> dict:
    """What this company's agent has spent, over its own workflows only."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT workflow_id), count(*), COALESCE(SUM(estimated_cost_usd), 0) "
            "FROM llm_call_cost WHERE workflow_id IN (" + MY_WORKFLOWS_SQL + ")",
            {"cid": company_id},
        )
        workflows, calls, total_cost = cur.fetchone()
    return {"workflows": workflows, "calls": calls, "total_cost_usd": float(total_cost)}


def pair_settings_for_invoice(invoice_id: str) -> dict | None:
    """What the intake loop needs before replying about an invoice: is the
    pair active, and may the reply be sent rather than drafted."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.status, p.auto_reply_status_inquiry
            FROM invoice i
            JOIN pair p ON p.company_a_id = LEAST(i.seller_company_id, i.buyer_company_id)
                       AND p.company_b_id = GREATEST(i.seller_company_id, i.buyer_company_id)
            WHERE i.id = %s
            """,
            (invoice_id,),
        )
        row = cur.fetchone()
        return {"status": row[0], "auto_reply_status_inquiry": row[1]} if row else None
