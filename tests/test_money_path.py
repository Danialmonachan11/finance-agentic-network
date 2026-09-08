"""Offline tests for the money path (PRD R6..R9). No Postgres, no API key:
the DB is faked at the get_conn seam. Each test encodes a bug found in the
2026-09-07 review and states why the behaviour matters.

Run:  python -m unittest tests.test_money_path
"""

import sys
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.discount_logic import Contract, DiscountPolicy, EligibilityResult, check_eligibility

POLICY = DiscountPolicy(max_rate=0.15, period_budget=5000.0, auto_approve_rate=0.05)
ACTIVE = Contract(status="active", effective_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31))
AS_OF = date(2026, 6, 1)


class FakeCursor:
    """Records every execute(); answers fetchone() from a queue of rows."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_get_conn(cursor):
    @contextmanager
    def _conn():
        yield mock.Mock(cursor=lambda: cursor)
    return _conn


class RateBounds(unittest.TestCase):
    """Why: the policy never sets a floor, so a negative extracted rate
    passes every check as 'auto' and books a negative discount."""

    def test_zero_negative_and_over_100_percent_are_rejected(self):
        for rate in (0.0, -0.10, 1.5):
            r = check_eligibility(rate, ACTIVE, POLICY, 0, 1000, AS_OF)
            self.assertFalse(r.eligible, rate)
            self.assertEqual(r.approved_rate, 0.0)

    def test_normal_rate_still_auto(self):
        r = check_eligibility(0.05, ACTIVE, POLICY, 0, 1000, AS_OF)
        self.assertTrue(r.eligible and r.approval_level == "auto")


class ContractlessInvoice(unittest.TestCase):
    """Why: an invoice with no contract used to raise, which crashed the
    graph mid-run. It must come back as a rejection so it escalates."""

    def test_returns_rejection_not_exception(self):
        from src.tools import db_lookups
        cur = FakeCursor(rows=[("contract-1", 1000.0, AS_OF)])
        with mock.patch.object(db_lookups, "get_conn", fake_get_conn(cur)), \
             mock.patch.object(db_lookups, "get_contract_and_policy", return_value=None):
            r = db_lookups.evaluate_invoice_discount("inv-1", claimed_rate=0.05)
        self.assertFalse(r.eligible)
        self.assertEqual(r.approval_level, "rejected")


class ExecutionRevalidatesOwnRate(unittest.TestCase):
    """Why: revalidation used to read the newest proposal on the invoice,
    so approving an old 5% proposal could be checked against a sibling's
    30% claim (or vice versa). The approver decided on one row."""

    def test_revalidate_gets_this_proposals_rate(self):
        from src.tools import execution
        cur = FakeCursor(rows=[("inv-1", "proposed", 0.30)])
        seen = {}

        def fake_revalidate(invoice_id, claimed_rate):
            seen["args"] = (invoice_id, claimed_rate)
            return EligibilityResult(False, 0.0, "rejected", "stop here")

        with mock.patch.object(execution, "get_conn", fake_get_conn(cur)), \
             mock.patch.object(execution, "revalidate_eligibility", fake_revalidate), \
             mock.patch.object(execution, "log_audit"):
            with self.assertRaises(execution.ExecutionError):
                execution.execute_discount("prop-1", "Alex", "manager")
        self.assertEqual(seen["args"], ("inv-1", 0.30))


class EscalateScopedToWorkflow(unittest.TestCase):
    """Why: a grounded rejection used to flip every 'proposed' row on the
    invoice to 'rejected', killing sibling proposals from other workflows
    that a human might be reviewing right now."""

    def test_update_filters_on_workflow_id(self):
        from src.orchestration import nodes
        cur = FakeCursor(rows=[])
        state = {"intent": "discount_request", "eligibility_eligible": False,
                 "eligibility_reason": "budget", "invoice_id": "inv-1",
                 "workflow_id": "00000000-0000-0000-0000-000000000001"}
        with mock.patch.object(nodes, "get_conn", fake_get_conn(cur)), \
             mock.patch.object(nodes, "log_audit"), \
             mock.patch.object(nodes, "publish_event"):
            nodes.escalate(state)
        sql, params = cur.calls[0]
        self.assertIn("workflow_id = %s", sql)
        self.assertEqual(params, ("inv-1", state["workflow_id"]))


if __name__ == "__main__":
    unittest.main()
