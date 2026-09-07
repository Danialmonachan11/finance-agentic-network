# Folding the Lovable build into the plan

Supersedes and extends `05-plan.md`. Read that first, this only covers what changes.

## What's real UI work vs what's new backend behavior

Checked against `src/api/main.py` and `src/api/queries.py` before planning anything, per the "read before you write" rule. Two of the Lovable screens imply behavior this app doesn't have yet.

**Already supported, template-only work:**
- Nav-based approval queue with a live pending count. `list_pending_proposals_for_seller` already exists (`queries.py:171`). This is routing plus a badge, no new query.
- Decisions log splitting auto vs human path. `executed` rows already carry `approved_by` (`queries.py:241`), a human name or an automated actor. Rendering that as a "path" badge is a template change, not a data change.

**Genuinely new backend work, smaller than first estimated:**
- A Decline action on a pending proposal. Grepped `main.py` for `/decline` and `/reject`, zero matches. Only `POST /proposals/{id}/approve` exists (`main.py:340`). Checked `schema.sql:68-69` afterward, `discount_proposal.status` already allows `'rejected'`, no migration needed, this was wrong in an earlier draft of this doc.
- What's actually needed: a new `POST /proposals/{id}/decline` route, same auth/session shape as the existing approve route, that sets `status='rejected'`, `approved_by` to the signed-in approver, `decided_at` to now, on the existing row.
- One real gotcha, found by reading `nodes.py` before writing this: `propose()` (`nodes.py:204-210`) sets `workflow_id` on every normal pending proposal at creation, the same field `auto_reject()` (`nodes.py:162-168`) sets on its own rows. `list_auto_rejected_for_seller` (`queries.py:215-238`) currently distinguishes auto-rejections from other rejected rows by `workflow_id IS NOT NULL` alone (`queries.py:231`). Once a human decline exists, a declined row would also satisfy that condition and show up misclassified as an auto-rejection. `auto_reject()`'s INSERT never sets `approved_by` (`nodes.py:164-167` omits the column), a human decline would. Fix: add `AND dp.approved_by IS NULL` to `queries.py:231`'s WHERE clause as part of the same change that adds the decline route, not a separate cleanup later.
- Companies-as-cards showing receivable/payable totals. Grepped `queries.py`, zero matches for `payable`/`receivable`. Nothing currently aggregates a company's open exposure in either direction. This is a new query, not a new card component.

## Revised phase order

Phase 1 (design tokens) and Phase 2 (shared components) from `05-plan.md` are unaffected, build those regardless of which direction wins.

**Phase 3 changes.** The original plan reordered sections within one page. The Lovable build's stronger move is promoting the approval queue to its own route with a persistent nav badge, visible from every page instead of buried in a scroll position on one page. Adopting that supersedes the original single-page reorder, and it's a routing change, not just a template change: a new `/companies/{id}/queue` view (or similar), a badge count wired into `base.html`'s nav for whichever company the signed-in approver belongs to.

**New Phase 3b: proposal detail view.** A master-detail pattern, click a queue row, see the full picture (amount, contract status, due date, why it was escalated, the existing `grounding_reason`/`risk_reason` fields promoted to real prose instead of a squeezed table cell). All the data for this already exists in `_company_page_context`, this is presentation, not new data.

**New Phase 3c: decline endpoint.** `POST /proposals/{id}/decline`, mirrors the shape of the existing approve endpoint (`main.py:340`) for auth/session handling, sets `status='rejected'` on the existing column (no migration, `schema.sql:68-69` already allows that value), plus the `queries.py:231` filter fix above in the same change so auto-rejections and human declines stay distinguishable. Smaller than originally scoped, but still the one item in this redesign that touches query logic beyond the view layer, flagging it on its own rather than folding it in silently.

**Phase 4 (propagate pattern) gains one item:** the companies list becomes cards with receivable/payable, which needs the new aggregation query above before the template work can start.

**Phase 5 (copy pass) unaffected.**

## Palette decision, locked

Direction 1, confirmed by the user. Drop the reference-site navy/baby-blue palette from the original brief. Adopt the Lovable build's own system as the real token set: dark sidebar, warm cream content area, ink text, a single orange/rust accent, monospace type throughout. Phase 1 of `05-plan.md` gets rewritten against these values, not the original reference palette. That palette research stays in `01-evidence.md` as a record of what was considered, it just isn't what ships.

## Principles that shaped this plan

`principle-experience-first` decided the queue-as-its-own-page adoption. A badge visible from every screen beats a scroll position on one screen, for the person actually using this daily, that's worth the extra routing work.

`principle-model-the-domain` is why the decline endpoint got called out separately instead of quietly wired to a fake button. A UI element that implies a state transition the domain doesn't have yet is a UI lie until the backend catches up.

`principle-subtract-before-you-add` means Phase 3's single-page reorder gets replaced, not kept alongside the new nav-based queue. Shipping both would leave two ways to see the same to-do list.

`principle-laziness-protocol` is why this plan doesn't touch Lovable's React/TypeScript output at all. Porting a Vite/React scaffold into a FastAPI/Jinja2 server-rendered app is a bigger rewrite than anyone asked for, extracting the IA and component decisions and reimplementing them natively is the smaller, correct move.

`principle-never-block-on-the-human` is why everything above got decided and written down instead of asked about, except the palette, which is a real preference call no amount of my judgment settles for you.
