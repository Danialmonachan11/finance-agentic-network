# Plan: wire frontend up as the real, live frontend

Goal: the Lovable-built React app at `frontend/` stops being a static design reference and becomes the actual UI, talking to real FastAPI endpoints, with live updates via the event bus that already exists in this codebase.

## Phase 0: Documentation discovery (done this session)

**CORSMiddleware** (`starlette.middleware.cors.CORSMiddleware`, the actual installed signature, checked via `inspect.signature`, not docs):
```
CORSMiddleware(app, allow_origins=(), allow_methods=('GET',), allow_headers=(),
               allow_credentials=False, allow_origin_regex=None,
               allow_private_network=False, expose_headers=(), max_age=600)
```
Cookie-based auth across origins needs `allow_credentials=True` plus an explicit `allow_origins` list (a `credentials: true` response can't pair with a wildcard `*` origin per the CORS spec, Starlette enforces this). `allow_methods` needs `["GET", "POST"]` at minimum since this app uses both.

**StreamingResponse** (`starlette.responses.StreamingResponse`, actual installed signature):
```
StreamingResponse(content, status_code=200, headers=None, media_type=None, background=None)
```
`content` accepts a sync or async generator/iterable. For SSE, `media_type="text/event-stream"` and each yielded chunk formatted as `f"data: {json.dumps(payload)}\n\n"` is the standard framing (a blank line terminates each event per the SSE spec).

**Unresolved, must observe empirically in Phase 1, don't guess:** `frontend/vite.config.ts` delegates port/host selection to `@lovable.dev/vite-tanstack-config`'s own "sandbox detection," no fixed port is set in this repo. The CORS `allow_origins` value can't be written until the dev server has actually been run once and its real origin observed.

## Phase 1: JSON API layer on FastAPI (read-only routes first)

**What to implement**, in `src/api/main.py`, alongside the existing HTML routes (don't remove or modify any existing route in this phase):
- `GET /api/companies` → `list_companies()`, same function the HTML `/companies` route already calls.
- `GET /api/companies/{company_id}` → the same data `_company_page_context()` assembles, minus the `request`/`approver` HTML-only fields, as a plain JSON dict.
- `GET /api/proposals` → `list_pending_proposals()`.
- `GET /api/invoices` → `list_all_invoices()`.
- `GET /api/executed` → `list_executed_proposals()`.
- `GET /api/audit` → whatever `/ops` currently assembles (`list_recent_workflows()`, `get_network_cost_summary()`), as JSON.
- `GET /api/me` → the current session's approver (`current_approver(request)`), or `null`, so the frontend knows if it's signed in without guessing from cookie presence alone.

Each of these wraps an existing query function, zero new business logic. Run the dev server, run the Vite dev server once (`cd frontend && bun install && bun dev`), observe and record its actual origin/port for Phase 2's CORS config.

**Verification:** `curl` or `TestClient` against every new route, confirm real JSON matching the field names already used in `frontend/src/lib/fan-data.ts`'s types (that's the whole point of those types mirroring the backend, confirm the mirror actually holds, don't assume it still does after months of the backend evolving).

**Anti-pattern guard:** don't paginate, filter, or reshape data in these routes beyond what the existing HTML routes already do, that's frontend work (Phase 4), not this phase's job.

## Known gaps from Phase 1, carried forward to Phase 4

Checked `fan-data.ts`'s TypeScript types field-by-field against the real Phase 1 responses. Two safe key renames (`created_at`→`requested_at`, `decision`/`occurred_at`→`status`/`timestamp`) were fixed directly in the `/api/*` route handlers, not the underlying queries. Three real gaps remain, deliberately not built ahead of need:

- **`Company.slug`** doesn't exist server-side, the real identity is a UUID `id`. Decision: Phase 4 changes the frontend's `/company/$slug` routing to use `id`, the backend does not grow a slug concept it doesn't otherwise have.
- **`InvoiceRow.has_pdf` / `discount_status` / `emailed`** are missing from `list_all_invoices()`. `has_pdf` is already computed elsewhere in `main.py` via `INVOICE_PDF_DIR`; `discount_status`/`emailed` already exist in the per-company `list_company_invoices()` query via a `LATERAL` join. Extending `list_all_invoices()` with the same pattern is real, small work, do it when Phase 4 actually needs it for the invoices page, not before.
- **`ExecutedRow.path` ("human"/"auto")** assumes an auto-execution path that doesn't exist in this domain today. `execute_discount` always records a real human's `approved_by`; `auto_reject` only auto-declines, nothing auto-approves. Every real executed row is currently "human". This is a product question for the user (should the pipeline ever auto-execute a low-risk discount without human sign-off, or should the frontend just always show "human" and drop the distinction), not a data-mapping bug to quietly work around.

## Phase 2: CORS + the mutating routes (approve, decline, invoice, request, poll)

**What to implement:**
- Add `CORSMiddleware` to `src/api/main.py` with `allow_origins=[<the real Vite origin observed in Phase 1>]`, `allow_credentials=True`, `allow_methods=["GET", "POST"]`.
- `POST /api/proposals/{id}/approve` and `POST /api/proposals/{id}/decline` — same auth check as the existing HTML routes (`current_approver(request)`, 401/redirect-equivalent if not signed in), same underlying `execute_discount`/`decline_proposal` calls, JSON body/response instead of a form redirect.
- **Add the missing `publish_event(..., "workflow.declined", {...})` call inside `decline_proposal`** (`src/api/queries.py`) as part of this phase, not deferred, since Phase 3's SSE stream is only complete once declines are visible in it too.
- `POST /api/companies/{id}/invoice` → same Scribo+Gmail flow the HTML route triggers.
- `POST /api/companies/{id}/request` → same `run_workflow` trigger. This call can take real wall-clock time (LLM calls in the pipeline), return the `workflow_id` immediately rather than blocking for the full pipeline result, the frontend follows progress via the Phase 3 SSE stream, not by waiting on this response.
- `POST /api/login` / `POST /api/logout` → same session-cookie mechanism as today, JSON request/response instead of form/redirect.
- `POST /api/intake/poll` → same Gmail-poll trigger.

**Verification:** a real signed-in session via `TestClient` (cookie jar persists across calls) exercising approve, decline, and confirming a `workflow_event` row now exists for a decline (query Postgres directly, same pattern used to verify Phase 3c/3+3b of the redesign work).

## Phase 3: SSE endpoint

**What to implement:** `GET /api/events/stream`, optionally accepting `?since_id=` for catch-up:
1. Call `replay_events(since_id)` and yield each as an SSE `data:` line immediately (catch-up).
2. Bridge `events.listen()`'s background-thread callback into the async generator `StreamingResponse` consumes (a thread-safe queue is the standard pattern: `listen()` runs in a thread, pushes to a `queue.Queue`, the async generator polls that queue and yields).
3. `media_type="text/event-stream"`.

**Verification:** open the stream (`curl -N` or a short-lived Python client), independently trigger a real event from another process (e.g. call `decline_proposal` directly, or hit `POST /api/proposals/{id}/decline`), confirm the stream actually delivers it within a couple seconds. This is the one phase where "the code looks right" isn't enough, prove the live path end to end before the frontend depends on it.

## Phase 4: wire the frontend to real data (read paths)

**What to implement**, in `frontend/src`:
- An API client module (fetch wrapper with `credentials: 'include'` baked in, base URL from an env var, not hardcoded).
- Replace `fan-data.ts`'s static array exports with `useQuery` calls against Phase 1's endpoints, in each route file (`queue.tsx`, `company.$slug.tsx`, `invoices.tsx`, `executed.tsx`, `audit.tsx`, `index.tsx`). Keep `fan-data.ts`'s TypeScript interfaces (`Company`, `PendingRequest`, etc.) if Phase 1's verification confirmed they still match, that's the reuse this whole design already earned.
- Loading and error states for each query (the redesign's own Rams audit flagged missing loading states as a real gap, don't repeat that here on the "real" frontend).

**Verification:** run both processes together, load every page in a real browser or via a headless check, confirm real seeded data renders (not the hardcoded demo numbers currently in `fan-data.ts`), confirm it changes if the underlying Postgres data changes (e.g. after Phase 2's decline test).

## Phase 5: wire the frontend to real actions (write paths) + live updates

**What to implement:**
- `useMutation` for Approve, Decline, invoice generation, and discount-request submission, each calling Phase 2's endpoints, invalidating the relevant query on success (TanStack Query's standard pattern).
- The login page posts to `/api/login`, redirects into the app on success, relies on the cookie for everything after, no token storage.
- An SSE-consuming hook (`EventSource` or a manual fetch-stream reader) subscribed to Phase 3's endpoint, updating the queue/audit views as events arrive, not only on next refetch. Given `queue.tsx`'s existing `useState`-based decided-locally UX is being replaced, verify decisions now genuinely persist across a page reload (the strongest proof the mock behavior is actually gone).

**Verification:** click through the real UI, approve one real seeded proposal, reload the page, confirm it's gone from the queue and present in executed history, confirm the audit/live view showed the event without a manual refresh.

## Final phase: full sweep + cutover decision (not executed here)

1. Every page in `frontend` loads real data and every action performs a real mutation, verified together in one session, both processes running.
2. Grep for any remaining reference to `fan-data.ts`'s static arrays being used instead of a live query, confirm none remain.
3. Write down, but do not act on, the cutover decision: whether/when the Jinja2 HTML routes get retired now that a live equivalent exists. That's explicitly out of scope for this plan, flag it for the next one.
