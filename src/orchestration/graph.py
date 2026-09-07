"""LangGraph state machine wiring the specialist nodes together
(docs/reference/architecture.md §3.1/§3.2). Sequential where a step needs the prior
step's output, with dynamic routing at three points: non-discount intent
skips straight to escalation; a grounded rejection (contract expired,
budget exhausted) skips risk-scoring and drafting entirely — no point
scoring or drafting a proposal for something already rejected; and a
high-risk-but-grounded-eligible claim skips human approval entirely and
gets auto-declined — the point of scoring risk is to spend human attention
only on the genuinely borderline middle, not on every request regardless
of how obviously bad it is.

Durability: uses LangGraph's Postgres-backed checkpointer (closed
2026-08-25 — this was the in-memory MemorySaver until compared against a
reference architecture that named a durable session store explicitly).
Workflow state now genuinely survives a process restart, keyed by
workflow_id as the thread_id. Run `python -m src.orchestration.checkpointer_setup`
once against a fresh database to create the checkpointer's own tables.
"""

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://finance:finance_dev_only@localhost:5432/finance_agentic")

from src.guardrails.audit import get_audit_trail
from src.orchestration.nodes import (
    auto_execute,
    auto_reject,
    escalate,
    extract_claim,
    ground_decision,
    intake_triage,
    propose,
    risk_score,
    route_after_grounding,
    route_after_risk_score,
    route_after_triage,
)
from src.orchestration.state import WorkflowState


def build_graph(checkpointer):
    graph = StateGraph(WorkflowState)

    graph.add_node("intake_triage", intake_triage)
    graph.add_node("extract_claim", extract_claim)
    graph.add_node("ground_decision", ground_decision)
    graph.add_node("risk_score", risk_score)
    graph.add_node("propose", propose)
    graph.add_node("auto_reject", auto_reject)
    graph.add_node("auto_execute", auto_execute)
    graph.add_node("escalate", escalate)

    graph.add_edge(START, "intake_triage")
    graph.add_conditional_edges("intake_triage", route_after_triage, {
        "extract_claim": "extract_claim", "escalate": "escalate",
    })
    graph.add_edge("extract_claim", "ground_decision")
    graph.add_conditional_edges("ground_decision", route_after_grounding, {
        "risk_score": "risk_score", "escalate": "escalate",
    })
    graph.add_conditional_edges("risk_score", route_after_risk_score, {
        "propose": "propose", "auto_reject": "auto_reject", "auto_execute": "auto_execute",
    })
    graph.add_edge("propose", END)
    graph.add_edge("auto_reject", END)
    graph.add_edge("auto_execute", END)
    graph.add_edge("escalate", END)

    return graph.compile(checkpointer=checkpointer)


def run_workflow(invoice_id: str, invoice_number: str, email_text: str) -> WorkflowState:
    workflow_id = uuid.uuid4()
    initial_state: WorkflowState = {
        "workflow_id": str(workflow_id),
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "email_text": email_text,
    }
    config = {"configurable": {"thread_id": str(workflow_id)}}

    with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
        app = build_graph(checkpointer)
        final_state = app.invoke(initial_state, config=config)
    return final_state


def demo() -> None:
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from src.ontology.db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (i.id) i.id, i.invoice_number, dp.justification
            FROM invoice i JOIN discount_proposal dp ON dp.invoice_id = i.id
            ORDER BY i.id, dp.created_at
            """
        )
        rows = cur.fetchall()
        rows.sort(key=lambda r: r[1])

    assert len(rows) == 4, f"expected 4 seeded invoices, found {len(rows)} — run `python -m data.seed.seed` first"

    outcomes = {}
    for invoice_id, invoice_number, justification in rows:
        final_state = run_workflow(str(invoice_id), invoice_number, justification)
        outcomes[invoice_number] = final_state
        print(f"\n=== {invoice_number} ===")
        print(f"  intent: {final_state.get('intent')}")
        print(f"  proposal_status: {final_state.get('proposal_status')}")
        if final_state.get("proposal_status") in ("proposed", "auto_executed"):
            print(f"  approval_level: {final_state['eligibility_approval_level']}")
            print(f"  risk_score: {final_state['risk_score']:.2f}")
            print(f"  draft: {final_state['draft_response'][:100]}...")
        else:
            print(f"  terminal_reason: {final_state.get('terminal_reason')}")

        trail = get_audit_trail(uuid.UUID(final_state["workflow_id"]))
        print(f"  audit steps: {[t['step'] for t in trail]}")

    # Every seeded claim here exactly matches its grounded rate (risk_score
    # 0.0) -> auto-executes regardless of tier (2026-08-27: risk-gated, not
    # tier-gated). INV-1001 is auto tier, INV-1002 and INV-2001 are manager
    # tier — all three clear the risk gate, so all three execute without a
    # human. Only a genuinely expired contract (INV-3001) still escalates.
    #
    # (2026-08-27: added a Neo4j trading-cycle check to risk_score. First
    # version applied its bump unconditionally, which in this demo's one
    # closed 3-company triangle meant every invoice got flagged and none
    # of these three could auto-execute anymore — the three-tier design
    # looked broken. 2026-08-28: fixed by only letting the cycle signal
    # amplify an EXISTING mismatch (score > 0), never manufacture risk out
    # of a clean match — restores this auto-execute behavior for real,
    # while still amplifying score for any invoice with a genuine
    # claim-vs-contract gap. Also briefly ran with both risk thresholds
    # collapsed as a separate full-autonomy experiment — reverted; see
    # nodes.py's RISK_AUTO_EXECUTE_THRESHOLD comment.)
    assert outcomes["INV-1001"]["proposal_status"] == "auto_executed"
    assert outcomes["INV-1001"]["eligibility_approval_level"] == "auto"
    assert outcomes["INV-2001"]["proposal_status"] == "auto_executed"
    assert outcomes["INV-2001"]["eligibility_approval_level"] == "manager"
    assert outcomes["INV-3001"]["proposal_status"] == "escalated_no_match", "expired contract must escalate, not propose"

    print("\ngraph.demo(): all 4 workflows ran end-to-end, outcomes match grounded expectations")


if __name__ == "__main__":
    demo()
