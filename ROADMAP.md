
## Production readiness

Decided 2026-09-08: the target is a public demo site and a publishable
working setup, not a laptop prototype. The shape stays small: one web
process, one worker process, one Postgres. No Kubernetes, no broker.

Keep: Python, FastAPI, LangGraph + Postgres checkpointer, Postgres 16,
Docker, the React frontend under `frontend/`.
Drop: Neo4j (cycle check becomes a recursive query in Postgres), the Jinja
UI (the React app is the demo).

In order:

1. Alembic migrations; the seed script stops owning the schema.
2. CI on GitHub Actions: unit tests, ruff, docker build, injection suite.
3. Pin dependencies with a lock file.
4. Worker process for mailbox polling and graph runs; Postgres queue with
   SKIP LOCKED.
5. Structured JSON logs with workflow id; Sentry; Langfuse or OpenTelemetry
   for LLM traces.
6. Rate limits on login and intake; daily LLM spend kill switch (R16).
7. Company-scoped approvers (R8); per-agent tool allowlist (R17).
8. Demo mode flags: seeded data, no real mailbox, drafts only, reset button,
   hard daily budget.
9. Hosting: API + worker on Fly.io or Railway, Postgres on Neon, frontend on
   Vercel or Cloudflare Pages.
ds.
5. **Guardrail gaps.** Company-scoped approvers (R8), per-workflow caps (R16),
   tool allowlist (R17). Why: turns "happens to be safe" into "cannot be
   unsafe".
6. **Update BRAIN.md with the 2026-09-07 decisions.**
   Why: it is the history doc and it still ends before the restart.

## Done

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
