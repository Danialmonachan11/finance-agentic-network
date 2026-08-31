# Finance Agentic Network

A multi-agent finance-ops platform: LangGraph orchestration, Postgres +
Neo4j, real Gmail intake, a propose/execute approval split, and
prompt-injection resistance testing — modeling a *network* of companies
trading with each other, not a fixed single-operator setup.

## The one workflow this proves end-to-end

```
Gmail inbox → Intake/Triage → Document Extraction → Finance Validation
  → Discount/Policy Agent (Neo4j-grounded) → Risk Agent (scoring only)
  → propose_discount() → human approval → execute → audit log
```

Every step is logged and traced. Every money-adjacent decision is
**propose-then-approve, never direct execution** — an LLM reads and drafts,
a deterministic function decides. That split is the core architectural
point of the whole build.

## What's real, not mocked

- **LangGraph orchestration** (`src/orchestration/graph.py`) — a real
  `StateGraph` with dynamic routing: non-discount intent skips straight to
  escalation, a grounded rejection skips risk-scoring and drafting entirely,
  a high-risk-but-eligible claim auto-declines instead of reaching a human.
- **Grounding, enforced structurally, not by convention.** The LLM's read
  of a claimed discount rate is recorded but never trusted — a
  deterministic function (`ground_decision`, zero LLM calls) independently
  re-derives eligibility from Postgres (contract status, rate ceiling,
  remaining budget) before anything happens.
- **Neo4j as a genuine multi-hop question**, not a decorative sync target —
  real trading-cycle detection (`TRADES_WITH*2..4`) across the company
  network feeds into risk scoring.
- **Real Gmail intake** — OAuth2, read + compose scopes only (no send
  scope in the base design), idempotent processing, real draft creation.
- **Zero-trust execution** — `execute_discount` re-validates eligibility
  and re-checks role-rank authorization every time it's called, even
  against its own prior output. Verified with a real 10-thread concurrency
  test (exactly 1 wins a race, 9 see a safe no-op) and defense-in-depth
  checks (a full-authority approver still gets blocked by an expired
  contract).
- **Prompt-injection resistance** — four adversarial email bodies run
  through the real orchestration graph with real LLM calls
  (`src/guardrails/injection_tests.py`). Each held for a different reason:
  deterministic rate clamping, unused fake fields, intent-based routing
  before extraction, and an out-of-band approver parameter that ignores
  any authority claimed in email text.
- **Cost tracking, PII redaction, rate limiting, session auth, CSRF
  resistance** — see `BRAIN.md` for the full security audit and what each
  one closes.

## Architecture

```
src/orchestration/   LangGraph supervisor + graph definition
src/agents/          specialist agent prompts/logic (thin — real logic lives in tools)
src/tools/           deterministic tool functions (the actual policy/calc logic)
src/ontology/        Postgres schema (SQL) + Neo4j schema/seed scripts
src/ingestion/       Gmail intake, document extraction (vision LLM)
src/guardrails/      audit log, policy gate, PII redaction, cost tracker, injection tests
src/api/             FastAPI app: approval endpoints, demo entry points
src/mcp_server/      a real MCP server wrapping the policy-lookup tools
data/seed/           sample companies, contracts, invoices
docs/architecture.md full 13-section design doc (reference — not all built, see BRAIN.md)
docs/demo_script.md  step-by-step walkthrough of the live demo
```

**Multi-LLM routing**: one OpenRouter key, cheap tier (Haiku) for
classification/extraction, strong tier (Sonnet) for narrative generation
and risk explanation — the number is always decided by code, never by the
model.

## Tech stack

Python · LangGraph · LangChain (OpenRouter-backed) · FastAPI · Postgres ·
Neo4j · MCP (`mcp` SDK) · PyMuPDF (vision-based document extraction) ·
Gmail API (OAuth2) · Jinja2

## Honest gaps

This is a scoped demo, not a finished product. Named directly, not hidden:

- Per-agent tool allowlisting and step/retry/cost limits are designed but
  not structurally enforced — any function can currently call any other.
- Document processing has no sandboxing for untrusted attachments.
- No multi-provider LLM fallback (both tiers are Claude, at different sizes).
- No automated evaluation harness for extraction/generation quality.
- External↔internal invoice-number reconciliation is a real unsolved
  matching problem, found by testing against a real generated invoice.

`BRAIN.md` has the full decision log, every real bug found and fixed
(most caught by actually clicking through the running app, not by reading
code), and the reasoning behind every architectural choice — the honest
version of "why," not the polished one.

## Running it

See `BRAIN.md`'s "How to run" section for the full setup (Docker Compose
for Postgres + Neo4j, seed data, environment variables, Gmail OAuth setup).
Short version:

```bash
docker compose up -d
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
python -m data.seed.seed
python -m src.ontology.sync_graph
python -m src.orchestration.graph          # runs the full workflow against 4 seeded invoices
python -m uvicorn src.api.main:app --port 8000
```

Needs `OPENROUTER_API_KEY` in `.env` (see `.env.example`). Gmail intake
additionally needs a Google Cloud OAuth client (Desktop app type).
