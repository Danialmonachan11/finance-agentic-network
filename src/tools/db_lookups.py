"""Read-tier tools (docs/reference/architecture.md §3.9 tool categories): resolve a
claim against the system of record. These are the *only* place an agent's
"our contract gives us X%" claim gets checked against real data — see §3.4.
No LLM involvement in this file; it's plain SQL.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn
from src.tools.discount_logic import Contract, DiscountPolicy, EligibilityResult, check_eligibility


def get_contract_and_policy(invoice_id: str) -> tuple[Contract, DiscountPolicy] | None:
    """get_contract() + get_discount_policy() combined, keyed off the invoice
    since that's what a real workflow has in hand at this step."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.status, c.effective_date, c.expiry_date,
                   p.max_rate, p.period_budget, p.auto_approve_rate
            FROM invoice i
            JOIN contract c ON c.id = i.contract_id
            JOIN discount_policy p ON p.contract_id = c.id
            WHERE i.id = %s
            """,
            (invoice_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        status, eff, exp, max_rate, budget, auto_rate = row
        return (
            Contract(status=status, effective_date=eff, expiry_date=exp),
            DiscountPolicy(max_rate=float(max_rate), period_budget=float(budget), auto_approve_rate=float(auto_rate)),
        )


def get_period_used(contract_id: str, period_days: int = 90) -> float:
    """get_discount_history(): sum of already-approved discounts on this
    contract within the trailing period. Only 'approved' or 'executed'
    proposals count — a rejected/pending one never consumed budget."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(i.amount * dp.approved_rate), 0)
            FROM discount_proposal dp
            JOIN invoice i ON i.id = dp.invoice_id
            WHERE i.contract_id = %s
              AND dp.status IN ('approved', 'executed')
              AND dp.decided_at >= now() - (%s || ' days')::interval
            """,
            (contract_id, period_days),
        )
        return float(cur.fetchone()[0])


def get_invoice_parties(invoice_id: str) -> tuple[str, str]:
    """Seller/buyer company names for an invoice — what find_network_cycle
    (Neo4j) needs to check whether this trade sits inside a trading loop."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT seller.name, buyer.name
            FROM invoice i
            JOIN company seller ON seller.id = i.seller_company_id
            JOIN company buyer ON buyer.id = i.buyer_company_id
            WHERE i.id = %s
            """,
            (invoice_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"no such invoice: {invoice_id}")
        return row[0], row[1]


def evaluate_invoice_discount(invoice_id: str, claimed_rate: float | None = None) -> EligibilityResult:
    """calculate_discount() + check_authorization() combined: the full
    grounded-decision flow from §3.4, steps 2-5, run against real Postgres
    rows instead of a claim the agent just asserts.

    claimed_rate is the thing actually being grounded — pass the live
    extraction (state["extracted_claim_rate"] in the orchestration graph)
    for a real inbound claim. It falls back to the latest discount_proposal
    row's rate ONLY when claimed_rate is omitted, which exists solely so
    this module's own demo() can exercise the grounding logic standalone
    against seeded data, independent of the LLM extraction step."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT contract_id, amount, issued_date FROM invoice WHERE id = %s", (invoice_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"no such invoice: {invoice_id}")
        contract_id, amount, issued_date = row

        if claimed_rate is None:
            cur.execute(
                "SELECT claimed_rate FROM discount_proposal WHERE invoice_id = %s ORDER BY created_at DESC LIMIT 1",
                (invoice_id,),
            )
            proposal_row = cur.fetchone()
            if proposal_row is None:
                raise ValueError(f"no discount_proposal found for invoice: {invoice_id}, and no claimed_rate was given")
            claimed_rate = float(proposal_row[0])

    resolved = get_contract_and_policy(invoice_id)
    if resolved is None:
        return EligibilityResult(False, 0.0, "rejected", "invoice has no linked contract or discount policy")
    contract, policy = resolved

    period_used = get_period_used(str(contract_id))

    return check_eligibility(
        claimed_rate=claimed_rate,
        contract=contract,
        policy=policy,
        period_used=period_used,
        invoice_amount=float(amount),
        as_of=issued_date,
    )


def demo() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, invoice_number FROM invoice ORDER BY invoice_number")
        invoices = cur.fetchall()

    assert len(invoices) == 4, f"expected 4 seeded invoices, found {len(invoices)} — run `python -m data.seed.seed` first"

    results = {}
    for invoice_id, invoice_number in invoices:
        results[invoice_number] = evaluate_invoice_discount(str(invoice_id))
        print(f"{invoice_number}: {results[invoice_number]}")

    assert results["INV-1001"].eligible and results["INV-1001"].approval_level == "auto"
    assert results["INV-1002"].eligible and results["INV-1002"].approval_level == "manager"
    assert results["INV-2001"].eligible and results["INV-2001"].approval_level == "manager"
    assert not results["INV-3001"].eligible, "expired contract must be rejected"

    print("db_lookups.demo(): all checks passed against live Postgres data")


if __name__ == "__main__":
    demo()
