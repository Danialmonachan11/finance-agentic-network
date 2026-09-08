"""Per-agent tool allowlist (PRD R17).

The rule: an LLM-backed agent may only ever be handed the tools listed for
it here, and the drafting and reading agents get none. Execution is not a
tool any model can be given; it is a function the graph calls in code, with
an approver identity from the session.

Today every list is empty because no node binds tools to a model at all:
the models read text into a typed shape or phrase a reply, and the code
decides. `tests/test_money_path.py` enforces both halves of that: no
`bind_tools` call anywhere under `src/`, and every list here empty. The day
a tool is bound, it goes through `tools_for` and the test changes on
purpose, not by accident.
"""

TOOLS_BY_AGENT: dict[str, tuple[str, ...]] = {
    "intake_triage_agent": (),
    "extraction_agent": (),
    "status_agent": (),
    "response_agent": (),
    "risk_agent": (),
}

NEVER_A_TOOL = ("execute_discount", "send_gmail_message", "create_gmail_draft")


class ToolNotAllowed(Exception):
    pass


def tools_for(agent: str, requested: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The tools this agent may be bound to. Raises if it asks for anything
    outside its list, or for anything on NEVER_A_TOOL."""
    allowed = TOOLS_BY_AGENT.get(agent)
    if allowed is None:
        raise ToolNotAllowed(f"unknown agent {agent!r}")
    for name in requested:
        if name in NEVER_A_TOOL or name not in allowed:
            raise ToolNotAllowed(f"agent {agent!r} may not be given tool {name!r}")
    return tuple(name for name in requested)
