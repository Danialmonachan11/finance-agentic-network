# Roadmap

The working board for the rebuild. One line per item, with the reason it is
on the list. Move items between sections as they change state; do not delete
finished ones. Requirement ids (R1..R18) refer to `docs/prd.md`.

Order inside "To do" is priority order.

## In progress

- (nothing)

## To do

1. **Decide buyer-side vs seller-side (PRD open question 3).**
   Why: it picks the first customer, the first metric, and who the
   counterparty is in every diagram. Recommendation: buyer side, mid-market.
2. **Decide ERP strategy for v1 (PRD open question 2).**
   Why: integration is the biggest cost and not the product. Recommendation:
   Postgres is the system of record for v1, one read-adapter interface so a
   real ERP can slot in later.
3. **Fix the four money-path bugs, with offline tests.** (R6..R9)
   Revalidation reads the wrong proposal; no floor on the extracted rate;
   `escalate` rejects sibling proposals; contract-less invoices crash the
   graph. Why: they are in code the PRD keeps, and they are the first thing a
   reviewer stops on. Tests must run with no Postgres and no API key.
4. **Draw the bank-detail change flow.** (P3)
   Why: the only pain where the network is categorically safer, not just
   faster, and it has no diagram yet.
5. **Build the status-inquiry path, shadow mode.** (R1..R5)
   Real intent classifier (four intents), resolver on counterparty + amount +
   reference, drafts only. Why: read-only, no money moves, and it forces the
   two pieces every later feature needs.
6. **Harness gaps.** Company-scoped approvers (R8), per-workflow caps (R16),
   tool allowlist (R17). Why: turns "happens to be safe" into "cannot be
   unsafe".
7. **Update BRAIN.md with the 2026-09-07 decisions.**
   Why: it is the history doc and it still ends before the restart.

## Done

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
