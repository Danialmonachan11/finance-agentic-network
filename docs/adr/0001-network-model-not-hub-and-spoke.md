# Network model, not a fixed-operator hub-and-spoke

The original schema had one `customer` table and every `contract`/`invoice`
pointed at it one-directionally (`customer_id`), implicitly encoding a
single fixed operator that everyone else owes money to. That's a
single-company AP/AR tool, not a network. Replaced with `company` and
`seller_company_id`/`buyer_company_id` on both `contract` and `invoice`, so
any Company can be a seller on one deal and a buyer on another.

Rejected: keeping the customer-centric shape and only changing the UI to
present it as a network. Doesn't work — the data model itself claimed a
fixed direction, so the UI would have been lying about what the schema
actually represented.

## Consequences

- Required dropping and reseeding all existing demo data — the old
  one-directional rows had no valid mapping onto the bidirectional model.
- Made the Neo4j graph load-bearing for the first time: a genuine trading
  cycle (Company A sells to B, B to C, C back to A) is a multi-hop
  question a flat SQL join can't answer cleanly. The single-customer model
  never had more than one hop to traverse.
