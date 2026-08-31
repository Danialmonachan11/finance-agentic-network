"""Workflow state shape for the invoice-discount graph. Everything a node
needs travels in this typed dict — no shared mutable blackboard, no node
reaching into another node's private state (docs/architecture.md §3.1
handoff discipline)."""

from typing import TypedDict


class WorkflowState(TypedDict, total=False):
    workflow_id: str
    invoice_id: str
    invoice_number: str
    email_text: str            # the raw claim text (from Gmail in Phase 6; from seed data for now)

    intent: str                 # intake_triage output: 'discount_request' | 'other'
    extracted_claim_rate: float  # extract_claim output — an LLM's read of the claim, NOT yet trusted

    eligibility_eligible: bool   # ground_decision output — the actual grounded truth
    eligibility_approved_rate: float
    eligibility_approval_level: str
    eligibility_reason: str

    risk_score: float
    risk_note: str

    proposal_status: str        # 'proposed' | 'auto_executed' | 'auto_rejected' | 'escalated_no_match'
    draft_response: str

    terminal_reason: str        # set when the graph ends early (escalation, non-discount intent)
