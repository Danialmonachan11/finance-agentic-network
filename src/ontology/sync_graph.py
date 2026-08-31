"""Mirror the Company/Contract/DiscountPolicy NETWORK from Postgres (the
transactional source of truth) into Neo4j (the traversal/explanation
layer). One-way sync, Postgres -> Neo4j, run after seeding or after any
contract change. See docs/architecture.md §3.3 for why this is a derived
view, not a second source of truth.

Rewritten 2026-08-24 from a single-customer hub-and-spoke model to an
actual network: every Company can be a seller on one Contract and a buyer
on another. This is also what makes the graph layer genuinely load-bearing
(a prior honest gap logged in BRAIN.md) — a triangle of companies gives a
real multi-hop traversal to run, not just one flat chain.

Run from repo root: python -m src.ontology.sync_graph
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.ontology.db import get_conn

load_dotenv()

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "finance_dev_only")


def fetch_rows():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name FROM company")
        companies = cur.fetchall()

        cur.execute("SELECT id, seller_company_id, buyer_company_id, status, effective_date, expiry_date FROM contract")
        contracts = cur.fetchall()

        cur.execute("SELECT id, contract_id, max_rate, period_budget, auto_approve_rate FROM discount_policy")
        policies = cur.fetchall()

    return companies, contracts, policies


def sync() -> None:
    companies, contracts, policies = fetch_rows()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")  # full resync, demo-scale data only

            for cid, name in companies:
                session.run(
                    "MERGE (c:Company {id: $id}) SET c.name = $name",
                    id=str(cid), name=name,
                )

            for contract_id, seller_id, buyer_id, status, eff, exp in contracts:
                session.run(
                    """
                    MATCH (seller:Company {id: $seller_id})
                    MATCH (buyer:Company {id: $buyer_id})
                    MERGE (c:Contract {id: $contract_id})
                    SET c.status = $status, c.effective_date = toString($eff), c.expiry_date = toString($exp)
                    MERGE (seller)-[:SELLS_ON]->(c)
                    MERGE (buyer)-[:BUYS_ON]->(c)
                    MERGE (seller)-[t:TRADES_WITH]->(buyer)
                    SET t.contract_id = $contract_id, t.status = $status
                    """,
                    seller_id=str(seller_id), buyer_id=str(buyer_id), contract_id=str(contract_id),
                    status=status, eff=eff, exp=exp,
                )

            for policy_id, contract_id, max_rate, budget, auto_rate in policies:
                session.run(
                    """
                    MATCH (c:Contract {id: $contract_id})
                    MERGE (p:DiscountPolicy {id: $policy_id})
                    SET p.max_rate = $max_rate, p.period_budget = $budget, p.auto_approve_rate = $auto_rate
                    MERGE (c)-[:GOVERNED_BY]->(p)
                    """,
                    contract_id=str(contract_id), policy_id=str(policy_id),
                    max_rate=float(max_rate), budget=float(budget), auto_rate=float(auto_rate),
                )
    finally:
        driver.close()

    print(f"synced {len(companies)} companies, {len(contracts)} contracts, {len(policies)} policies to Neo4j")


def get_policy_via_graph(seller_name: str, buyer_name: str) -> dict | None:
    """The direct lookup a Discount/Policy agent runs for one specific
    trading relationship — one hop, same cost as a SQL join."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (seller:Company {name: $seller_name})-[:SELLS_ON]->(contract:Contract {status: 'active'})
                      <-[:BUYS_ON]-(buyer:Company {name: $buyer_name}),
                      (contract)-[:GOVERNED_BY]->(policy:DiscountPolicy)
                RETURN contract.id AS contract_id, policy.max_rate AS max_rate,
                       policy.period_budget AS period_budget, policy.auto_approve_rate AS auto_approve_rate
                """,
                seller_name=seller_name, buyer_name=buyer_name,
            )
            record = result.single()
            return dict(record) if record else None
    finally:
        driver.close()


def find_network_cycle(start_company: str, max_hops: int = 4) -> list[str] | None:
    """The query that actually needs the graph, not SQL: is this company
    part of a trading cycle (A sells to B, B sells to C, ... back to A)?
    This is a real multi-hop traversal — the kind of question a flat SQL
    join can't answer cleanly without recursive CTEs, and exactly the case
    named as the graph's honest gap earlier (docs/BRAIN.md, "Neo4j not yet
    in the hot path" — closed by giving it a question that needs 2+ hops)."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            result = session.run(
                f"""
                MATCH path = (start:Company {{name: $start_company}})-[:TRADES_WITH*2..{max_hops}]->(start)
                RETURN [n IN nodes(path) | n.name] AS cycle
                LIMIT 1
                """,
                start_company=start_company,
            )
            record = result.single()
            return record["cycle"] if record else None
    finally:
        driver.close()


def demo() -> None:
    sync()

    direct = get_policy_via_graph("Kessler Manufacturing", "Nordwind Logistik GmbH")
    assert direct is not None, "expected an active contract Kessler -> Nordwind"
    assert direct["max_rate"] == 0.15, direct
    print(f"sync_graph.demo(): direct (1-hop) lookup returned {direct}")

    cycle = find_network_cycle("Kessler Manufacturing")
    assert cycle is not None, "expected to find the Kessler -> Nordwind -> Aurea -> Kessler trading cycle"
    print(f"sync_graph.demo(): found trading cycle via multi-hop traversal: {' -> '.join(cycle)}")


if __name__ == "__main__":
    demo()
