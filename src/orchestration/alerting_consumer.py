"""A real, decoupled event consumer — the piece that makes this
event-driven rather than just 'the orchestration graph happens to write to
a table.' Subscribes to workflow.escalated and reacts (here: logs what a
real alert to a human ops channel would contain). It has zero knowledge of
LangGraph, the discount domain, or which node published the event — only
the event contract (docs/architecture.md §3.2's "event contracts" line from
agent-boundary design). A Slack/PagerDuty integration would slot in here
without touching src/orchestration/graph.py at all.
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.orchestration.events import listen
from src.orchestration.graph import run_workflow


def handle_escalation_alert(event: dict) -> None:
    if event["event_type"] != "workflow.escalated":
        return
    print(f"  [ALERT] workflow {event['workflow_id']} escalated — would page a human ops channel here")


def demo() -> None:
    stop_event = threading.Event()
    received = []

    def on_event(event: dict) -> None:
        received.append(event)
        handle_escalation_alert(event)

    consumer_thread = threading.Thread(target=listen, args=(on_event, stop_event), daemon=True)
    consumer_thread.start()
    time.sleep(0.5)  # let LISTEN register before the real workflow runs

    print("running a real workflow (INV-3001, expired contract -> escalates) while the consumer listens...")
    final_state = run_workflow(
        invoice_id=_get_invoice_id("INV-3001"), invoice_number="INV-3001",
        email_text="Claiming our usual 15% discount.",
    )
    assert final_state["proposal_status"] == "escalated_no_match", final_state

    deadline = time.time() + 5.0
    while not received and time.time() < deadline:
        time.sleep(0.1)

    stop_event.set()
    consumer_thread.join(timeout=2.0)

    assert len(received) == 1, f"expected exactly 1 event from the real workflow run, got {received}"
    assert received[0]["event_type"] == "workflow.escalated", received

    print(f"alerting_consumer.demo(): a real graph.run_workflow() escalation was received by a fully "
          f"decoupled consumer via Postgres NOTIFY — no direct call from the graph to this module exists")


def _get_invoice_id(invoice_number: str) -> str:
    from src.ontology.db import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM invoice WHERE invoice_number = %s", (invoice_number,))
        return str(cur.fetchone()[0])


if __name__ == "__main__":
    demo()
