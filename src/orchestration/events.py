"""Event-driven agent handoffs (docs/reference/architecture.md §3.2), via Postgres's
native LISTEN/NOTIFY — not Kafka/RabbitMQ. Deliberate choice: at this
throughput (one event per workflow transition, not per token or per tool
call), a message broker is infrastructure the JD's own domain doesn't
need yet, and Postgres pub/sub gives the same decoupling — producers never
know who's listening, consumers can join/leave independently — without a
new service to operate. The pattern generalizes to a real broker later
without changing publish_event's call sites, only its implementation.

Durability: NOTIFY alone is ephemeral (a consumer that isn't connected at
the moment of NOTIFY never sees it). Every publish also writes to
workflow_event, so a consumer that was offline can replay by querying
instead of silently missing events — this is what makes it a real event
log, not just a live pub/sub toy.
"""

import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn

CHANNEL = "workflow_events"


def publish_event(workflow_id: uuid.UUID, event_type: str, payload: dict[str, Any]) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO workflow_event (workflow_id, event_type, payload) VALUES (%s, %s, %s)",
            (str(workflow_id), event_type, json.dumps(payload)),
        )
        notify_payload = json.dumps({"workflow_id": str(workflow_id), "event_type": event_type})
        cur.execute("SELECT pg_notify(%s, %s)", (CHANNEL, notify_payload))


def replay_events(since_id: int = 0) -> list[dict]:
    """What a consumer that missed live NOTIFYs (was offline, just started)
    calls to catch up on everything after since_id."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, workflow_id, event_type, payload, occurred_at FROM workflow_event "
            "WHERE id > %s ORDER BY id",
            (since_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def listen(on_event: Callable[[dict], None], stop_event: threading.Event, timeout_seconds: float = 5.0) -> None:
    """Blocks (on a background thread, via stop_event) consuming live
    NOTIFYs on CHANNEL until stop_event is set. This is the real async
    consumer — e.g. an alerting agent reacting to 'workflow.escalated'
    without the producer (the orchestration graph) knowing or caring that
    anyone is listening."""
    conn = get_conn()
    conn.execute(f"LISTEN {CHANNEL}")
    while not stop_event.is_set():
        for notify in conn.notifies(timeout=timeout_seconds, stop_after=1):
            on_event(json.loads(notify.payload))
    conn.close()


def demo() -> None:
    received: list[dict] = []
    stop_event = threading.Event()

    consumer_thread = threading.Thread(
        target=listen, args=(received.append, stop_event), daemon=True
    )
    consumer_thread.start()
    time.sleep(0.5)  # let LISTEN register before we publish

    workflow_id = uuid.uuid4()
    publish_event(workflow_id, "workflow.escalated", {"invoice_number": "INV-3001", "reason": "expired contract"})
    publish_event(workflow_id, "workflow.proposed", {"invoice_number": "INV-1002", "approval_level": "manager"})

    deadline = time.time() + 3.0
    while len(received) < 2 and time.time() < deadline:
        time.sleep(0.1)

    stop_event.set()
    consumer_thread.join(timeout=2.0)

    assert len(received) == 2, f"expected 2 live NOTIFY events, got {len(received)}: {received}"
    assert received[0]["event_type"] == "workflow.escalated", received

    # Durability: replay must independently show the same events via the table,
    # proving this isn't just a live pub/sub toy that loses history.
    replayed = replay_events(since_id=0)
    escalated_events = [e for e in replayed if e["event_type"] == "workflow.escalated" and str(e["workflow_id"]) == str(workflow_id)]
    assert len(escalated_events) == 1, escalated_events

    print(f"events.demo(): live consumer received {len(received)} events via LISTEN/NOTIFY, "
          f"replay_events() independently confirms durability via workflow_event table")


if __name__ == "__main__":
    demo()
