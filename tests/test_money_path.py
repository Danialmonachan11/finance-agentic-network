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
        cur = FakeCursor(rows=[("inv-1", "proposed", 0.30, "co-a", "active")])
        seen = {}

        def fake_revalidate(invoice_id, claimed_rate):
            seen["args"] = (invoice_id, claimed_rate)
            return EligibilityResult(False, 0.0, "rejected", "stop here")

        with mock.patch.object(execution, "get_conn", fake_get_conn(cur)), \
             mock.patch.object(execution, "revalidate_eligibility", fake_revalidate), \
             mock.patch.object(execution, "log_audit"):
            with self.assertRaises(execution.ExecutionError):
                execution.execute_discount("prop-1", "Alex", "manager", approver_company_id="co-a")
        self.assertEqual(seen["args"], ("inv-1", 0.30))


class ExecutionStaysInsideThePair(unittest.TestCase):
    """Why: a discount is the seller's money. Only the seller's own approver
    may release it (R8), and only inside an active pair with this buyer
    (R19). Both checks run before any eligibility work."""

    def _run(self, row, company):
        from src.tools import execution
        cur = FakeCursor(rows=[row])
        with mock.patch.object(execution, "get_conn", fake_get_conn(cur)), \
             mock.patch.object(execution, "revalidate_eligibility") as reval, \
             mock.patch.object(execution, "log_audit"):
            with self.assertRaises(execution.ExecutionError) as ctx:
                execution.execute_discount("prop-1", "Alex", "cfo", approver_company_id=company)
        reval.assert_not_called()
        return str(ctx.exception)

    def test_other_companys_approver_is_refused(self):
        msg = self._run(("inv-1", "proposed", 0.05, "co-a", "active"), company="co-b")
        self.assertIn("different company", msg)

    def test_no_active_pair_is_refused(self):
        msg = self._run(("inv-1", "proposed", 0.05, "co-a", "invited"), company="co-a")
        self.assertIn("no active pair", msg)


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


class StatusInquiryPath(unittest.TestCase):
    """Why: the status path is read-only and must stay that way. Routing
    sends only two intents to autonomous nodes; a bank change never gets
    one. The resolver matches on counterparty plus reference or amount, and
    an ambiguous match is a human's problem, not a guess (R2, R3)."""

    def test_routing(self):
        from src.orchestration.nodes import route_after_triage
        self.assertEqual(route_after_triage({"intent": "status_inquiry"}), "answer_status")
        self.assertEqual(route_after_triage({"intent": "discount_request"}), "extract_claim")
        for intent in ("bank_change", "other", "anything-else"):
            self.assertEqual(route_after_triage({"intent": intent}), "escalate", intent)

    def test_extract_references(self):
        from decimal import Decimal
        from src.tools.resolver import extract_references, sender_domain
        refs = extract_references("Re INV-1001 / inv-1002, EUR 4,200.00 due 2026-07-01, 10% off, 1.234,56")
        self.assertEqual(refs.invoice_numbers, ("INV-1001", "INV-1002"))
        self.assertEqual(refs.amounts, (Decimal("4200.00"), Decimal("1234.56")))
        self.assertEqual(sender_domain("Anna <anna@Nordwind-Logistik.de>"), "nordwind-logistik.de")

    def test_ambiguous_match_is_none(self):
        from src.tools import resolver
        two_by_amount = [("id1", "INV-1", False), ("id2", "INV-2", False)]
        cur = FakeCursor(rows=[])
        cur.fetchall = lambda: two_by_amount
        refs = resolver.References((), (resolver.Decimal("10.00"),))
        with mock.patch.object(resolver, "get_conn", fake_get_conn(cur)):
            self.assertIsNone(resolver.find_invoice("x.example", refs))
        self.assertIsNone(resolver.find_invoice("", refs))

    def test_answer_status_states_only_row_facts(self):
        from src.orchestration import nodes
        facts = {"invoice_number": "INV-1001", "amount": 4200.0, "currency": "EUR",
                 "status": "received", "due_date": "2026-07-01", "issued_date": "2026-06-01"}
        fake_llm = mock.Mock()
        fake_llm.invoke.return_value = mock.Mock(content="Invoice INV-1001 was received; due 2026-07-01.")
        state = {"workflow_id": "00000000-0000-0000-0000-000000000002", "invoice_id": "inv-1"}
        with mock.patch.object(nodes, "get_invoice_status", return_value=facts), \
             mock.patch.object(nodes, "guard_llm_call"), \
             mock.patch.object(nodes, "get_llm", return_value=fake_llm), \
             mock.patch.object(nodes, "log_llm_cost"), mock.patch.object(nodes, "log_audit"), \
             mock.patch.object(nodes, "publish_event"):
            out = nodes.answer_status(state)
        self.assertEqual(out["proposal_status"], "status_answered")
        prompt = fake_llm.invoke.call_args.args[0]
        self.assertIn("received", prompt)
        self.assertIn("do not add or guess", prompt)


class ReplyDeliveryGate(unittest.TestCase):
    """Why: shadow mode is the rollout promise (R5). Only a status reply on
    an active pair with the switch on is sent. Everything else, including
    every discount reply, is a draft a human reads first."""

    def _deliver(self, status, settings):
        from src.ingestion import gmail_intake
        state = {"invoice_id": "inv-1", "proposal_status": status, "draft_response": "hi"}
        email = {"sender": "a@b.example", "subject": "s", "threadId": "t"}
        with mock.patch.object(gmail_intake, "pair_settings_for_invoice", return_value=settings), \
             mock.patch.object(gmail_intake, "send_gmail_message") as send, \
             mock.patch.object(gmail_intake, "create_gmail_draft") as draft:
            result = gmail_intake.deliver_reply(state, email)
        return result, send.called, draft.called

    def test_status_reply_on_enabled_active_pair_is_sent(self):
        self.assertEqual(self._deliver("status_answered", {"status": "active", "auto_reply_status_inquiry": True}),
                         ("sent", True, False))

    def test_everything_else_is_a_draft(self):
        cases = [
            ("status_answered", {"status": "active", "auto_reply_status_inquiry": False}),
            ("status_answered", {"status": "invited", "auto_reply_status_inquiry": True}),
            ("status_answered", None),
            ("proposed", {"status": "active", "auto_reply_status_inquiry": True}),
            ("auto_executed", {"status": "active", "auto_reply_status_inquiry": True}),
        ]
        for status, settings in cases:
            self.assertEqual(self._deliver(status, settings), ("drafted", False, True), (status, settings))


class WorkflowCaps(unittest.TestCase):
    """Why: a runaway loop does not fail, it keeps calling the model (R16).
    The cap is checked in code before every call and raises; the graph
    turns that into a human escalation. Numbers come from the cost table
    every call already writes to."""

    def _guard(self, calls, spend, today):
        from src.guardrails import caps
        cur = FakeCursor(rows=[(calls, spend, today)])
        with mock.patch.object(caps, "get_conn", fake_get_conn(cur)):
            caps.guard_llm_call("wf-1", "extract_claim")

    def test_under_every_cap_passes(self):
        self._guard(2, 0.01, 0.5)

    def test_each_cap_raises_with_its_name(self):
        from src.guardrails import caps
        for args, name in (((caps.WORKFLOW_MAX_LLM_CALLS, 0.0, 0.0), "llm_calls"),
                           ((0, caps.WORKFLOW_MAX_SPEND_EUR * caps.USD_PER_EUR, 0.0), "workflow_spend_eur"),
                           ((0, 0.0, caps.DAILY_MAX_SPEND_EUR * caps.USD_PER_EUR), "daily_spend_eur")):
            with self.assertRaises(caps.CapExceeded) as ctx:
                self._guard(*args)
            self.assertEqual(ctx.exception.cap, name)

    def test_every_model_call_in_the_graph_is_guarded(self):
        import re
        src = Path("src/orchestration/nodes.py").read_text(encoding="utf-8")
        # every node that calls a helper or a model must guard first; the two
        # read helpers are called only from guarded nodes and from evals
        for name in ("classify_intent(", "extract_claim_rate(", "llm = get_llm("):
            for m in re.finditer(re.escape(name), src):
                if src[: m.start()].rstrip().endswith("def " + name[:-1]):
                    continue
                if name != "llm = get_llm(" and "def " in src[m.start() - 5: m.start()]:
                    continue
                block = src[: m.start()]
                fn_start = block.rfind("\ndef ")
                fn_name = block[fn_start + 5: block.find("(", fn_start)]
                if fn_name in ("classify_intent", "extract_claim_rate"):
                    continue
                self.assertIn("guard_llm_call(", block[fn_start:], f"model call in {fn_name} without a cap check")


class ToolAllowlist(unittest.TestCase):
    """Why: the only thing that stops a tricked model from moving money is
    that it was never given the tool (R17). No node binds tools today, and
    the allowlist for every model-backed agent is empty. Binding one later
    must change this test on purpose."""

    def test_no_tools_bound_anywhere(self):
        hits = [p for p in Path("src").rglob("*.py") if "bind_tools(" in p.read_text(encoding="utf-8")]
        self.assertEqual(hits, [])

    def test_allowlist_is_empty_and_execution_is_never_a_tool(self):
        from src.guardrails import tool_allowlist as ta
        self.assertTrue(all(v == () for v in ta.TOOLS_BY_AGENT.values()))
        self.assertIn("execute_discount", ta.NEVER_A_TOOL)
        with self.assertRaises(ta.ToolNotAllowed):
            ta.tools_for("response_agent", ("execute_discount",))
        with self.assertRaises(ta.ToolNotAllowed):
            ta.tools_for("nobody", ())


if __name__ == "__main__":
    unittest.main()
