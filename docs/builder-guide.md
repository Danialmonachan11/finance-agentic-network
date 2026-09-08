# Builder's guide

For the person who owns this project and wants to know why each piece is
there, not only that it is. Read this when you come back after a break, when
you want to add something, or when an AI suggests a change and you want to
judge it.

How this fits with the other docs:

- `docs/prd.md` says what we are building and why (the target).
- `BRAIN.md` says what happened and what was decided, in date order (the history).
- `ROADMAP.md` says what is next, in progress, and done (the board).
- This file says how the thing works and why it is shaped this way (the map).

## 1. The two ideas everything hangs on

**Code decides, the model reads and drafts.** A wrong discount is money. So
the number that gets booked is never a model output. The model does two
jobs only: read free text into a typed shape ("this email claims 10%") and
turn a decision into a polite reply. Everything between those two, the
check against the contract, the budget, the risk score, the approval rank,
the write to the database, is plain Python and SQL that a test can pin
down. If you ever see a proposal to let the model "decide" something, the
question to ask is "what happens when it is wrong", and the answer is
usually "we lose money and cannot explain why".

**The pair is the product.** Since 2026-09-08 the unit of deployment is a
pair of companies, A to B. Each pair has its own contract, policy,
approvers on each side, keys, caps, and history. A to C is a different
pair. There is no view above the pairs. This matches how finance teams
think ("our thing with Acme"), it makes approver scoping a fact of the data
model rather than a rule someone has to remember, and it lets you sell one
pair at a time without waiting for a network to exist.

## 2. A message's journey

One email arrives: "Per our contract we are taking the 10% early payment
discount on INV-2041." Here is what touches it, in order, and why.

1. **Gmail intake** (`src/ingestion/gmail_intake.py`) polls the mailbox,
   skips anything already processed by message id, and pulls the invoice
   number out of the text. Why the dedupe: Gmail will hand you the same
   message twice, and a double-processed claim is a double discount.
2. **PII redaction** (`src/guardrails/pii_redaction.py`) masks emails,
   phones, and IBANs before any text goes to the model. Why: the model is
   a third party. The decision never needs a person's phone number.
3. **Resolver** (`src/tools/resolver.py`) works out which invoice the
   message is about, before any model call: the sender's company from the
   email domain, plus a quoted invoice number or a quoted amount. Two
   candidates means no match and a human, never a guess. Why not the
   invoice number alone: senders misquote it, quote several, or give the
   amount instead.
4. **Intake triage** (`intake_triage` in `src/orchestration/nodes.py`) asks
   the cheap model "what kind of message is this": status inquiry,
   discount request, bank change, or other. Status inquiries go to
   `answer_status`, which reads the invoice row and has the model phrase
   those facts and nothing else, as a draft. Discount requests continue
   below. Bank changes and everything else go to a human. Why the cheap
   model: classification is easy and this runs on every message.
5. **Claim extraction** (`extract_claim`) asks the cheap model for the
   claimed rate as a number. This is a read, not a decision.
6. **Grounding** (`ground_decision`, which calls
   `src/tools/db_lookups.py` and then `src/tools/discount_logic.py`) checks
   that number against the contract in Postgres: is the contract active, is
   the rate within the ceiling, is there budget left this period. No model.
   Pure function, testable offline. This is the heart of the system.
7. **Risk score** (`risk_score`) adds a heuristic on top: how far the claim
   is from the contract, and whether the two companies sit in a trading
   loop. Low risk executes on its own, high risk declines with a drafted
   reply, the middle goes to a human. Why three outcomes: a human should see
   only the cases a rule cannot settle, otherwise the product saves no time.
8. **Propose, auto-execute, auto-reject, escalate** are the four terminal
   nodes. Each writes a row to `discount_proposal` so the UI shows reality,
   an audit row so the trace is complete, and an event so anything
   listening (the alerting consumer, a dashboard) hears about it.
9. **Execution** (`src/tools/execution.py`) is the only function that can
   mark a proposal executed. It re-derives eligibility from scratch for the
   exact proposal being approved, checks the approver's rank, and flips the
   row with an atomic conditional update. Why re-derive: the proposal might
   be hours old and the contract might have changed. Why the exact
   proposal: an approver decided on one row, not "whatever is newest". Why
   atomic: two approvers clicking at once must not both succeed. It also
   refuses an approver who is not on the seller's side of the invoice, and
   any invoice whose two companies do not have an active pair.

Every step writes to `audit_log` with the same `workflow_id`, and every
model call writes to `llm_call_cost`. One id, one trace, one cost line.

## 3. Component by component

For each: what it is, why it exists, what breaks without it, how to change it.

### Orchestration (`src/orchestration/`)

LangGraph state machine. `graph.py` wires the nodes, `nodes.py` holds them,
`state.py` is the typed dict passed between them, `llm.py` picks the model
per tier through OpenRouter, `events.py` is the Postgres LISTEN/NOTIFY event
log, `checkpointer_setup.py` creates the tables LangGraph uses to save state
mid-run.

Why a state machine instead of one long prompt: each step is a named node
with a typed input and output, so you can test a node alone, see in the
audit log which node did what, and resume a run from a checkpoint if the
process dies. Why Postgres for events instead of a broker: the envelope is
about a hundred messages a day per company. A queue product would be a
second system to run for no gain.

To add a node: write the function in `nodes.py`, add its outputs to
`state.py`, wire it in `graph.py`, and log an audit row inside it. Nothing
else needs to know.

### Tools (`src/tools/`)

`discount_logic.py` is the pure policy function. No database, no model.
`db_lookups.py` fetches the rows it needs and calls it, and holds
`get_invoice_status`, the one read the status reply may state facts from.
`resolver.py` maps a message to an invoice. `execution.py` is
the one writer. `scribo_client.py` talks to a third-party invoicing product
and maps to no requirement in the PRD; it will go when it gets in the way.

Why the split between logic and lookups: the pure function can be tested
with no infrastructure (see `tests/test_money_path.py`), and the same
function is used both when a claim first arrives and when it is executed
later, so the two can never disagree.

### Guardrails (`src/guardrails/`)

`audit.py` writes the immutable trace. `cost_tracker.py` prices every model
call. `caps.py` is checked before every model call: calls and spend per
workflow, spend per day; over the line raises and the graph escalates to a
human with the reason. `tool_allowlist.py` says which tools each
model-backed agent may be given, and today that is none. `policy_gate.py`
holds the role rank check and the revalidation entry point.
`pii_redaction.py` is the regex redactor. `injection_tests.py` feeds
hostile emails through the graph and asserts nothing executes.

Why these are a folder of their own: they are the parts that must hold
even when a prompt is tricked. The design method we follow says only
capability limits stop an attack, not instructions. A model that has been
told "ignore your rules" still cannot call `execute_discount` if the code
never gives it that tool.

### Ontology (`src/ontology/`)

`schema.sql` is the schema as of 2026-09-08 and the baseline migration
runs it verbatim; every change after that is a numbered file under
`migrations/versions/`, applied with `alembic upgrade head`. Never edit
`schema.sql` for a change; write a migration. `db.py` is the one place that
reads `DATABASE_URL`. `sync_graph.py` mirrors companies and contracts into Neo4j
for the trading-loop check.

Why one connection helper: every query goes through it, so swapping the
connection string, adding pooling, or pointing tests at a fake is one
change. Neo4j is on the drop list; section 4 says why.

### Ingestion (`src/ingestion/`)

`gmail_oauth.py` is the real Gmail API client. `gmail_intake.py` is the
poll loop. `document_extraction.py` reads an invoice PDF into fields with a
vision-capable model.

Why email first: the counterparty does not have to install anything for
the product to be useful on day one. The signed agent-to-agent channel is
added when both sides run the product; email keeps working underneath.

### API and UI (`src/api/`, `frontend/`)

`main.py` is the FastAPI app, `auth.py` is the login with a server-signed
session cookie, `queries.py` is the read-only SQL behind the pages. The
Jinja templates in `src/api/templates/` are the first UI. The React app in
`frontend/` is the Lovable design and will be the only UI.

Why the approver identity comes from the session and not the form: a
security audit found the role was a form field anyone could edit. The
approve endpoint now trusts only what the server put in the cookie.

The pair routes (`/api/pairs`, invite, accept, settings) and the `/pairs`
page in the React app are the company home screen. Every read and write
is scoped to the signed-in approver's company inside the SQL, so a wrong
pair id changes zero rows. An approver with no pair of their own is the
company's pair admin and sees all of its pairs; one with a pair sees that
pair. The one switch on a pair today decides whether status replies are
sent or drafted. Money-moving replies are never sent by the agent.

Every other JSON read is scoped the same way: the signed-in company sees
its counterparties, its invoices in both directions, and the audit and
cost of its own workflows. `MY_WORKFLOWS_SQL` in `queries.py` is the one
definition of "my workflows" and every scoped query embeds it. Signed out
returns empty, never the network. `docs/market/day-in-the-life.md` is the
reasoning behind which screens exist.

### MCP server (`src/mcp_server/`)

Exposes the grounded discount check as a tool an outside agent could call.
It is not on the hot path. It exists to prove the policy check can be
offered to other agents without exposing execution.

### Tests (`tests/`)

`test_money_path.py` runs with no Postgres and no API key. Each test names
a bug that was found and why the behaviour matters. Run them with
`python -m unittest tests.test_money_path`. The rule for new tests: the
docstring says why, and the test must fail if the business rule changes.

### Evaluation (`evals/`)

`golden_set.jsonl` is fifty messages a person labelled: the intent, the
invoice it is about, and the rate it claims. `python -m evals.run` sends
each through the same prompt and schema the graph uses, scores the three
reads, prints the failures with the labeller's note, and writes a results
file. The rule: change a prompt, run this, compare with the run before.
Misses that land on "other" are acceptable, because "other" goes to a
human. Misses that land on an autonomous class are not.

### Continuous integration (`.github/workflows/ci.yml`)

Every push runs two jobs. Backend: lint for syntax errors and undefined
names, the offline tests, then a migration of an empty Postgres, the seed,
and the four database-backed checks. Frontend: type-check and build. No
step calls a model. A red commit means one of those broke, and the log
says which. There is no deploy step yet; hosting is on the roadmap.

## 4. Things we chose not to do

- **No RAG.** The facts are rows in the system of record and they change
  hourly. A retrieved document about the contract is stale by definition;
  the row is not.
- **No message broker.** See orchestration above. Add one when the
  envelope is a hundred times larger.
- **No agent-decided numbers.** See section 1.
- **No global approvers.** Approvers belong to one side of one pair. Since
  2026-09-08 the `approver` row carries a company and a pair, and
  `execute_discount` refuses an approver from any other company or a pair
  that is not active. The invite flow that creates pairs is not built yet.
- **Neo4j, being removed.** It answers one question, "is the seller in a
  trading loop of four hops or less", and Postgres answers that with a
  recursive query at our size. A second database is a second thing to
  secure and back up. It comes back if the network grows to thousands of
  companies and we start asking richer graph questions.

## 5. How to bring in a change

Whether it comes from you, a reviewer, or an AI:

1. Name the pain or the lever it serves. If it does not map to a PRD
   requirement or a listed pain, it goes to the Improvements section of the
   roadmap, not into the code.
2. Put it on the board with a one-line why.
3. Ask "what happens when this is wrong". If the answer involves money or
   a bank detail, the change goes through the policy function or execution
   tool, never through a prompt.
4. Write the test that fails without the change.
5. Update the PRD status table, this guide if a component changed shape,
   and BRAIN.md if a decision was made.
6. Commit and push. One change, one commit.

## 6. Words we use

- **Pair.** One A-to-B relationship with its own everything.
- **Grounding.** Checking a claim from free text against the rows in the
  system of record.
- **Contested middle.** Cases the policy cannot settle by itself; the only
  ones a human sees.
- **Envelope.** The size we design for: about a hundred messages a day per
  company, three model calls per message, about $1.50 a day.
- **Lever.** One of the five things that shape a design: scale, latency,
  freshness, error cost, budget. The PRD tags each requirement with one.
- **Workflow id.** The one id that links audit rows, cost rows, events,
  and the proposal for a single case.
