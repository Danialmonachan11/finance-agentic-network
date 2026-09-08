# Roadmap

The working board for the rebuild. One line per item, with the reason it is
on the list. Move items between sections as they change state; do not delete
finished ones. Requirement ids (R1..R21) refer to `docs/prd.md`.

Order inside "To do" is priority order.

## In progress

- (nothing)

## To do

1. **Remaining guardrail gaps.** Per-workflow caps (R16), per-agent tool
   allowlist (R17). Why: turns "happens to be safe" into "cannot be unsafe".
2. **Update BRAIN.md with the 2026-09-07 decisions.**
   Why: it is the history doc and it still ends before the restart.

## Done

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
- Golden set of 50 real-shaped messages for the intent classifier, before
  anyone tunes a prompt.
- Approvers are created by the seed script only. A pair admin should be
  able to name approvers for their side from the `/pairs` page (R20).
- The `/companies` pages still show every company. They are the old
  bird's-eye view and go when the Jinja UI goes.

## Production readiness

Decided 2026-09-08: the target is a public demo site and a publishable
working setup, not a laptop prototype. The shape stays small: one web
process, one worker process, one Postgres. No Kubernetes, no broker.

Keep: Python, FastAPI, LangGraph + Postgres checkpointer, Postgres 16,
Docker, the React frontend under `frontend/`.
Drop: Neo4j (cycle check becomes a recursive query in Postgres), the Jinja
UI (the React app is the demo).

In order:

1. Alembic migrations; the seed script stops owning the schema. (The pair
   table was applied to the demo database by hand on 2026-09-08; this is
   the last time that should happen.)
2. CI on GitHub Actions: unit tests, ruff, docker build, injection suite.
3. Pin dependencies with a lock file.
4. Worker process for mailbox polling and graph runs; Postgres queue with
   SKIP LOCKED.
5. Structured JSON logs with workflow id; Sentry; Langfuse or OpenTelemetry
   for LLM traces.
6. Rate limits on login and intake; daily LLM spend kill switch (R16).
7. Per-agent tool allowlist (R17).
8. Demo mode flags: seeded data, no real mailbox, drafts only, reset button,
   hard daily budget.
9. Hosting: API + worker on Fly.io or Railway, Postgres on Neon, frontend on
   Vercel or Cloudflare Pages.
