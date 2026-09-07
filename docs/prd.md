# PRD: Finance Agentic Network

Status: draft v0.1, 2026-09-07. Owner: Danial.
Inputs: `docs/market/ap-ar-primer.md`, `docs/market/pain-points-network.md`,
the design method in `docs/reference/ai-system-design-interviews-live-session.pdf`.
Every requirement below names the pain or the lever that licenses it. If a
requirement has no source, delete it.

Architecture diagram: `docs/diagrams/architecture.html` (interactive, source in
`architecture.json`, static copy `architecture.png`).

## 1. Problem

Every B2B invoice has two finance teams on it, and they talk by email.
Status questions, discount and deduction claims, and bank-detail changes
all cross the company boundary as free text that a human on the far side
must read, look up, and answer. That is where the hours, the delays, and
the fraud live:

| Pain | Cost today | Source |
|---|---|---|
| "Where is my payment?" | ~2 hours of an 8-hour AP day on supplier inquiries | MineralTree, AP Benchmarking |
| Disputes, deductions, short-pays | 40% of B2B payment delays; 5 to 15 days to resolve | PYMNTS 2025, AgentCollect 2026 |
| Bank-detail change fraud | $3.05B lost in 2025, $123k per incident, 74% of firms hit | FBI IC3, AFP |

Existing vendors (Coupa, Tipalti, HighRadius, Billtrust) automate one
side. None of the three pains above can be fixed from one side, because
the answer or the evidence sits with the counterparty.

## 2. Product in one sentence

An agent that sits on a company's finance mailbox and ERP, answers and
raises the three cross-company questions on the company's behalf, and
talks to the counterparty's agent directly when one exists, falling back
to email when it does not.

## 3. Users

- **Primary: AP or AR analyst at a mid-market company** (roughly 500 to
  5,000 invoices a month). Wants the inbox to shrink. Judges the product
  by exceptions cleared per day without them.
- **Approver: finance manager or controller.** Sees only the contested
  middle. Judges the product by whether anything wrong ever reached
  execution.
- **Counterparty's agent.** Not a person. Needs a protocol, an identity,
  and a reason to trust ours.

## 4. Goals and non-goals

**Goals for v1**

1. Answer inbound invoice-status questions with zero human touches when
   the invoice is on file.
2. Validate inbound discount and deduction claims against the contract
   and route only the contested ones to a human.
3. Refuse any bank-detail change that did not arrive through a verified
   channel, and open a verification task instead.
4. Work single-sided against email on day one. Upgrade to structured
   agent-to-agent exchange when the counterparty runs the product.

**Non-goals for v1**

- OCR and capture quality. E-invoicing mandates are removing this need.
- GL coding, approval routing inside one company, credit decisions.
- Payment execution. We stop at "approved, ready for the payment run."
- Multi-tenant SaaS operations. One deployment per company is fine.
- Early-payment negotiation. Medium fit, needs treasury data. Later.

## 5. The five levers (design method step 1)

| Lever | Answer for this product | What it moves in the design |
|---|---|---|
| Scale | 500 to 5,000 invoices/month per company, roughly 10 to 100 cross-company messages a day | No queue needed at v1; a single worker with a durable checkpoint is enough |
| Latency | Minutes are fine. A dispute answer inside one business hour beats the current 5 days | No streaming, no p95 obsession. Batch polling acceptable |
| Freshness | Contracts and invoice status change hourly at most | Direct ERP or Postgres lookups. No RAG for facts. Ever. |
| Error cost | A wrong discount is money; a wrong bank change is theft | Deterministic policy layer decides, LLM only reads and drafts. Human gate on every write. Capability caps, not prompt rules |
| Budget | Manual cost is ~$6 per claim and ~$9 per invoice. Target under $0.50 per resolved message | Cheap model for classification and extraction, strong model only for drafting. Hard cap on calls per workflow |

## 6. The envelope (design method step 2)

Per company, per day, upper end of the v1 range:

```
messages        100 cross-company messages/day
LLM calls       3 per message (classify, extract, draft) = 300 calls/day
tokens          ~2,000 per call = 600k tokens/day
cost            at Haiku/Sonnet mix: ~$1.50/day, ~$0.015 per message
human touches   target 30 of 100 messages reach a person (the contested middle)
```

Cost is not the constraint. Correctness and trust are. The design should
spend tokens freely and spend human attention stingily.

## 7. Functional requirements

Each line names its source pain (P1 status, P2 dispute, P3 bank change) or
lever (L-risk, L-fresh, L-cost).

**Intake**
- R1. Read a shared finance mailbox and classify each message as status
  inquiry, discount or deduction claim, bank-detail change, or other. (P1, P2, P3)
- R2. Resolve the invoice, counterparty, and contract the message refers
  to from the system of record. Match on counterparty plus amount plus
  date plus reference, not invoice-number string equality. (P1, P2)
- R3. Unresolvable messages go to a human queue with the reason. Never
  silently dropped. (L-risk)

**Status inquiry (P1)**
- R4. Answer with the invoice's real state: received, matched, approved,
  scheduled with date, paid with reference, or blocked with reason. (P1)
- R5. Draft the reply. Send only if the company has enabled autonomous
  replies for this counterparty and message type. Default is draft. (L-risk)

**Claims (P2)**
- R6. Extract the claimed rate or amount. Verify it against the contract
  policy with a deterministic function. The LLM's extraction is an input
  to verify, never the decision. (P2, L-risk)
- R7. Route by outcome: within policy and low risk executes at the tier
  the policy names; outside policy is declined with the reason; the
  contested middle goes to an approver with the evidence attached. (P2)
- R8. Approvers act only on proposals for their own company, at or above
  the required role rank. Approver identity comes from the session, never
  from message text. (L-risk)
- R9. Execution re-derives eligibility for the exact proposal being
  approved, and is idempotent. (L-risk)

**Bank-detail change (P3)**
- R10. Any message that asks to change payment details is classified as
  such and never applied automatically, regardless of content. (P3)
- R11. Open a verification task with the counterparty's previously known
  contact, not the contact in the message. (P3)
- R12. When the counterparty runs the product, accept a change only as a
  signed message from its agent under its registered identity. (P3)

**Network**
- R13. Every outbound cross-company message is also emitted in a
  structured form. If the counterparty's agent is reachable, deliver the
  structured form; else send the email. (Goal 4)
- R14. Counterparty identity is a registry keyed on VAT ID or Peppol ID,
  with a signing key. Unknown identity means email-only mode. (P3)

**Harness**
- R15. Every step writes an audit row. Every LLM call writes a cost row.
  One trace per case from first message to final state. (L-cost, L-risk)
- R16. Per-workflow caps: max LLM calls, max steps, max spend. Exceeding
  a cap escalates to a human. (L-cost, design method section 8)
- R17. Per-agent tool allowlist enforced by the framework, not by
  convention. The drafting agent cannot call execution. (L-risk, design
  method section 9)
- R18. PII redaction before any text leaves for a third-party model. (L-risk)

## 8. Success metrics

| Metric | Baseline (market) | v1 target |
|---|---|---|
| Status inquiries answered with zero human touches | ~0% | 80% |
| Claim resolution time, clear-cut cases | 5 to 15 days | under 1 hour |
| Share of claims reaching a human | 100% | 30% |
| Bank-detail changes applied without verification | unknown, non-zero | 0 |
| Cost per resolved message | ~$6 manual | under $0.50 |
| Wrong executions | n/a | 0, gated by the golden set |

## 9. Evaluation (design method step 6)

- A golden set of at least 200 real or realistic messages across the four
  intents, including adversarial and injection cases, with expected
  outcome per message. Runs on every prompt, model, or policy change.
- Offline unit tests for the deterministic policy layer that run without
  any database or model.
- Online: override rate (human reverses agent), policy-violation rate,
  cost per message, alerted on the delta week over week.

## 10. Rollout (design method step 7)

Shadow (draft everything, send nothing), then autonomous for status
inquiries only, then autonomous for within-policy claims below a rate
threshold, one counterparty at a time. Bank-detail changes are never
autonomous. Kill switch per intent.

## 11. Decision ledger

One line per box. Add to this, never edit history.

| Decision | Licensed by |
|---|---|
| Deterministic policy function decides, LLM reads and drafts | L-risk: a wrong discount is money |
| Facts from ERP or Postgres lookups, no RAG | L-fresh: transactional truth, hourly changes |
| Cheap model for classify and extract, strong for drafting | L-cost, envelope: 3 calls per message |
| Human gate on every write, capability caps not prompt rules | L-risk, design method section 9: only capability stops attacks |
| Email-first, structured exchange when available | Cold-start: never require both sides |
| Status inquiry is the first autonomous intent | P1 is read-only, no money moves, same ERP integration feeds P2 and P3 |
| Bank changes never autonomous | P3: $123k per incident, verification is the whole product |
| Postgres checkpoint and event log, no message broker | Envelope: 100 messages a day per company |
| Approvers scoped to a company | Network model: no fixed "us", segregation of duties is per entity |

## 12. Open questions

1. Identity registry. Self-hosted, or piggyback on Peppol participant IDs?
   Decides R12 and R14.
2. ERP boundary. Which ERP first? NetSuite and Dynamics BC are the
   mid-market defaults. Read-only adapter is the integration tax.
3. Who pays first, buyer or seller? Status inquiry is a buyer-side cost,
   disputes are a seller-side cost. Pick one to sell to.
4. What of the current codebase survives? The discount workflow, policy
   gate, execution tool, audit and cost tables, and event log map onto
   R6 to R9 and R15. The Jinja UI and the Scribo invoice generator do not
   map to any requirement.

## 13. What exists today against this PRD

| Requirement | State in `src/` |
|---|---|
| R1 classify | Partial: four intents, one hardcoded Gmail query |
| R2 resolve | Missing: regex on invoice number only |
| R3 human queue for unresolved | Missing: returns None |
| R4, R5 status inquiry | Missing |
| R6, R7 claims | Present, with the bugs listed in the 2026-09-07 review |
| R8 approver scoping | Missing: approvers are global |
| R9 idempotent execution | Present, revalidation reads the wrong row |
| R10 to R12 bank change | Missing |
| R13, R14 network | Missing |
| R15 audit and cost | Present |
| R16 caps | Missing |
| R17 allowlist | Missing |
| R18 PII redaction | Present, regex only |
