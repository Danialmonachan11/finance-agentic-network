"""Independent verification that discount_policy_server.py is a genuine,
working MCP server — spawns it as a real subprocess and talks to it over
stdio via the actual MCP protocol (JSON-RPC), not an in-process function
call. Compares results against calling the underlying tools directly, to
prove the protocol round-trip doesn't lose or corrupt anything.

Run: python -m src.mcp_server.test_client
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from src.ontology.db import get_conn
from src.tools.db_lookups import evaluate_invoice_discount

REPO_ROOT = Path(__file__).resolve().parents[2]


async def run() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM invoice WHERE invoice_number = 'INV-1002'")
        invoice_id = str(cur.fetchone()[0])

    server_params = StdioServerParameters(
        command=str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
        args=["-m", "src.mcp_server.discount_policy_server"],
        cwd=str(REPO_ROOT),
    )

    async with Client(server_params) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools.tools}
        print(f"real MCP server advertised tools: {sorted(tool_names)}")
        assert {"get_policy", "check_discount_eligibility"} <= tool_names

        policy_result = await client.call_tool("get_policy", {"invoice_id": invoice_id})
        print(f"get_policy (via real MCP protocol, subprocess, stdio transport): {policy_result.structured_content}")
        assert policy_result.structured_content["contract_status"] == "active"
        assert policy_result.structured_content["max_rate"] == 0.15

        eligibility_result = await client.call_tool(
            "check_discount_eligibility", {"invoice_id": invoice_id, "claimed_rate": 0.12}
        )
        print(f"check_discount_eligibility (via real MCP protocol): {eligibility_result.structured_content}")

    # Cross-check against calling the same underlying function directly —
    # the MCP round-trip must not change the answer.
    direct_result = evaluate_invoice_discount(invoice_id, claimed_rate=0.12)
    assert eligibility_result.structured_content["eligible"] == direct_result.eligible
    assert eligibility_result.structured_content["approved_rate"] == direct_result.approved_rate
    assert eligibility_result.structured_content["approval_level"] == direct_result.approval_level

    print("test_client: real MCP server verified — subprocess spawned, stdio protocol round-trip, "
          "results match the direct function call exactly")


def demo() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    demo()
