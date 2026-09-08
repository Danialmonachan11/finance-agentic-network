"""Per-workflow and per-day caps (PRD R16).

An agent loop that misbehaves does not fail loudly; it keeps calling the
model. The design method we follow (deck section 8) says the only reliable
stop is a hard cap the code enforces before each call, not a prompt asking
the model to be frugal. Three caps, all read from the cost table that every
call already writes to:

- calls per workflow: a message needs about three; eight is runaway
- spend per workflow: dollars, same idea
- spend per day, all workflows: the kill switch a mail storm trips

Exceeding any of them raises CapExceeded; the graph runner turns that into
an escalation to a human with the reason. Step count is LangGraph's own
recursion limit, set in graph.run_workflow from WORKFLOW_MAX_STEPS.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn

WORKFLOW_MAX_LLM_CALLS = int(os.environ.get("WORKFLOW_MAX_LLM_CALLS", "8"))
WORKFLOW_MAX_SPEND_USD = float(os.environ.get("WORKFLOW_MAX_SPEND_USD", "0.10"))
DAILY_MAX_SPEND_USD = float(os.environ.get("DAILY_MAX_SPEND_USD", "5.00"))
WORKFLOW_MAX_STEPS = int(os.environ.get("WORKFLOW_MAX_STEPS", "20"))


class CapExceeded(Exception):
    def __init__(self, cap: str, value: float, limit: float, step: str):
        self.cap, self.value, self.limit, self.step = cap, value, limit, step
        super().__init__(f"{cap} cap hit before step {step!r}: {value} of {limit}")


def usage(workflow_id: str) -> tuple[int, float, float]:
    """(calls so far in this workflow, spend so far in this workflow, spend
    today across all workflows). One query."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE workflow_id = %(wf)s),
                   COALESCE(SUM(estimated_cost_usd) FILTER (WHERE workflow_id = %(wf)s), 0),
                   COALESCE(SUM(estimated_cost_usd) FILTER (WHERE occurred_at >= date_trunc('day', now())), 0)
            FROM llm_call_cost
            WHERE workflow_id = %(wf)s OR occurred_at >= date_trunc('day', now())
            """,
            {"wf": workflow_id},
        )
        calls, spend, today = cur.fetchone()
    return int(calls), float(spend), float(today)


def guard_llm_call(workflow_id: str, step: str) -> None:
    """Call before every model call. Raises CapExceeded; never returns a
    softer signal, because a soft signal is what gets ignored."""
    calls, spend, today = usage(workflow_id)
    if calls >= WORKFLOW_MAX_LLM_CALLS:
        raise CapExceeded("llm_calls", calls, WORKFLOW_MAX_LLM_CALLS, step)
    if spend >= WORKFLOW_MAX_SPEND_USD:
        raise CapExceeded("workflow_spend_usd", round(spend, 4), WORKFLOW_MAX_SPEND_USD, step)
    if today >= DAILY_MAX_SPEND_USD:
        raise CapExceeded("daily_spend_usd", round(today, 4), DAILY_MAX_SPEND_USD, step)
