"""Per-workflow and per-day caps (PRD R16).

An agent loop that misbehaves does not fail loudly; it keeps calling the
model. The design method we follow (deck section 8) says the only reliable
stop is a hard cap the code enforces before each call, not a prompt asking
the model to be frugal. Three caps, all read from the cost table that every
call already writes to:

- calls per workflow: a message needs about three; eight is runaway
- spend per workflow: euros, same idea
- spend per day, all workflows, in euros: the kill switch a mail storm trips

Exceeding any of them raises CapExceeded; the graph runner turns that into
an escalation to a human with the reason. Step count is LangGraph's own
recursion limit, set in graph.run_workflow from WORKFLOW_MAX_STEPS.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.guardrails.cost_tracker import USD_PER_EUR, to_eur
from src.ontology.db import get_conn

WORKFLOW_MAX_LLM_CALLS = int(os.environ.get("WORKFLOW_MAX_LLM_CALLS", "8"))
WORKFLOW_MAX_SPEND_EUR = float(os.environ.get("WORKFLOW_MAX_SPEND_EUR", "0.10"))
DAILY_MAX_SPEND_EUR = float(os.environ.get("DAILY_MAX_SPEND_EUR", "5.00"))
WORKFLOW_MAX_STEPS = int(os.environ.get("WORKFLOW_MAX_STEPS", "20"))


class CapExceeded(Exception):
    def __init__(self, cap: str, value: float, limit: float, step: str):
        self.cap, self.value, self.limit, self.step = cap, value, limit, step
        super().__init__(f"{cap} cap hit before step {step!r}: {value} of {limit}" + (" EUR" if "eur" in cap else ""))


def usage(workflow_id: str) -> tuple[int, float, float]:
    """(calls so far in this workflow, spend so far in this workflow, spend
    today across all workflows), spend in euros. One query."""
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
    return int(calls), to_eur(spend), to_eur(today)


def guard_llm_call(workflow_id: str, step: str) -> None:
    """Call before every model call. Raises CapExceeded; never returns a
    softer signal, because a soft signal is what gets ignored."""
    calls, spend, today = usage(workflow_id)
    if calls >= WORKFLOW_MAX_LLM_CALLS:
        raise CapExceeded("llm_calls", calls, WORKFLOW_MAX_LLM_CALLS, step)
    if spend >= WORKFLOW_MAX_SPEND_EUR:
        raise CapExceeded("workflow_spend_eur", round(spend, 4), WORKFLOW_MAX_SPEND_EUR, step)
    if today >= DAILY_MAX_SPEND_EUR:
        raise CapExceeded("daily_spend_eur", round(today, 4), DAILY_MAX_SPEND_EUR, step)
