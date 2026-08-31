"""Deterministic policy gate (docs/architecture.md §3.5/§3.6): the harness
layer that sits between a proposal and execution. Nothing here trusts state
that another component already computed — every check re-derives from
Postgres, because a proposal record could be stale (contract changed since
it was proposed) or, in an adversarial framing, tampered with. This is the
zero-trust point the JD names explicitly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tools.db_lookups import evaluate_invoice_discount
from src.tools.discount_logic import EligibilityResult

# Segregation of duties: an approver's role must be at least as senior as
# the approval level the discount requires. A manager cannot self-approve a
# CFO-level discount by relabeling it — the rank check is structural, not a
# prompt instruction an agent could talk its way around.
ROLE_RANK = {"auto": 0, "manager": 1, "cfo": 2}


class PolicyViolation(Exception):
    pass


def revalidate_eligibility(invoice_id: str) -> EligibilityResult:
    """Re-derive eligibility from Postgres right now, ignoring whatever a
    prior workflow run (or an agent's claim) said. This is what makes
    execution safe even if the proposal is hours old."""
    return evaluate_invoice_discount(invoice_id)


def authorize_approval(approval_level: str, approver_role: str) -> None:
    if approver_role not in ROLE_RANK:
        raise PolicyViolation(f"unknown approver role: {approver_role!r}")
    if ROLE_RANK[approver_role] < ROLE_RANK[approval_level]:
        raise PolicyViolation(
            f"approver role '{approver_role}' cannot approve a '{approval_level}'-level discount "
            f"(requires role rank >= {ROLE_RANK[approval_level]}, got {ROLE_RANK[approver_role]})"
        )


def demo() -> None:
    # authorize_approval: rank enforcement, independent of any invoice
    authorize_approval("manager", "manager")  # ok: exact match
    authorize_approval("manager", "cfo")       # ok: cfo outranks manager

    try:
        authorize_approval("cfo", "manager")
        raise AssertionError("manager should not be able to approve a cfo-level discount")
    except PolicyViolation:
        pass

    try:
        authorize_approval("manager", "auto")
        raise AssertionError("auto should not be able to approve a manager-level discount")
    except PolicyViolation:
        pass

    print("policy_gate.demo(): role-rank authorization checks passed")


if __name__ == "__main__":
    demo()
