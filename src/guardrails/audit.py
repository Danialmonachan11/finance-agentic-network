"""Immutable audit log writer (docs/reference/architecture.md §3.5). Every agent step
in the orchestration graph calls this — one row per step, append-only,
never updated or deleted. This is the harness-enforced side of "every
decision is auditable," not something an agent can opt out of.
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn


def log_audit(
    workflow_id: uuid.UUID,
    step: str,
    agent: str,
    decision: str,
    reason: str,
    model: str | None = None,
    tool_calls: dict[str, Any] | None = None,
) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log (workflow_id, step, agent, model, tool_calls, decision, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (str(workflow_id), step, agent, model, json.dumps(tool_calls) if tool_calls else None, decision, reason),
        )


def get_audit_trail(workflow_id: uuid.UUID) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT step, agent, model, decision, reason, occurred_at FROM audit_log "
            "WHERE workflow_id = %s ORDER BY occurred_at",
            (str(workflow_id),),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def demo() -> None:
    wf_id = uuid.uuid4()
    log_audit(wf_id, step="intake_triage", agent="intake_agent", decision="classified", reason="discount_request", model="anthropic/claude-haiku-4.5")
    log_audit(wf_id, step="ground_decision", agent="discount_policy_agent", decision="eligible", reason="within policy")

    trail = get_audit_trail(wf_id)
    assert len(trail) == 2, trail
    assert trail[0]["step"] == "intake_triage"
    print(f"audit.demo(): wrote and retrieved {len(trail)} audit rows for workflow {wf_id}")


if __name__ == "__main__":
    demo()
