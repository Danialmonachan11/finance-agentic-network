# Architecture — Finance Agentic Network (full design reference)

This is the full 13-section architecture designed for a controlled,
auditable agentic finance-ops platform. **Not all of this is built** — see
`../BRAIN.md` for what's actually implemented vs. reference-only. Sections
below are reference for design conversations and for explaining "here's how
this would scale" in the interview, beyond what's live in the demo.

## 1. Multi-agent architecture

Supervisor + specialists, routed through the orchestrator only — no direct
agent-to-agent calls. This is what keeps permission boundaries and audit
trails tractable.

Specialists: Intake/Triage, Document Extraction, Finance Validation,
Discount/Policy, Risk/Fraud, Reconciliation, Response/Follow-up,
Audit/Governance (passive event-log sink, not an LLM agent).

Each gets a scoped context object from the supervisor — only the fields it
needs. Handoff is a typed message on the event bus
(`{workflow_id, step, payload, schema_version}`), not shared mutable state.

Escalation: any specialist that can't complete its step emits a typed
failure (`NEEDS_HUMAN`, `NEEDS_DATA`, `POLICY_VIOLATION`) rather than
guessing.

Single-agent or pure-deterministic instead of multi-agent when the task is
one classification+action, or a fixed calculation/lookup (wrap as a tool,
not an agent).

## 2. Orchestration and durability

LangGraph, state-machine per workflow type, not free-form conversation.
Sequential where a step needs the prior step's output (extraction →
validation); parallel where steps are independent (risk scoring +
discount-policy evaluation once validation passes).

Durable checkpointing per node transition. Human approval = a workflow
signal/wait state, not a blocking call — resumes on an external event.

Idempotency: every execution-tier tool call carries a key derived from
`{workflow_id, step_id}` so a crash-retry never double-executes.

## 3. Financial domain ontology

Postgres = system of record / transactional truth. Neo4j = relationship
layer for traversal (Customer → Contract → DiscountPolicy → Approval chains)
— used for grounding discount/policy reasoning, not for balances or
transactional state.

Entities: Customer, Vendor, Contract, Invoice, InvoiceLine, Product,
Discount, DiscountPolicy, Payment, Transaction, Account, Approval, Employee,
BusinessUnit, Promotion.

## 4. Grounded decision making

Agents never trust a natural-language claim without checking authoritative
data. For "our contract gives us 10%": extract claim → `get_contract()` →
`get_discount_policy()` → deterministic eligibility check (rate ≤ contract
max, budget remaining, effective dates) → map to approval level →
`propose_discount()`. RAG (if used at all) is for policy/SOP explanation
only — never the source of a rate, limit, or approval threshold.

## 5. Harness and guardrails

`Agent = LLM + Harness + Tools + Policy + State + Observability`. Harness
enforces tool allowlist per agent role, input/output schema validation,
policy checks (discount ceilings, segregation of duties), step/retry/cost
limits, escalation on any check failure, immutable audit log on every tool
call. Guardrail categories: schema, business policy, temporal, authorization,
information-flow, behavioral, financial, emergency (kill switch).

## 6. Proposal vs execution

`propose_discount()` (any agent) → deterministic policy validation → risk
score → routed to approval level → `approve_discount()` (human/auto-tier
only) → `execute_discount()` (separate execution credential, idempotent).
No agent identity holds both propose and execute credentials for
money-adjacent actions.

## 7. Autonomy tiers

0 Observation → 1 Recommendation → 2 Drafts (autonomous drafting, human
sends) → 3 Low-risk autonomous (small pre-approved discounts) → 4
Conditional high-value (approval gate) → 5 Human-only (contract mods, large
payments, new bank details).

## 8. Enterprise integration — email-first

Shared inbox, read + draft-only scopes initially, shadow mode (draft
everything, send nothing) before graduating any workflow to autonomous
execution, one workflow type at a time.

## 9. Tool architecture (MCP-style)

Read (`get_customer`, `get_invoice`, `get_contract`, ...) / Proposal
(`calculate_discount`, `propose_discount`, `create_draft`, ...) / Execution
(`execute_payment`, `send_email`, ...) — execution tools require a valid
Approval record + distinct execution identity + idempotency key. No
permission inheritance between agents.

## 10. Data, RAG, security

Postgres + object storage + Neo4j + vector store (SOP/policy text only) +
event bus. Structured truth never comes from RAG. One service identity per
agent function, scoped DB roles, no shared secrets, short-lived tokens for
execution-tier identities. Tenant isolation via RLS. Every email/attachment
treated as untrusted input — sandboxed parsing, no macro/script execution;
tool-boundary checks re-validate regardless of what the LLM claims (this is
what actually stops prompt-injection from being consequential, not a system
prompt instruction).

## 11. Observability and FinOps

OTel traces per workflow: workflow_id, agent+version, model, prompt version,
tool calls, policy checks, tokens, cost, latency, outcome. Cost per
resolved task (not per call). Model routing: cheap model for
classification/routing, stronger model only where reasoning is genuinely
needed. Cache contracts/policies at the tool layer; reuse intermediate
workflow results downstream instead of recomputing.

## 12. Evaluation

Offline benchmark suite (built from shadow-mode traffic, including
adversarial/injection cases) as a CI gate. Online: monitor override rate,
policy-violation rate, cost/latency drift.

## 13. Governance and deployment

Agent registry (identity, owner, permissions, risk tier per agent). Dev →
Test → Shadow → Canary → limited prod → broader prod. Incident response:
detect → kill switch → investigate via trace → rollback/compensate →
post-mortem → new eval case.

---

See `../BRAIN.md` for the actual build phases and what's implemented today.
