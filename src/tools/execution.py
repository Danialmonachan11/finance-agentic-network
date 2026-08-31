"""Execution-tier tool (docs/architecture.md §3.9 tool categories). This is
the ONLY function in the codebase that moves a discount_proposal to
'executed' — every other code path (the orchestration graph, gmail_intake)
stops at 'proposed'. Calling this always re-validates from scratch via
policy_gate: a stale or previously-eligible proposal is checked again, not
trusted, before anything is marked executed.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.guardrails.audit import log_audit
from src.guardrails.policy_gate import PolicyViolation, authorize_approval, revalidate_eligibility
from src.ontology.db import get_conn
from src.orchestration.events import publish_event


class ExecutionError(Exception):
    pass


def execute_discount(proposal_id: str, approver_name: str, approver_role: str) -> dict:
    """Takes the SPECIFIC proposal being approved, not an invoice_id — this
    used to look up 'whatever the latest proposal for this invoice is
    right now', which meant an approve click could silently target a
    different, newer proposal than the one a human actually reviewed on
    screen (found live: a background test run created a newer proposal
    between page render and click; the safety net correctly refused rather
    than executing the wrong one, but the real fix is not letting that
    ambiguity exist in the first place — pin to the exact row reviewed)."""
    workflow_id = uuid.uuid4()  # a fresh workflow_id scopes this execution's own audit trail

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT invoice_id, status, claimed_rate FROM discount_proposal WHERE id = %s",
            (proposal_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ExecutionError(f"no such discount_proposal: {proposal_id}")
        invoice_id, status, claimed_rate = str(row[0]), row[1], row[2]

        if status == "executed":
            log_audit(workflow_id, step="execute_discount", agent="execution_tool",
                       decision="no_op_already_executed", reason=f"proposal {proposal_id} already executed")
            return {"proposal_id": str(proposal_id), "status": "executed", "already_executed": True}

        if status != "proposed":
            raise ExecutionError(f"proposal {proposal_id} is in status '{status}', not 'proposed' — cannot execute")

    # Re-derive from Postgres now — never trust the proposal row's own
    # approval_level/status as sufficient, even though it was set correctly
    # at propose time. See policy_gate module docstring.
    eligibility = revalidate_eligibility(invoice_id)
    if not eligibility.eligible:
        log_audit(workflow_id, step="execute_discount", agent="execution_tool",
                   decision="blocked", reason=f"revalidation failed: {eligibility.reason}")
        raise ExecutionError(f"cannot execute: revalidation failed — {eligibility.reason}")

    try:
        authorize_approval(eligibility.approval_level, approver_role)
    except PolicyViolation as e:
        log_audit(workflow_id, step="execute_discount", agent="execution_tool",
                   decision="blocked", reason=str(e))
        raise ExecutionError(str(e)) from e

    with get_conn() as conn, conn.cursor() as cur:
        # Conditioned on status = 'proposed', not just id: this is the fix
        # for the race between the SELECT above and this UPDATE. Two
        # concurrent approve calls can both pass every check above with the
        # same pre-image; only one of them can win this atomic
        # check-and-set. Without the WHERE clause both would silently
        # "succeed" — harmless today because the final row state is
        # idempotent, but the exact bug that becomes a real double-spend
        # the day an actual side effect (a payment call, a ledger row)
        # gets attached to this step.
        cur.execute(
            "UPDATE discount_proposal SET status = 'executed', approved_rate = %s, "
            "approved_by = %s, decided_at = now() WHERE id = %s AND status = 'proposed'",
            (eligibility.approved_rate, approver_name, proposal_id),
        )
        if cur.rowcount == 0:
            # Lost the race: something else changed this row between our
            # SELECT and this UPDATE. Re-check rather than assume — if it's
            # now 'executed', that's a safe no-op (the other caller won,
            # not us); anything else is a real conflict to surface.
            cur.execute("SELECT status FROM discount_proposal WHERE id = %s", (proposal_id,))
            current_status = cur.fetchone()[0]
            log_audit(workflow_id, step="execute_discount", agent="execution_tool",
                       decision="race_lost", reason=f"proposal {proposal_id} was '{current_status}' by the time of the conditional update")
            if current_status == "executed":
                return {"proposal_id": str(proposal_id), "status": "executed", "already_executed": True}
            raise ExecutionError(f"proposal {proposal_id} changed to '{current_status}' concurrently — not executed")

    log_audit(
        workflow_id, step="execute_discount", agent="execution_tool",
        decision="executed", reason=f"approved by {approver_name} ({approver_role})",
        tool_calls={"approved_rate": eligibility.approved_rate, "approval_level": eligibility.approval_level},
    )
    publish_event(workflow_id, "workflow.executed", {
        "invoice_id": invoice_id, "approved_rate": eligibility.approved_rate,
        "approved_by": approver_name, "approver_role": approver_role,
    })
    return {"proposal_id": str(proposal_id), "status": "executed", "approved_rate": eligibility.approved_rate,
            "already_executed": False}


def demo() -> None:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from src.ontology.db import get_conn as _get_conn

    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM invoice WHERE invoice_number = 'INV-1002'")
        inv1002_id = str(cur.fetchone()[0])
        cur.execute("SELECT id FROM invoice WHERE invoice_number = 'INV-3001'")
        inv3001_id = str(cur.fetchone()[0])
        # reset any prior demo run's state so this is repeatable, and grab
        # THE specific proposal_id each check operates on — execute_discount
        # takes a proposal_id now, not an invoice_id (see its docstring).
        cur.execute("UPDATE discount_proposal SET status = 'proposed', approved_rate = NULL, "
                     "approved_by = NULL, decided_at = NULL WHERE invoice_id IN (%s, %s)",
                     (inv1002_id, inv3001_id))
        cur.execute("SELECT id FROM discount_proposal WHERE invoice_id = %s ORDER BY created_at DESC LIMIT 1", (inv1002_id,))
        inv1002_proposal_id = str(cur.fetchone()[0])
        cur.execute("SELECT id FROM discount_proposal WHERE invoice_id = %s ORDER BY created_at DESC LIMIT 1", (inv3001_id,))
        inv3001_proposal_id = str(cur.fetchone()[0])

    # 1. Insufficient authority: a manager-level discount, approver is only 'auto' rank -> blocked
    try:
        execute_discount(inv1002_proposal_id, approver_name="Alex", approver_role="auto")
        raise AssertionError("expected ExecutionError for insufficient approver role")
    except ExecutionError as e:
        print(f"  [expected] blocked insufficient authority: {e}")

    # 2. Sufficient authority -> executes
    result = execute_discount(inv1002_proposal_id, approver_name="Jordan (Manager)", approver_role="manager")
    assert result["status"] == "executed" and not result["already_executed"], result
    print(f"  executed: {result}")

    # 3. Idempotency: re-executing the same proposal is a safe no-op, not a double-apply
    result2 = execute_discount(inv1002_proposal_id, approver_name="Jordan (Manager)", approver_role="manager")
    assert result2["already_executed"] is True, result2
    print(f"  re-execute is a no-op: {result2}")

    # 4. Defense in depth: even with a manager's full authority, an invoice whose
    #    contract is expired (INV-3001) still gets blocked — because execute_discount
    #    re-derives eligibility itself rather than trusting any prior state.
    try:
        execute_discount(inv3001_proposal_id, approver_name="Jordan (Manager)", approver_role="cfo")
        raise AssertionError("expected ExecutionError for expired contract, regardless of approver authority")
    except ExecutionError as e:
        print(f"  [expected] blocked on revalidation despite full authority: {e}")

    print("execution.demo(): authorization, idempotency, and revalidation checks all passed")


if __name__ == "__main__":
    demo()
