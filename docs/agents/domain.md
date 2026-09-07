# Domain docs

**Layout: single-context.** One `CONTEXT.md` at the repo root, one
`docs/decisions/adr/` at the repo root. No monorepo signals in this project (single
Python service, no `packages/*`), so multi-context (a `CONTEXT-MAP.md`
pointing at several per-package `CONTEXT.md` files) doesn't apply.

## Consumer rules

- Read `CONTEXT.md` before making a change that touches domain
  entities/terminology (company, contract, invoice, discount_proposal,
  workflow) — it's the canonical vocabulary, not `docs/reference/architecture.md`
  (that's the broader 13-section reference design, not all of it built) or
  `BRAIN.md` (that's the project's running log of status/decisions, useful
  for "why," not "what things are called").
- Check `docs/decisions/adr/` for a relevant decision record before re-deciding
  something structural (storage split, event pattern, auth boundary) that
  may already have a recorded rationale.
- `CONTEXT.md` and `docs/decisions/adr/0001-network-model-not-hub-and-spoke.md` were
  written 2026-08-25 via the `domain-modeling` skill. Keep both current as
  the model changes — `domain-modeling` is the active discipline for that,
  this file just records where they live.
