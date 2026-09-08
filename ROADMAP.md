# Roadmap

The working board for the rebuild. One line per item, with the reason it is
on the list. Move items between sections as they change state; do not delete
finished ones. Requirement ids (R1..R21) refer to `docs/prd.md`.

Order inside "To do" is priority order.

## In progress

- (nothing)

## To do

1. **Seller-side chase.** Kessler's own "where is my payment" going out to
   Nordwind, by email now and agent-to-agent once both sides run the
   product. Why: `day-in-the-life.md`, 16:00; the first place the network
   pays off.
2. **Bank-change verification task.** A queue item that names the contact
   on file and records the phone check (R11). Why: today a bank change only
   escalates by name; the control that stops the fraud is the call.
3. **Name approvers from the Pairs page.** (R20) Why: seeded only today.

## Done

- 2026-09-08 Evaluation set: 50 real-shaped messages with known intent,
  invoice, and rate in `evals/golden_set.jsonl`; `python -m evals.run`
  scores the classifier, the resolver, and the rate extractor and writes a
  results file per run. First run: intent 82%, every miss was ordinary mail
  called a status inquiry. One prompt change, re-run: 96%, resolver and
  rate 100%. The two remaining misses fall to "other", which is the safe
  side. Why: nobody should change a prompt without a number before and
  after.
- 2026-09-08 Migrations and CI: Alembic with a baseline migration that runs
  `schema.sql`, the compose file no longer loads the schema, the demo
  database is stamped; GitHub Actions runs lint, offline tests, a migration
  of an empty Postgres, seed, and the database checks on every push, plus
  a frontend type-check and build. Why: two hand-applied schema changes in
  one day, and eighteen tests nobody ran automatically.
- 2026-09-08 BRAIN.md rebuild entry: the ten steps of the restart and where
  the working docs live now.
- 2026-09-08 Caps and allowlist (R16, R17): `guard_llm_call` before every
  model call (calls and spend per workflow, spend per day), LangGraph step
  limit, cap hits escalate to a human with the reason; tool allowlist with
  every model-backed agent empty and a test that fails if a tool is ever
  bound. Why: only capability limits stop a runaway or a tricked agent.
- 2026-09-08 Every screen is the signed-in company's view: companies are
  me plus my counterparties with counts relative to me, invoices are mine
  with a payable/receivable direction, executed, audit, agent activity, and
  cost cover my workflows only, and the old Companies overview redirects to
  Pairs. Signed out means empty, never the network. Why: Alice must see
  what her own agent is doing, not a bird's-eye view. Grounded in
  `docs/market/day-in-the-life.md`.
- 2026-09-08 Pair setup flow (R19, R21, R5 switch): invite and accept over
  `/api/pairs`, only the invited side can accept, a per-pair switch that
  turns status replies from drafts into sends, `/pairs` home screen in the
  React app scoped to the signed-in company. Not built: naming approvers
  through the UI (they are seeded), caps and channel config on the pair.
  Why: the product is deployed per pair, so the pair needed a real
  lifecycle before anything else could hang off it.
- 2026-09-08 Status-inquiry path in shadow mode (R1..R5): four intents,
  `src/tools/resolver.py` matches sender company plus number or amount,
  `answer_status` phrases only the invoice row's facts, draft never sent,
  bank changes escalate by name (R10). Verified live against OpenRouter and
  the seeded data. Why: the first read-only autonomous path, and it forced
  the classifier and resolver every later feature needs.
- 2026-09-08 Decided: buyer side first, mid-market; Postgres is the system
  of record for v1 behind one read adapter. Logged in the PRD ledger.
- 2026-09-08 Pair table and pair-scoped execution (R8, R19, R20 in part).
  `pair` row per company pair, approvers carry company and pair, execution
  refuses an approver from another company or a pair that is not active,
  pending lists and decline are scoped to the approver's side. Seven
  offline tests. Why: approver scoping is now the data model, not a rule.
- 2026-09-08 Bank-detail change sequence diagram (`docs/diagrams/bank-change`).
  Why: the P3 story, email refused and signed still gated, had no picture.
- 2026-09-08 Builder's guide at `docs/builder-guide.md`. Why: the owner
  needs to know why each piece exists to judge changes, not only that it
  exists.
- 2026-09-08 Product model regroup: the unit of deployment is a pair of
  companies, not a company or a network. BRAIN.md entry, PRD v0.2 (section
  2a, R19 to R21), architecture and status-inquiry diagrams redrawn. Why:
  the PRD had been written from the code, and the code was a platform view
  the user never wanted.
- 2026-09-08 Four money-path bugs fixed (R6..R9): revalidation checks the
  executed proposal's own rate; rates outside (0, 1] rejected; `escalate`
  only rejects its own workflow's proposal; contract-less invoice is a
  rejection, not a crash. `tests/test_money_path.py` runs with no Postgres
  and no API key: `python -m unittest tests.test_money_path`. Why: money
  code the PRD keeps, and the first thing a reviewer stops on.
- 2026-09-07 Market research: `docs/market/ap-ar-primer.md`,
  `docs/market/pain-points-network.md`. Why: we did not know the process or
  the vendors before designing anything.
- 2026-09-07 PRD v0.1 at `docs/prd.md`. Why: one rebuild target instead of
  eleven design docs.
- 2026-09-07 Repo trimmed and reorganised; Lovable design kept under
  `docs/design/lovable/`. Why: clutter from three earlier tooling passes.
- 2026-09-07 Four diagrams in `docs/diagrams/` (architecture, status
  inquiry, claim lifecycle, PII data flow). Why: the PRD needed pictures for
  the three network pains and the trust boundary.
- 2026-09-07 Commit-and-push after every change. Why: earlier work sat
  uncommitted for a whole session.

## Improvements

Things that would be better but do not block the list above.

- Rate limiting on the mailbox poller so a mail storm cannot blow the daily
  LLM budget (R16 covers the cap; this is the front door).
- Replace the regex PII redactor with a proper detector once real customer
  text is in scope (R18).
- Retire the Jinja templates and the Scribo invoice generator when they get in
  the way. Neither maps to a PRD requirement.
- Approvers are created by the seed script only. A pair admin should be
  able to name approvers for their side from the `/pairs` page (R20).
- The Jinja pages under `/companies` still show every company. They are
  the old bird's-eye view and go when the Jinja UI goes. The JSON API and
  the React app are already scoped.

## Production readiness

Decided 2026-09-08: the target is a public demo site and a publishable
working setup, not a laptop prototype. The shape stays small: one web
process, one worker process, one Postgres. No Kubernetes, no broker.

Keep: Python, FastAPI, LangGraph + Postgres checkpointer, Postgres 16,
Docker, the React frontend under `frontend/`.
Drop: Neo4j (cycle check becomes a recursive query in Postgres), the Jinja
UI (the React app is the demo).

In order:

1. Evaluation in CI: a manual workflow that runs `evals.run` with a real
   key and posts the scores, so a prompt change shows its number on the
   pull request.
2. Pin dependencies: a Python lock file, and a package-lock.json for the
   frontend (there is none today, so CI installs whatever is newest).
3. Worker process for mailbox polling and graph runs; Postgres queue with
   SKIP LOCKED.
4. Structured JSON logs with workflow id; Sentry; Langfuse or OpenTelemetry
   for LLM traces.
5. Rate limits on login and intake.
6. Demo mode flags: seeded data, no real mailbox, drafts only, reset button,
   hard daily budget.
7. Hosting: API + worker on Fly.io or Railway, Postgres on Neon, frontend on
   Vercel or Cloudflare Pages.
