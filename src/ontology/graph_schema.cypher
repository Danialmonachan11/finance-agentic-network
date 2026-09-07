// Neo4j relationship layer — mirrors the Postgres entities that matter for
// discount-policy grounding (docs/reference/architecture.md §3.3/§3.4). This is a
// derived view for traversal/explanation, NOT the transactional source of
// truth — Postgres owns balances, amounts, and status.
//
// Run with: cypher-shell -f graph_schema.cypher (after Postgres is seeded,
// via the sync script that mirrors IDs across both stores).

CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT contract_id IF NOT EXISTS FOR (c:Contract) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT policy_id IF NOT EXISTS FOR (p:DiscountPolicy) REQUIRE p.id IS UNIQUE;

// Example shape (populated by src/ontology/sync_graph.py from Postgres rows):
//
// (:Customer {id, name})
//   -[:OWNS]-> (:Contract {id, status, effective_date, expiry_date})
//     -[:GOVERNED_BY]-> (:DiscountPolicy {id, max_rate, period_budget, auto_approve_rate})
//
// Query the Discount/Policy agent actually runs (grounding step 3.4):
//
// MATCH (cust:Customer {id: $customer_id})-[:OWNS]->(contract:Contract {status: 'active'})
//       -[:GOVERNED_BY]->(policy:DiscountPolicy)
// RETURN contract.id AS contract_id, policy.max_rate AS max_rate,
//        policy.period_budget AS period_budget, policy.auto_approve_rate AS auto_approve_rate
