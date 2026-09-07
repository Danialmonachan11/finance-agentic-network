"""A real MCP server exposing the read-tier grounded-discount tools
(docs/reference/architecture.md §3.9's MCP-style tool categorization — designed
there, never actually transported over the MCP protocol until now).

Honest scope note (see BRAIN.md, 2026-08-25): this server is real and
independently verified (see test_client.py) — a genuine MCP client,
talking to this process over stdio, gets back the same answers as calling
the underlying functions directly. It is NOT wired into the live
orchestration graph's runtime path — ground_decision still calls
db_lookups.evaluate_invoice_discount() as a direct Python function, not
over this MCP server. That's a deliberate choice, not an oversight: adding
a subprocess/IPC hop to a graph node that already runs synchronously inside
a web request trades reliability for a protocol-purity point a demo
doesn't need. The read/propose/execute tool categorization the JD's MCP
framing actually cares about is already correctly modeled in the codebase
(src/tools/) — this server proves the transport works, independent of
whether the hot path uses it.

Run standalone: python -m src.mcp_server.discount_policy_server
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.mcpserver import MCPServer

from src.tools.db_lookups import evaluate_invoice_discount, get_contract_and_policy

server = MCPServer("discount-policy")


@server.tool(structured_output=True)
def get_policy(invoice_id: str) -> dict[str, Any]:
    """Return the contract status and discount policy (max_rate,
    period_budget, auto_approve_rate) governing this invoice."""
    resolved = get_contract_and_policy(invoice_id)
    if resolved is None:
        return {"error": f"no contract/policy found for invoice {invoice_id}"}
    contract, policy = resolved
    return {
        "contract_status": contract.status,
        "effective_date": str(contract.effective_date),
        "expiry_date": str(contract.expiry_date),
        "max_rate": policy.max_rate,
        "period_budget": policy.period_budget,
        "auto_approve_rate": policy.auto_approve_rate,
    }


@server.tool(structured_output=True)
def check_discount_eligibility(invoice_id: str, claimed_rate: float) -> dict[str, Any]:
    """Ground a claimed discount rate against Postgres — the same
    grounded-decision check the live orchestration graph runs, exposed
    here over the MCP protocol for any MCP-speaking client."""
    result = evaluate_invoice_discount(invoice_id, claimed_rate=claimed_rate)
    return {
        "eligible": result.eligible,
        "approved_rate": result.approved_rate,
        "approval_level": result.approval_level,
        "reason": result.reason,
    }


if __name__ == "__main__":
    server.run(transport="stdio")
