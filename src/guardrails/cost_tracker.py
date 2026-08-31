"""AI FinOps (docs/architecture.md §3.11): cost per LLM call, aggregated per
workflow. Designed in the architecture doc, never implemented until now —
closed after comparing this build against a reference banking-agent
architecture diagram that named a "Cost Tracker" as its own component.

Pricing is a hardcoded estimate (checked against OpenRouter's published
per-model rates at time of writing, 2026-08-25) — not a live pricing API
call, which would be a real integration for a production FinOps system but
is overkill for a demo. Documented as an estimate, not claimed as exact.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn

# USD per 1M tokens, (input, output). Estimate as of 2026-08-25 — see
# module docstring. Update here if OpenRouter's published rates move.
MODEL_PRICING = {
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "anthropic/claude-sonnet-5": (3.00, 15.00),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = MODEL_PRICING.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def log_llm_cost(workflow_id: str, step: str, model: str, response) -> float:
    """Call with the raw LangChain AIMessage (for a structured-output call,
    that's the with_structured_output(..., include_raw=True) result's
    'raw' key, not the parsed object — the parsed Pydantic model doesn't
    carry usage data). OpenRouter reports real per-call cost directly in
    response_metadata['token_usage']['cost'] — prefer that over our own
    pricing-table estimate when present; it's the provider's own number,
    strictly more accurate than a hardcoded rate we'd have to keep in sync
    by hand."""
    usage = response.usage_metadata or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    reported_cost = response.response_metadata.get("token_usage", {}).get("cost")
    cost = float(reported_cost) if reported_cost is not None else estimate_cost_usd(model, input_tokens, output_tokens)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_call_cost (workflow_id, step, model, input_tokens, output_tokens, estimated_cost_usd) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (workflow_id, step, model, input_tokens, output_tokens, cost),
        )
    return cost


def get_workflow_cost(workflow_id: str) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(estimated_cost_usd),0) "
            "FROM llm_call_cost WHERE workflow_id = %s",
            (workflow_id,),
        )
        calls, input_tokens, output_tokens, cost = cur.fetchone()
    return {"calls": calls, "input_tokens": input_tokens, "output_tokens": output_tokens, "estimated_cost_usd": float(cost)}


def get_network_cost_summary() -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT workflow_id), count(*), COALESCE(SUM(estimated_cost_usd),0) FROM llm_call_cost"
        )
        workflows, calls, total_cost = cur.fetchone()
    return {"workflows": workflows, "calls": calls, "total_cost_usd": float(total_cost)}


def demo() -> None:
    import uuid
    from src.orchestration.llm import get_llm

    workflow_id = str(uuid.uuid4())
    llm = get_llm("cheap")
    response = llm.invoke("Reply with exactly one word: ok")
    cost = log_llm_cost(workflow_id, "test_step", "anthropic/claude-haiku-4.5", response)
    assert cost > 0, "expected a nonzero cost estimate for a real API response"

    summary = get_workflow_cost(workflow_id)
    assert summary["calls"] == 1, summary
    assert summary["estimated_cost_usd"] == cost, summary
    print(f"cost_tracker.demo(): logged 1 call, {summary['input_tokens']} in / {summary['output_tokens']} out tokens, "
          f"${summary['estimated_cost_usd']:.6f} estimated")


if __name__ == "__main__":
    demo()
