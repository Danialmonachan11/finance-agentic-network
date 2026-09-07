# Plan: wire the agents/automation page to real data

Goal: `frontend/src/routes/agents.tsx` stops rendering hardcoded numbers from `fan-data.ts` and shows what the system has actually done.

## Phase 0: Documentation discovery (done this session)

Read `agents.tsx` in full and every field it consumes from `fan-data.ts`'s `automation`, `automationTrend`, `models`, `evals` exports. Two real gaps found, not assumed:

- **`ModelRow.p50_latency_ms` / `p95_latency_ms` / `agreement_rate` / `sampled`** have no backing data anywhere. `llm_call_cost` (schema.sql:111-120) has no duration/latency column and no human-agreement sampling mechanism exists in this codebase at all. These are not "missing a query", they're **not measurable** without new instrumentation, which is explicitly out of scope (no schema changes).
- **The entire `evals` concept** (an eval-suite pass/fail tracker) has zero backing. No evals table, no eval-runner code, nothing. This section cannot become real without building an eval framework from scratch, a different, much larger project than "wire this page to real data."
- **Current copy is actively wrong**: `agents.tsx:79` says requests were "approved or declined by the pipeline alone." The real backend never auto-approves, only `auto_reject()` runs without a human (`src/orchestration/nodes.py`). Shipping real numbers under this copy would make an honest page say something false.

Decision, not deferred to the implementer: drop the latency/agreement columns and the entire evals section from the live page rather than fake them or leave them silently static. Relabel "handled without a human" to reflect what's actually true (auto-declined vs human-decided), not implied auto-approval.

## Phase 1: backend endpoint

**What to implement**, `GET /api/automation?days=30` in `src/api/main.py`, wrapping new query functions in `src/api/queries.py`, following the exact pattern already used for every other `/api/*` route added this session (see `docs/design/lovable/09-frontend-integration-plan.md` Phase 1-2):

1. `count_decisions_in_window(days)`: over `discount_proposal` rows with `created_at >= now() - interval '%s days'`, count total, count `status='rejected' AND workflow_id IS NOT NULL AND approved_by IS NULL` (auto-declined, the exact discriminator already used in `list_auto_rejected_for_seller`), count `approved_by IS NOT NULL` (human-decided, whether approved or declined), count `status='proposed'` (still pending).
2. `weekly_decision_trend(days)`: same split, grouped by ISO week (`date_trunc('week', created_at)`), for the week-by-week bars.
3. `model_usage_summary(days)`: from `llm_call_cost`, grouped by `model`, real columns only: `count(*)` as calls, `sum(input_tokens)`, `sum(output_tokens)`, `sum(estimated_cost_usd)`. No latency, no agreement_rate, no error_rate, those columns don't exist in this table.
4. Reuse `get_network_cost_summary()` for the window-total spend figure rather than re-deriving it, it already exists and is already exposed via `/api/audit`.

Response shape: `{decided_or_pending: {total, auto_declined, human_decided, still_pending}, weekly: [{week, auto_declined, human_decided}], models: [{model, calls, tokens_in, tokens_out, cost_usd}], network_cost: {...}}`.

**Verification**: live against the real dev DB, cross-check the auto_declined/human_decided counts against a direct `SELECT ... GROUP BY` run manually in Postgres, same discipline as every backend phase already merged this session. Confirm the numbers are non-fabricated by comparing to what `/api/proposals`, `/api/executed`, and `/api/audit` already independently report for overlapping data (e.g. total decided should be consistent with executed + auto-declined counts elsewhere).

## Phase 2: frontend wiring

**What to implement**, in `agents.tsx`:

1. Replace `automation`/`automationSummary()`/`automationTrend` static usage with a `useQuery` against `/api/automation`.
2. Replace `models` static usage with the same response's `models` array. Remove the columns that have no real data: `p50_latency_ms`, `p95_latency_ms`, `agreement_rate`, `sampled` (and their table headers). Don't render an empty/dash column for something structurally unmeasurable, remove the column.
3. Remove the entire `evals` section and its import. If the page's layout looks sparse without it, that's honest, don't backfill with something else invented to fill the space.
4. Fix the copy at `agents.tsx:79` (and anywhere else making the same claim) from "approved or declined by the pipeline alone" to something accurate, e.g. "auto-declined by the pipeline alone" for the auto path, since that's what's actually true today. Keep `reviewer_hourly_cost_usd`/`minutes_per_manual_review` as a small local config object (real assumption inputs, not fabricated data), with the existing `InfoTip` pattern disclosing exactly how the savings figure is derived from them, same honesty standard already used elsewhere in this app.
5. Loading and error states matching every other page wired this session.

**Verification**: real numbers rendered, cross-checked against the same live Postgres query used in Phase 1's verification, not just "the page loads." Confirm `tsc --noEmit` is clean given the type/field removals.

## Anti-patterns to guard against

- Inventing a plausible-looking number for latency, agreement_rate, or evals because the UI has a slot for it. If it's not measurable, the slot goes away.
- Leaving "approved or declined by the pipeline alone" copy in place because fixing prose feels out of scope for a "wire to real data" task, the honesty of the page depends on this line specifically.
- Re-deriving network-wide cost totals instead of reusing `get_network_cost_summary()`, which already exists and is already correct.
