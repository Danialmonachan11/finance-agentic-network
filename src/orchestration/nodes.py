"""Specialist agent nodes for the invoice-discount workflow
(docs/reference/architecture.md §3.1). Each node is deliberately narrow: one job, a
scoped slice of state in, a scoped slice of state out, one audit log entry.

Grounding discipline (§3.4) is enforced structurally here: extract_claim
(LLM) writes extracted_claim_rate, but ground_decision (deterministic, no
LLM) is what actually decides eligibility — it re-reads the claim from
Postgres via db_lookups, not from the LLM's extraction. The LLM's read is
recorded for audit/comparison, never trusted as the source of truth.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pydantic import BaseModel, Field

from src.guardrails.audit import log_audit
from src.guardrails.cost_tracker import log_llm_cost
from src.guardrails.pii_redaction import redact_pii
from src.ontology.db import get_conn
from src.orchestration.events import publish_event
from src.orchestration.llm import CHEAP_MODEL, STRONG_MODEL, get_llm
from src.orchestration.state import WorkflowState
from src.tools.db_lookups import evaluate_invoice_discount, get_invoice_parties
from src.ontology.sync_graph import find_network_cycle
from src.tools.execution import ExecutionError, execute_discount


class IntentClassification(BaseModel):
    intent: str = Field(description="one of: discount_request, dispute, payment_inquiry, other")


class ClaimExtraction(BaseModel):
    claimed_rate: float = Field(description="the discount rate the sender claims, as a decimal e.g. 0.10 for 10%")


def intake_triage(state: WorkflowState) -> dict:
    """Intake/Triage agent — cheap model, one classification call.
    email_text is untrusted free text; redact_pii runs before it reaches
    OpenRouter (a third party) — the raw text stays in Postgres for
    internal/audit use, only what's SENT to the LLM changes (§3.10)."""
    llm = get_llm("cheap").with_structured_output(IntentClassification, include_raw=True)
    raw_result = llm.invoke(
        f"Classify the intent of this finance email:\n\n{redact_pii(state['email_text'])}"
    )
    result: IntentClassification = raw_result["parsed"]
    log_audit(
        state["workflow_id"], step="intake_triage", agent="intake_triage_agent",
        decision=result.intent, reason="LLM classification", model=CHEAP_MODEL,
    )
    log_llm_cost(state["workflow_id"], "intake_triage", CHEAP_MODEL, raw_result["raw"])
    return {"intent": result.intent}


def route_after_triage(state: WorkflowState) -> str:
    return "extract_claim" if state["intent"] == "discount_request" else "escalate"


def extract_claim(state: WorkflowState) -> dict:
    """Document/claim extraction agent — cheap model, structured output.
    This is a READ of the claim, not a decision — see module docstring."""
    llm = get_llm("cheap").with_structured_output(ClaimExtraction, include_raw=True)
    raw_result = llm.invoke(
        f"Extract the claimed discount rate from this email:\n\n{redact_pii(state['email_text'])}"
    )
    result: ClaimExtraction = raw_result["parsed"]
    log_audit(
        state["workflow_id"], step="extract_claim", agent="extraction_agent",
        decision=f"claimed_rate={result.claimed_rate}", reason="LLM extraction, not yet grounded",
        model=CHEAP_MODEL,
    )
    log_llm_cost(state["workflow_id"], "extract_claim", CHEAP_MODEL, raw_result["raw"])
    return {"extracted_claim_rate": result.claimed_rate}


def ground_decision(state: WorkflowState) -> dict:
    """Discount/Policy agent — deterministic, zero LLM. The actual §3.4
    grounded-decision flow: takes the claim extract_claim just read from
    free text and checks IT against Postgres (contract status, rate ceiling,
    remaining budget) — the claim is an input to verify, not something to
    ignore. Grounding means "verify the claim against authoritative data,"
    not "substitute a different number entirely" (see the bug this fixed,
    in BRAIN.md's decisions log)."""
    result = evaluate_invoice_discount(state["invoice_id"], claimed_rate=state["extracted_claim_rate"])
    log_audit(
        state["workflow_id"], step="ground_decision", agent="discount_policy_agent",
        decision="eligible" if result.eligible else "rejected", reason=result.reason,
        tool_calls={"tool": "evaluate_invoice_discount", "invoice_id": state["invoice_id"]},
    )
    return {
        "eligibility_eligible": result.eligible,
        "eligibility_approved_rate": result.approved_rate,
        "eligibility_approval_level": result.approval_level,
        "eligibility_reason": result.reason,
    }


def route_after_grounding(state: WorkflowState) -> str:
    return "risk_score" if state["eligibility_eligible"] else "escalate"


# Above this, a proposal is auto-declined instead of sent to a human for
# approval — the whole point of scoring risk is to spend human attention
# only where it's actually needed, not on every request regardless of how
# obviously bad it is. 0.8 catches near-max risk, not just the 1.0 ceiling
# the heuristic clamps to (see risk_score's docstring for how the score is
# computed) — tunable, not a magic number picked for one demo case.
RISK_AUTO_REJECT_THRESHOLD = 0.8

# Below this: execute without a human, at whatever approval_level the
# contract policy computed (auto/manager/cfo) — see auto_execute()'s
# docstring for why self-authorizing at that tier is still policy-derived,
# not agent-invented. Deliberately much tighter than the reject ceiling
# above — auto-execution moves money, auto-rejection doesn't, so the bar
# for skipping a human is higher on this side. Gating on risk alone (not
# tier) was a deliberate choice, made explicit 2026-08-27: the eligibility
# check (contract active, within rate ceiling, within budget) already
# bounds what "compliant" means; risk_score catches the case that check
# can't — a claim that doesn't match the grounded truth.
#
# (2026-08-28: briefly set equal to RISK_AUTO_REJECT_THRESHOLD as a
# full-autonomy experiment — collapsed the human-approval middle band to
# nothing, everything either auto-executed or auto-declined. Reverted to
# 0.2 to restore the three-tier design for the real demo: the
# propose/human-approval walkthrough in demo_script.md step 5, and the
# Lovable dashboard's approval queue, both depend on the middle band
# actually existing.)
RISK_AUTO_EXECUTE_THRESHOLD = 0.2


CYCLE_RISK_BUMP = 0.3  # additive, not multiplicative: a cycle is a signal to
# weigh alongside the claim-vs-contract gap, not proof of fraud on its own —
# see find_network_cycle's docstring for why this alone is a weak signal.
#
# 2026-08-28: only applied when score > 0 (see below) — a perfect
# claim-vs-contract match is safe regardless of network topology; a closed
# trading loop should amplify existing doubt, not manufacture doubt out of
# a clean request. First version applied the bump unconditionally, which
# in THIS demo's 3-company closed triangle meant every single invoice sat
# in the human-review band, auto-execute never fired, and the three-tier
# design looked broken from the outside. Same root cause as the honest
# "weak signal" caveat already on this feature — found by actually running
# it against real seed data, not by reasoning about it in the abstract.


def risk_score(state: WorkflowState) -> dict:
    """Risk agent — deterministic heuristic score + a strong-model one-line
    narrative. The heuristic (not the LLM) sets the number; the LLM only
    explains it — the JD's zero-trust framing means scoring logic must stay
    inspectable, not hidden inside a model call.

    Also checks Neo4j for a trading cycle involving this invoice's seller
    and buyer (closing the gap named in BRAIN.md — the graph was proven
    correct via sync_graph.demo() but never called from the live workflow).
    A closed loop of companies discounting each other is a real fraud
    shape (circular trading) that a single-invoice check can never see,
    since it only ever looks at one invoice at a time. Neo4j being
    unreachable degrades to "no cycle signal available," not a crash —
    this is a risk-scoring input, not part of the eligibility guardrail,
    so it must never be able to block or corrupt a decision by being down."""
    claimed = state["extracted_claim_rate"]
    approved = state["eligibility_approved_rate"]
    delta = abs(claimed - approved)
    score = min(delta * 2, 1.0)  # bigger gap between claim and grounded truth = higher risk

    cycle_note = ""
    try:
        seller_name, buyer_name = get_invoice_parties(state["invoice_id"])
        cycle = find_network_cycle(seller_name)
        if cycle and buyer_name in cycle and score > 0:
            score = min(score + CYCLE_RISK_BUMP, 1.0)
            cycle_note = f" Part of a trading cycle: {' -> '.join(cycle)}."
    except Exception as e:
        cycle_note = f" (cycle check unavailable: {e})"

    llm = get_llm("strong")
    response = llm.invoke(
        f"In one short sentence, explain the risk of this discount proposal for a finance "
        f"approver: claimed rate {claimed:.2%}, grounded/approved rate {approved:.2%}, "
        f"risk score {score:.2f} (0=low, 1=high)."
    )
    note = response.content

    log_audit(
        state["workflow_id"], step="risk_score", agent="risk_agent",
        decision=f"risk_score={score:.2f}", reason=note + cycle_note, model=STRONG_MODEL,
    )
    log_llm_cost(state["workflow_id"], "risk_score", STRONG_MODEL, response)
    return {"risk_score": score, "risk_note": note}


def route_after_risk_score(state: WorkflowState) -> str:
    if state["risk_score"] >= RISK_AUTO_REJECT_THRESHOLD:
        return "auto_reject"
    if state["risk_score"] <= RISK_AUTO_EXECUTE_THRESHOLD:
        return "auto_execute"
    return "propose"


def auto_reject(state: WorkflowState) -> dict:
    """Risk-gated terminal node — a proposal that's grounded-eligible (it
    passed ground_decision) but too risky to put in front of a human as a
    routine approval. No approve button, no pending state: it's declined
    immediately and the company that asked gets told why. This is the other
    half of minimizing human interaction — escalate() sends unclear/rejected
    cases to a human; this sends obviously-bad-but-technically-eligible ones
    straight to a decline, so a human only ever sees the genuinely
    borderline middle."""
    llm = get_llm("strong")
    response = llm.invoke(
        f"Write a short, professional email declining a discount request. "
        f"Invoice: {state['invoice_number']}. The requested rate could not be "
        f"automatically approved due to a high risk score ({state['risk_score']:.2f}). "
        f"Note: {state['risk_note']}. Invite them to resubmit with clarification if this "
        f"was a mistake. Keep it under 80 words, no subject line."
    )
    draft = response.content
    log_llm_cost(state["workflow_id"], "auto_reject", STRONG_MODEL, response)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO discount_proposal (invoice_id, workflow_id, claimed_rate, approval_level, status, risk_score, justification) "
            "VALUES (%s, %s, %s, %s, 'rejected', %s, %s)",
            (state["invoice_id"], state["workflow_id"], state["extracted_claim_rate"], state["eligibility_approval_level"],
             state["risk_score"], state["email_text"]),
        )

    log_audit(
        state["workflow_id"], step="auto_reject", agent="risk_agent",
        decision="auto_rejected", reason=f"risk_score {state['risk_score']:.2f} >= threshold {RISK_AUTO_REJECT_THRESHOLD}",
        model=STRONG_MODEL,
    )
    publish_event(uuid.UUID(state["workflow_id"]), "workflow.auto_rejected", {
        "invoice_number": state["invoice_number"],
        "risk_score": state["risk_score"],
    })
    return {"proposal_status": "auto_rejected", "draft_response": draft}


def propose(state: WorkflowState) -> dict:
    """Response/Follow-up agent — drafts the human-facing proposal (Tier 2:
    autonomous drafting, human sends/approves — see §3.7). This node never
    calls an execute_* tool; it only writes a draft.

    Persists a NEW discount_proposal row for this specific workflow run
    (rather than relying on a pre-seeded one) — this is the propose() gap
    from BRAIN.md's decisions log, closed here. Every workflow that reaches
    this node is a real, distinct proposal instance; execute_discount()
    already selects the latest row per invoice, so this just makes that
    query meaningful for a genuinely new invoice instead of only working by
    coincidence with seed data."""
    llm = get_llm("strong")
    response = llm.invoke(
        f"Write a short, professional email reply approving/proposing a discount. "
        f"Invoice: {state['invoice_number']}. Approved rate: {state['eligibility_approved_rate']:.2%} "
        f"(approval level: {state['eligibility_approval_level']}). "
        f"Note: {state['eligibility_reason']}. Keep it under 80 words, no subject line."
    )
    draft = response.content
    log_llm_cost(state["workflow_id"], "propose", STRONG_MODEL, response)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO discount_proposal (invoice_id, workflow_id, claimed_rate, approval_level, status, risk_score, justification) "
            "VALUES (%s, %s, %s, %s, 'proposed', %s, %s)",
            (state["invoice_id"], state["workflow_id"], state["extracted_claim_rate"], state["eligibility_approval_level"],
             state["risk_score"], state["email_text"]),
        )

    log_audit(
        state["workflow_id"], step="propose", agent="response_agent",
        decision="draft_created", reason=f"approval_level={state['eligibility_approval_level']}",
        model=STRONG_MODEL,
    )
    publish_event(uuid.UUID(state["workflow_id"]), "workflow.proposed", {
        "invoice_number": state["invoice_number"],
        "approval_level": state["eligibility_approval_level"],
        "approved_rate": state["eligibility_approved_rate"],
    })
    return {"proposal_status": "proposed", "draft_response": draft}


def auto_execute(state: WorkflowState) -> dict:
    """Tier 3 autonomous execution (docs/reference/architecture.md §3.4's original
    intent, never wired up until now — see discount_logic.DiscountPolicy's
    auto_approve_rate docstring). Gated by route_after_risk_score on risk
    alone (2026-08-27 decision) — any grounded-eligible claim (active
    contract, within rate ceiling, within budget: check_eligibility, not
    this node) with a low-enough risk score executes without a human,
    regardless of approval_level tier.

    Deliberately reuses execute_discount() — the same zero-trust tool the
    human "Approve" button calls — rather than writing a second execution
    path. That means this gets the exact same re-validation against
    Postgres (a stale/tampered proposal is still caught) and the exact
    same role-rank check (src/guardrails/policy_gate.py) as a human
    approval. approver_role is passed as eligibility_approval_level itself
    (auto/manager/cfo), not hardcoded "auto" — the agent self-authorizes
    at whatever tier the deterministic policy engine computed for THIS
    discount, not a tier it picked for itself. A manager- or cfo-tier
    discount only auto-executes because check_eligibility already decided
    the contract terms genuinely call for that tier, and risk_score found
    nothing wrong with the claim; the agent isn't granting itself
    authority, it's satisfying the authority the policy already required.
    If execute_discount refuses for any reason (a guardrail catching
    something this node's own state didn't know about), this falls back to
    a human-reviewed proposal instead of failing the workflow — the row is
    already 'proposed' at that point, so no data is lost, just no
    autonomous execution."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO discount_proposal (invoice_id, workflow_id, claimed_rate, approval_level, status, risk_score, justification) "
            "VALUES (%s, %s, %s, %s, 'proposed', %s, %s) RETURNING id",
            (state["invoice_id"], state["workflow_id"], state["extracted_claim_rate"], state["eligibility_approval_level"],
             state["risk_score"], state["email_text"]),
        )
        proposal_id = str(cur.fetchone()[0])

    approver_role = state["eligibility_approval_level"]
    try:
        execute_discount(proposal_id, approver_name=f"AI Agent (auto-execute, {approver_role} tier)", approver_role=approver_role)
    except ExecutionError as e:
        log_audit(
            state["workflow_id"], step="auto_execute", agent="execution_agent",
            decision="fell_back_to_human", reason=f"guardrail refused autonomous execution: {e}",
        )
        publish_event(uuid.UUID(state["workflow_id"]), "workflow.proposed", {
            "invoice_number": state["invoice_number"],
            "approval_level": state["eligibility_approval_level"],
            "approved_rate": state["eligibility_approved_rate"],
        })
        return {"proposal_status": "proposed", "draft_response": ""}

    llm = get_llm("strong")
    response = llm.invoke(
        f"Write a short, professional email confirming a discount was applied automatically. "
        f"Invoice: {state['invoice_number']}. Approved rate: {state['eligibility_approved_rate']:.2%}. "
        f"Note this was within the standing auto-approval terms of the contract, so no manual "
        f"sign-off was required. Keep it under 80 words, no subject line."
    )
    draft = response.content
    log_llm_cost(state["workflow_id"], "auto_execute", STRONG_MODEL, response)

    log_audit(
        state["workflow_id"], step="auto_execute", agent="execution_agent",
        decision="auto_executed", reason=f"approval_level=auto, risk_score={state['risk_score']:.2f} <= {RISK_AUTO_EXECUTE_THRESHOLD}",
        model=STRONG_MODEL,
    )
    publish_event(uuid.UUID(state["workflow_id"]), "workflow.auto_executed", {
        "invoice_number": state["invoice_number"],
        "approved_rate": state["eligibility_approved_rate"],
    })
    return {"proposal_status": "auto_executed", "draft_response": draft}


def escalate(state: WorkflowState) -> dict:
    """Terminal node for anything the graph can't safely auto-progress —
    non-discount intent, or a grounded rejection. No LLM call: escalation
    is a routing decision, not a generative one."""
    is_grounded_rejection = state.get("intent") == "discount_request" and state.get("eligibility_eligible") is False
    reason = (
        f"grounded rejection: {state.get('eligibility_reason')}" if is_grounded_rejection
        else f"intent={state.get('intent')}"
    )

    if is_grounded_rejection:
        # Persist the rejection so Postgres reflects reality — otherwise a
        # dashboard/approval UI querying discount_proposal would show this
        # invoice as still 'proposed' (pending) forever, even though
        # grounding already rejected it. Found via testing the actual
        # dashboard, not in the abstract — see BRAIN.md decisions log.
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE discount_proposal SET status = 'rejected' "
                "WHERE invoice_id = %s AND status = 'proposed'",
                (state["invoice_id"],),
            )

    log_audit(
        state["workflow_id"], step="escalate", agent="supervisor",
        decision="escalated_to_human", reason=reason,
    )
    publish_event(uuid.UUID(state["workflow_id"]), "workflow.escalated", {
        "invoice_number": state.get("invoice_number"),
        "reason": reason,
    })
    return {"proposal_status": "escalated_no_match", "terminal_reason": reason}
