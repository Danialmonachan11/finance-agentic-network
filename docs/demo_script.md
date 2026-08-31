# Demo script — walkthrough

~15-20 min walkthrough. Each step is a real command against real running
services — nothing here is mocked output. Full command reference:
`BRAIN.md`'s "How to run" section. Full gap/decision history (for anything
asked "why not X"): `BRAIN.md`'s decisions log and "Honest gaps" section,
both dated.

## Presentation option: web app instead of terminal (recommended opener)

`uvicorn src.api.main:app --port 8000`, then http://localhost:8000/ —
lands on `/companies`: a network overview, not a role picker. This is the
strongest opener for a non-terminal audience:

1. Point out the overview first: every company shows an "issued" count AND
   a "received" count — visible proof this is a network, not a fixed
   "us vs customers" setup.
2. Click into one company (e.g. Aurea Retail) → its page shows both sides:
   a to-do list of requests it needs to review **as seller**, and a form to
   send a request on an invoice it received **as buyer**. Submit one — this
   runs the real pipeline live (same `run_workflow()` a real Gmail email
   hits) and narrates the result step by step, ending in the trace link.
3. Click into a *different* company that's the seller on that same
   invoice's contract → its to-do list now shows the request you just
   submitted, with a real approve form (name + role) — this is where §3.6's
   propose/execute split and §7's role-rank authorization become a UI
   action, not just code.
4. `/ops` still has the raw technical dashboard if asked "show me the
   underlying data" directly.

Worth naming if asked: this went through two real revisions from user
feedback, not one. First pass was a raw ops table with no role framing —
rebuilt into a Customer/Finance split. Second pass: even that was still a
fixed "us vs customers" assumption baked into the schema itself
(`customer_id`, one direction only) — the user caught that it should be a
genuine multi-company **network** where any company is a seller on one
deal and a buyer on another, which meant a real schema change (`company`
table, `seller_company_id`/`buyer_company_id`), not a UI tweak. Both
revisions are logged in BRAIN.md's decisions log, 2026-08-24 — good
self-review material either way, but the second one especially: it shows
catching a structural assumption, not just a display bug.

The terminal-based walkthrough below still works and is worth showing at
least once for audit-trail / raw-data credibility (nothing in the web app
is a mocked UI over fake state — same Postgres, same functions).

## 0. Framing (30 sec, before touching the keyboard)

"This is a working slice of the platform your job posting describes —
multi-agent orchestration, document AI, Neo4j, Gmail integration, and
security — built as one real, running, email-to-decision workflow rather
than a broad set of half-built pieces. Everything I'm about to run is live:
real Postgres, real Neo4j, real LLM calls, a real Gmail inbox."

Have `BRAIN.md` open in an editor tab throughout — it's the single source
of truth for what's built, and answers "why did you do X" questions
directly without improvising.

## 1. Infrastructure (1 min)

```powershell
docker compose ps
```
Postgres (transactional truth) + Neo4j (relationship graph) both up. Point
at `docker-compose.yml` — one command, fully reproducible.

## 2. The domain model (1 min)

Open `src/ontology/schema.sql`. Walk the entities in ~20 seconds: company
→ contract (seller_company_id + buyer_company_id) → discount_policy,
invoice (also seller/buyer, not one-directional) → invoice_line,
discount_proposal, audit_log (append-only). "This is the system of record
— every decision downstream gets checked against these tables, never
trusted from free text alone. And note there's no 'customer' table — any
company can be seller on one contract and buyer on another, which is the
actual point of a network."

## 3. Grounded decision-making (2 min) — the core architectural point

```powershell
.venv\Scripts\python -m src.tools.db_lookups
```

Shows 4 seeded invoices resolving correctly: two auto/manager approvals, one
manager approval, one hard rejection (expired contract). Say: "This is pure
deterministic logic — zero LLM calls. `src/tools/discount_logic.py` is the
actual policy math, independently testable, and it's the same function the
LLM-driven workflow calls later — the agent never gets its own private
version of the truth."

## 4. Neo4j — the relationship layer (1 min)

```powershell
.venv\Scripts\python -m src.ontology.sync_graph
```

Open http://localhost:7474, run:
```cypher
MATCH p = (:Company {name:'Kessler Manufacturing'})-[:TRADES_WITH*2..4]->(:Company {name:'Kessler Manufacturing'})
RETURN p LIMIT 1
```
This finds the real trading cycle: Kessler → Nordwind → Aurea → Kessler. Say: "Postgres is
still the source of truth for the actual eligibility check — that's a one-hop lookup, no
faster in Neo4j than SQL. But this query genuinely needs the graph: 'is this company part of
a trading cycle' is a multi-hop question a flat SQL join can't answer cleanly without a
recursive CTE. This was an honest gap earlier in the build — Neo4j was synced but not
load-bearing — closed once the data model became a real network instead of one company at
the center of everything." (Full detail: BRAIN.md decisions log, 2026-08-24, "Network model rework.")

## 5. The multi-agent orchestration (3 min) — the centerpiece

```powershell
.venv\Scripts\python -m src.orchestration.graph
```

Watch it run live: intake → extract → ground → risk → propose (or escalate).
Point out in `src/orchestration/nodes.py` while it runs:
- `intake_triage` / `extract_claim`: cheap model (Haiku), LLM judgment calls only
- `ground_decision`: **zero LLM calls** — re-derives eligibility from Postgres using the claim `extract_claim` just parsed
- `risk_score` / `propose`: stronger model (Sonnet 5), narrative generation only, never the decision itself
- Dynamic routing: INV-3001 skips risk/propose entirely and escalates, because grounding rejected it — no point drafting a proposal for something already rejected

"Multi-LLM routing through one OpenRouter key — cheap model for
classification, strong model only where reasoning quality actually matters."

## 6. Document extraction (2 min)

```powershell
.venv\Scripts\python -m src.ingestion.document_extraction
```

Mention `data/seed/invoices/INV-1002.pdf` is a **real, Invopop-validator-
passed, ZUGFeRD-compliant invoice** — generated using Scribo, a real
third-party invoicing API. Worth telling the CLI-vs-API story briefly here
(BRAIN.md decisions log, 2026-08-24) — shows evaluating the actual product
before assuming everything had to be built from scratch.

## 7. Real Gmail intake (3 min) — most demo-visible piece

```powershell
.venv\Scripts\python -m src.ingestion.gmail_intake
```

If already processed (idempotent — see BRAIN.md), send a fresh test email
first, referencing an invoice number, to trigger it live. Show:
- The real email in the inbox
- The resulting draft in Gmail Drafts (never auto-sent — Tier 2 boundary)
- Re-run to prove idempotency: second run does nothing, doesn't duplicate

"OAuth scopes are read + compose only — no send scope exists at all. The
'never send automatically' rule isn't just code discipline, it's enforced
by what the token can even do."

## 8. Propose vs execute, and defense in depth (3 min)

```powershell
.venv\Scripts\python -m src.tools.execution
```

Four results in one run, walk through each:
1. Insufficient-authority approver → blocked
2. Correct authority → executes
3. Re-run same execution → safe no-op, not a double-apply
4. **The strongest one**: even a full-authority CFO approver gets blocked
   executing against an expired contract, because `execute_discount`
   re-derives eligibility itself rather than trusting the proposal's
   stored state. "This is zero-trust applied to your own system's prior
   output, not just to the LLM."

## 8.5. Event-driven handoffs (2 min)

```powershell
.venv\Scripts\python -m src.orchestration.alerting_consumer
```

A consumer thread subscribes to Postgres `LISTEN`/`NOTIFY` on a separate
connection, then a *real* `run_workflow()` call fires (INV-3001, escalates)
while it's listening — and the consumer receives the live event with zero
import of or coupling to the orchestration graph. Say: "Producers and
consumers are fully decoupled — a Slack or PagerDuty integration slots in
here without touching the graph at all. I used Postgres `LISTEN`/`NOTIFY`
instead of Kafka/RabbitMQ deliberately — at one event per workflow
transition, not per token or tool call, a broker is infrastructure this
domain doesn't need yet. Same decoupling property, zero new services to
operate, and the call sites don't change if it's swapped for a real broker
later." Also mention: NOTIFY alone is ephemeral, so every event is also
durably logged (`workflow_event` table) — `replay_events()` lets an
offline consumer catch up instead of silently missing history.

## 9. Prompt-injection resistance (2 min)

```powershell
.venv\Scripts\python -m src.guardrails.injection_tests
```

Four adversarial email bodies, four different defenses (full breakdown:
BRAIN.md decisions log). Lead with the most interesting one: the "ignore
all previous instructions" case gets classified `intent=other` and
escalated to a human **before it ever reaches extraction** — routing
itself is a security control, not just a data-flow choice.

## 10. If asked "what's not built"

Answer directly from `BRAIN.md`'s "Honest gaps" section — don't
improvise. Known, precisely-scoped gaps:
- Per-agent tool allowlisting and step/retry/cost limits are designed, not enforced
- Reconciling an external invoice number to an internal record (found via
  the Scribo-generated PDF test) is a real unsolved matching problem
- Invoice-amount validation against an agreed PO/price (as opposed to
  discount-rate validation, which is grounded) isn't built — a seller
  invoicing above what was actually agreed wouldn't currently be caught

Naming these precisely, unprompted if it fits, is itself a signal — it
shows the difference between "I know where my system's edges are" and
"I hope nobody asks."

## Fallback if live infra breaks mid-demo

Every command above has been run and its real output is logged in
`BRAIN.md`'s decisions log with exact figures (rates, invoice IDs, audit
steps). If Docker/network fails live, narrate from those logs — they're
real prior runs, not invented numbers.
