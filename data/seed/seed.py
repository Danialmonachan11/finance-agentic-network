"""Generate a small NETWORK of companies transacting with each other, and
load it into Postgres. Run from repo root: python -m data.seed.seed

Deliberately a triangle, not a hub-and-spoke: Kessler sells to Nordwind,
Nordwind sells to Aurea, Aurea sells to Kessler. Every company is a seller
on one leg and a buyer on another — there is no fixed "us" the network
revolves around (that was the bug in the original single-customer-table
design; see BRAIN.md decisions log, 2026-08-24). This also gives Neo4j a
genuine multi-hop structure to traverse (a cycle), instead of one flat
Customer->Contract->Policy chain.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn
from src.tools.discount_logic import Contract, DiscountPolicy, check_eligibility

COMPANIES = [
    ("Kessler Manufacturing", "kessler-mfg.com"),      # 0
    ("Nordwind Logistik GmbH", "nordwind-logistik.de"),  # 1
    ("Aurea Retail S.A.", "aurea-retail.es"),           # 2
]

# (seller_idx, buyer_idx, status, effective, expiry, max_rate, period_budget, auto_approve_rate)
CONTRACTS = [
    (0, 1, "active", "2026-01-01", "2026-12-31", 0.15, 5000.00, 0.05),   # Kessler -> Nordwind
    (1, 2, "active", "2026-01-01", "2026-12-31", 0.10, 2000.00, 0.05),   # Nordwind -> Aurea
    (2, 0, "expired", "2024-01-01", "2024-12-31", 0.20, 10000.00, 0.05),  # Aurea -> Kessler (lapsed)
]

# (contract_idx, invoice_number, amount, issued, due, claimed_rate, justification)
INVOICES = [
    (0, "INV-1001", 4200.00, "2026-06-01", "2026-07-01", 0.05,
     "Per our standing agreement we apply the standard 5% volume discount."),
    (0, "INV-1002", 9800.00, "2026-06-10", "2026-07-10", 0.12,
     "Our contract gives us 12% for this order given the order size."),
    (1, "INV-2001", 1500.00, "2026-06-05", "2026-07-05", 0.10,
     "Requesting the full 10% contract rate on this invoice."),
    (2, "INV-3001", 3000.00, "2026-06-15", "2026-07-15", 0.15,
     "Claiming our usual 15% discount."),  # contract expired -> should be rejected
]


def seed() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE audit_log, workflow_event, processed_email, discount_proposal, invoice_line, invoice, discount_policy, contract, company RESTART IDENTITY CASCADE")

        company_ids = []
        for name, domain in COMPANIES:
            cur.execute(
                "INSERT INTO company (name, email_domain) VALUES (%s, %s) RETURNING id",
                (name, domain),
            )
            company_ids.append(cur.fetchone()[0])

        contract_ids = []
        for seller_idx, buyer_idx, status, eff, exp, max_rate, budget, auto_rate in CONTRACTS:
            cur.execute(
                "INSERT INTO contract (seller_company_id, buyer_company_id, status, effective_date, expiry_date) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (company_ids[seller_idx], company_ids[buyer_idx], status, eff, exp),
            )
            contract_id = cur.fetchone()[0]
            contract_ids.append(contract_id)

            cur.execute(
                "INSERT INTO discount_policy (contract_id, max_rate, period_budget, auto_approve_rate) "
                "VALUES (%s, %s, %s, %s)",
                (contract_id, max_rate, budget, auto_rate),
            )

        for contract_idx, inv_num, amount, issued, due, claimed_rate, justification in INVOICES:
            seller_idx, buyer_idx = CONTRACTS[contract_idx][0], CONTRACTS[contract_idx][1]
            cur.execute(
                "INSERT INTO invoice (seller_company_id, buyer_company_id, contract_id, invoice_number, amount, issued_date, due_date) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (company_ids[seller_idx], company_ids[buyer_idx], contract_ids[contract_idx], inv_num, amount, issued, due),
            )
            invoice_id = cur.fetchone()[0]

            # Run the SAME deterministic grounding check the live agents
            # use (src/tools/discount_logic.check_eligibility) before
            # deciding this seed row's initial status — seed data must
            # never claim a status the pipeline itself wouldn't produce.
            # Previously every invoice was hardcoded 'proposed' regardless
            # of eligibility, which meant INV-3001 (expired contract) sat
            # in the pending-approval queue even though ground_decision
            # would reject it instantly — found live when a user tried to
            # approve it. That was a seeding shortcut bypassing the exact
            # agent check meant to catch this, not a gap in the agents.
            _, _, contract_status, eff, exp, max_rate, budget, auto_rate = CONTRACTS[contract_idx]
            eligibility = check_eligibility(
                claimed_rate=claimed_rate,
                contract=Contract(status=contract_status, effective_date=date.fromisoformat(eff), expiry_date=date.fromisoformat(exp)),
                policy=DiscountPolicy(max_rate=max_rate, period_budget=budget, auto_approve_rate=auto_rate),
                period_used=0.0,
                invoice_amount=amount,
                as_of=date.fromisoformat(issued),
            )
            initial_status = "proposed" if eligibility.eligible else "rejected"
            # approval_level is CHECK-constrained to auto/manager/cfo — an
            # ineligible claim has no meaningful approval level (nobody
            # was ever going to approve it), so fall back to 'manager' as
            # a neutral placeholder rather than eligibility's own
            # 'rejected' value, which the column would reject outright.
            approval_level = eligibility.approval_level if eligibility.eligible else "manager"

            cur.execute(
                "INSERT INTO discount_proposal (invoice_id, claimed_rate, approval_level, status, justification) "
                "VALUES (%s, %s, %s, %s, %s)",
                (invoice_id, claimed_rate, approval_level, initial_status, justification),
            )

    print(f"seeded {len(company_ids)} companies (network: "
          f"{COMPANIES[0][0]} -> {COMPANIES[1][0]} -> {COMPANIES[2][0]} -> {COMPANIES[0][0]}), "
          f"{len(contract_ids)} contracts, {len(INVOICES)} invoices")


def demo() -> None:
    seed()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM company")
        assert cur.fetchone()[0] == len(COMPANIES)
        cur.execute("SELECT count(*) FROM invoice")
        assert cur.fetchone()[0] == len(INVOICES)
        # Not every invoice grounds as eligible (INV-3001's contract is
        # expired on purpose) — seed status must reflect that, not claim
        # every invoice is pending approval regardless of eligibility.
        cur.execute("SELECT count(*) FROM discount_proposal WHERE status = 'proposed'")
        assert cur.fetchone()[0] == len(INVOICES) - 1, "expected all but INV-3001 (expired contract) to seed as 'proposed'"
        cur.execute("SELECT count(*) FROM discount_proposal WHERE status = 'rejected'")
        assert cur.fetchone()[0] == 1, "expected exactly INV-3001 to seed as 'rejected'"

        # Confirm the network property: every company appears as BOTH a
        # seller and a buyer somewhere — this is what makes it a network,
        # not a hub-and-spoke.
        cur.execute("SELECT DISTINCT seller_company_id FROM invoice")
        sellers = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT DISTINCT buyer_company_id FROM invoice")
        buyers = {r[0] for r in cur.fetchall()}
        assert sellers == buyers, f"expected every company to be both seller and buyer somewhere: sellers={sellers} buyers={buyers}"

    print("seed.demo(): row counts verified, network property confirmed (every company is both seller and buyer)")


if __name__ == "__main__":
    demo()
