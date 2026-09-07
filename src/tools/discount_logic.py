"""Deterministic discount eligibility + authorization logic.

This is the "grounded decision making" core from docs/reference/architecture.md §3.4:
pure functions, no LLM involved, no DB access. db_lookups.py resolves a
customer's contract/policy from Postgres; this module decides what to do
with them. Keeping this pure makes it independently testable and keeps the
harness (src/guardrails/) able to re-validate any LLM-proposed discount
against the exact same function the LLM's tool call used.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DiscountPolicy:
    max_rate: float            # e.g. 0.10 = 10%
    period_budget: float       # max discount $ in the period
    auto_approve_rate: float   # <= this: Tier 3 autonomous, no human needed


@dataclass(frozen=True)
class Contract:
    status: str                # 'active' | 'expired' | 'terminated'
    effective_date: date
    expiry_date: date


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    approved_rate: float       # clamped to max_rate; 0 if ineligible
    approval_level: str        # 'auto' | 'manager' | 'cfo' | 'rejected'
    reason: str


def check_eligibility(
    claimed_rate: float,
    contract: Contract,
    policy: DiscountPolicy,
    period_used: float,        # $ already discounted this period, from Postgres
    invoice_amount: float,
    as_of: date,
) -> EligibilityResult:
    """The step-by-step grounded check from §3.4: contract active, within
    rate ceiling, within remaining budget, then map to an approval level.
    """
    if contract.status != "active":
        return EligibilityResult(False, 0.0, "rejected", f"contract status is '{contract.status}', not active")

    if not (contract.effective_date <= as_of <= contract.expiry_date):
        return EligibilityResult(False, 0.0, "rejected", "contract not in effect on invoice date")

    approved_rate = min(claimed_rate, policy.max_rate)
    if approved_rate < claimed_rate:
        reason_prefix = f"claimed {claimed_rate:.2%} exceeds contract max {policy.max_rate:.2%}, clamped; "
    else:
        reason_prefix = ""

    discount_amount = invoice_amount * approved_rate
    if period_used + discount_amount > policy.period_budget:
        remaining = max(policy.period_budget - period_used, 0)
        return EligibilityResult(
            False, 0.0, "rejected",
            f"{reason_prefix}period budget exceeded: remaining ${remaining:.2f}, requested ${discount_amount:.2f}",
        )

    if approved_rate <= policy.auto_approve_rate:
        level = "auto"
    elif approved_rate <= policy.max_rate:
        level = "manager" if approved_rate <= 0.15 else "cfo"
    else:
        level = "cfo"

    return EligibilityResult(True, approved_rate, level, reason_prefix + "within policy" if reason_prefix else "within policy")


def demo() -> None:
    policy = DiscountPolicy(max_rate=0.15, period_budget=5000.0, auto_approve_rate=0.05)
    active_contract = Contract(status="active", effective_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31))

    # 1. Within auto-approve range -> auto
    r = check_eligibility(0.05, active_contract, policy, period_used=0, invoice_amount=1000, as_of=date(2026, 6, 1))
    assert r.eligible and r.approval_level == "auto", r

    # 2. Above auto but within max -> manager
    r = check_eligibility(0.10, active_contract, policy, period_used=0, invoice_amount=1000, as_of=date(2026, 6, 1))
    assert r.eligible and r.approval_level == "manager", r

    # 3. Claimed rate exceeds contract max -> clamped, still eligible
    r = check_eligibility(0.30, active_contract, policy, period_used=0, invoice_amount=1000, as_of=date(2026, 6, 1))
    assert r.eligible and r.approved_rate == 0.15, r

    # 4. Expired contract -> rejected regardless of rate
    expired = Contract(status="expired", effective_date=date(2024, 1, 1), expiry_date=date(2024, 12, 31))
    r = check_eligibility(0.05, expired, policy, period_used=0, invoice_amount=1000, as_of=date(2026, 6, 1))
    assert not r.eligible and r.approval_level == "rejected", r

    # 5. Budget already exhausted this period -> rejected (discount = 1000*0.05 = 50, pushes past the 5000 cap)
    r = check_eligibility(0.05, active_contract, policy, period_used=4980, invoice_amount=1000, as_of=date(2026, 6, 1))
    assert not r.eligible, r

    print("discount_logic.demo(): all checks passed")


if __name__ == "__main__":
    demo()
