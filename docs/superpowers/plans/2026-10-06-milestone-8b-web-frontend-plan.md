# Implementation Plan: Milestone 8B Web Frontend

**Spec:** `docs/superpowers/specs/2026-10-06-milestone-8b-web-frontend-design.md`
**ADRs:** `docs/adr/0010-web-story-mode-and-session-source-preferences.md`, `docs/adr/0009-juya-story-mode-and-digest-presentation-metadata.md`
**Created:** 2026-10-06
**Goal scope:** One goal: ship the Vue app in `frontend/` against a `/api/v1` contract that already carries every field the approved prototype needs. The additive backend slice (F1-F7) is sequenced first because the frontend binds to its OpenAPI output.

## Summary

Phase 1 (B1-B8) extends the Python API additively: message and session metadata, structured progress, Hugging Face base model, history topics, GitHub `stars_today`, and fake-mode fixtures that exercise every new field. Phase 2 (T1-T12) builds `frontend/` from the generated client: scaffold, tokens and theme, SSE and lifecycle logic, view-models, then one UI section per pass (layout first, motion second). No SQLite migration, no change to CLI, Gradio, or OpenClaw output, no auth or deployment, no semantic search.

## Discovery notes

- Reuse: `api/routers/sessions.py` builds every response through `_session_out` (4 call sites) and `_message_out`; `_chat_event_payload` maps typed chat events to SSE payloads. Extend these, do not add parallel builders.
- Reuse: `DigestStore.get_connector_warnings_for_run(run_id)` and `get_digest_by_run_id(run_id)` already exist. `digests` rows carry both `id` and `run_id`, so `digest_id` is a lookup, not a new column.
- Reuse: `services/digest_views.py` (`extract_huggingface_evidence`, `extract_github_evidence`) is the single evidence-to-view projection. Connector evidence already stores `base_model` (`connectors/huggingface.py`) and owner fields.
- Reuse: `github_previews.py` is the pattern for F7: bounded unauthenticated GET, concurrency/size/redirect limits, non-fatal `ConnectorWarning`. `GitHubConnector` gates it with `preview_enrichment`, enabled only for live in `sources.py`.
- Reuse: `HistorySearchMatch` is built in `history_search._candidate_to_match`, and the candidate row already has `digest_topics`. The model has no `topics` field yet, so F6 touches `history.py` too (additive default).
- Reuse: per-source progress is a string pipeline. `collect.py` emits formatted lines (`Calling X…`, `Done X: Found n X result(s).`, `Tool failed X: collection failed.`) and chat.py forwards them as `ProgressEvent(stage=…)`. Gradio and the tool agent consume the same strings.
- Constraint: `FakeGitHubConnector` returns a bare item with no evidence, and the fake HF connector has no owner or base model. Fake Juya already supports story mode. Spec acceptance 1 (every screen works in fake mode) needs fixture enrichment.
- Constraint: the OpenAPI document is the client source. The backend slice must be done and its schema checked before the client is generated.
- Constraint: markdown rendering (`rendering.py`) and history scoring stay unchanged. Existing GitHub, HF, and API tests keep passing.
- Patterns to follow: Pydantic DTOs with `extra="ignore"` on views; additive nullable fields; tests in the existing `tests/test_api_*.py`, `test_digest_views.py`, `test_connectors_github.py` files; workspace TDD rule (RED then GREEN per behavior).
- Anti-goals: no drive-by refactors; do not change the progress tuple pipeline `(progress, done, payload)`; do not touch `rendering.py`; do not expose raw `source_evidence`; do not add a Juya toggle; do not port `motion/react`.

## File map

### Goal A: Backend prerequisite slice (Phase 1)

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|---|---|---|---|---|
| `src/ai_news_agent/api/schemas/sessions.py` | modify | Add `MessageOut.digest_id`, `MessageOut.warnings`, `SessionOut.digest_count`, `SessionOut.active_request_id` | Pydantic models | verified |
| `src/ai_news_agent/api/schemas/streaming.py` | modify | Add `DigestPayload.digest_id`; optional `ProgressPayload.source/status/count` | Pydantic models | verified |
| `src/ai_news_agent/api/schemas/digests.py` | modify | Add `HuggingFaceDigestEntryView.base_model`, `GitHubDigestEntryView.stars_today` | Pydantic models | verified |
| `src/ai_news_agent/api/schemas/history.py` | modify | Add `HistorySearchMatchOut.topics` | Pydantic model | verified |
| `src/ai_news_agent/api/routers/sessions.py` | modify | Populate new message, session, and SSE fields | existing routes | verified |
| `src/ai_news_agent/api/routers/history.py` | modify | Pass `topics` through | existing route | verified |
| `src/ai_news_agent/repositories/digest_store.py` | modify | `get_digest_id_for_run(run_id) -> int \| None` | method | verified |
| `src/ai_news_agent/repositories/session_store.py` | modify | Per-session digest count and active request id for listed and single sessions | methods (names set in B2) | verified |
| `src/ai_news_agent/progress.py` | modify | Structured progress parse helper kept beside the formatter contract | `parse_connector_progress(line)` | provisional (home may move to `graph/nodes/collect.py` next to the formatters) |
| `src/ai_news_agent/graph/nodes/collect.py` | modify | Expose formatter/parse pair so they cannot drift | existing formatters | verified |
| `src/ai_news_agent/history.py` | modify | `HistorySearchMatch.topics: list[str] = []` | model | verified |
| `src/ai_news_agent/history_search.py` | modify | Fill `topics` from `candidate["digest_topics"]` | `_candidate_to_match` | verified |
| `src/ai_news_agent/services/digest_views.py` | modify | Project `base_model`, `stars_today` | extractors | verified |
| `src/ai_news_agent/github_trending.py` | create | Fetch and parse `github.com/trending?since=daily`, join `stars_today` into evidence | `parse_trending_stars_today(html)`, `enrich_github_stars_today(items, client=)` | verified (mirrors `github_previews.py`; separate 2 MB streamed cap) |
| `src/ai_news_agent/connectors/github.py` | modify | Opt-in trending enrichment after previews; non-fatal warning | `GitHubConnector(trending_enrichment=)` | verified |
| `src/ai_news_agent/sources.py` | modify | Enable trending for live GitHub; enrich fake GitHub and fake HF fixtures | connector wiring | verified |
| `tests/test_api_sessions.py` | modify | Message and session fields, SSE digest and progress payloads | pytest | verified |
| `tests/test_digest_bundle.py` | modify | `get_digest_id_for_run` | pytest | verified |
| `tests/test_session_store.py` | modify | Digest count and active request id queries | pytest | verified |
| `tests/test_digest_views.py` | modify | `base_model`, `stars_today` projection | pytest | verified |
| `tests/test_history_search.py` | modify | Match carries digest topics | pytest | verified |
| `tests/test_api_history.py` | modify | `topics` on the HTTP result | pytest | verified |
| `tests/test_connectors_github.py` | modify | Trending enrichment behavior | pytest | verified |
| `tests/test_github_trending.py` | create | Trending HTML parsing, fetch bounds, and warning behavior | pytest | verified |
| `tests/fixtures/github_trending_daily_sample.html` | create | Offline excerpt of the daily trending page for parser tests | fixture | verified |
| `tests/test_sources.py` | modify | Fake fixtures expose new evidence; live GitHub enables trending while fake stays offline | pytest | verified |
| `README.md` | modify | Document new fields in the local web API section | docs | verified |

### Goal B: Frontend (Phase 2), all under `frontend/` (all paths provisional)

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|---|---|---|---|---|
| `frontend/package.json`, `vite.config.ts`, `tsconfig*.json`, `index.html`, `components.json` | create | Vite + Vue 3 + TS + Tailwind + shadcn-vue + Vitest scaffold; pre-paint theme script | npm scripts `dev`, `build`, `typecheck`, `test`, `gen:api` | provisional |
| `frontend/src/api/generated/` | create | OpenAPI-generated types and client | generated | provisional |
| `frontend/src/api/sse.ts` | create | POST SSE reader over `fetch` + `ReadableStream`, frame parser | `parseSseStream`, `postMessageStream` | provisional |
| `frontend/src/api/lifecycle.ts` | create | Request state machine, cancel, reconnect polling | `createRequestLifecycle` | provisional |
| `frontend/src/vm/` | create | `Vm` types, `toVm` mappers, `toVmFromFixture`, fixtures | pure functions | provisional |
| `frontend/src/stores/` | create | session, thread, composer, history, theme stores | Pinia stores | provisional |
| `frontend/src/styles/tokens.css`, `motion.css` | create | Verbatim prototype tokens and literal keyframes | CSS | provisional |
| `frontend/src/components/**` | create | shell, sidebar, chat head, thread, digest, composer, history, hover card | Vue components | provisional |
| `frontend/src/assets/sources/*` | create | Source logos copied from the prototype project | assets | provisional |

### Blast radius

| Path | Why sensitive | Behavior that must stay intact | Plan mode |
|---|---|---|---|
| `api/routers/sessions.py` (`_message_out`, `_session_out`, `_chat_event_payload`) | Every transcript and stream response | Existing fields, ordering, status codes; old clients ignore additive fields; replay SSE unchanged | high |
| `graph/nodes/collect.py`, `progress.py`, `services/chat.py` | Progress strings feed Gradio, the tool agent, and the stream | String lines unchanged byte for byte; `stage` still sent | high |
| `connectors/github.py` | Live collect path, rate limits | Search results, warnings, README enrichment, and previews unchanged when trending is off or fails | high |
| `history.py`, `history_search.py` | Shared by CLI, tools, OpenClaw history, HTTP | Scoring, refs, and rendered history text unchanged; `topics` defaults to `[]` | medium |
| `repositories/session_store.py` | Session list used by every sidebar load | Ordering and cursor behavior; no N+1 per listed session | medium |
| `sources.py` fake connectors | Used by many offline tests | Existing assertions on fake item ids and counts | medium |
| `rendering.py`, history scoring | Easy to touch by accident | No change at all | skip |

## Workflow (for implementers)

1. **writing-plans** produced this file (type-1 decomposition only).
2. Per subtask: **Plan mode** + **planning-subtasks** → type-2 plan when **Plan mode** is `high` (or `medium` with a real remaining unknown).
3. **Agent mode**: **test-driven-development** when `TDD suitable: yes` (or the testable slice of `partial`). Stub-first only for new modules such as `github_trending.py`.
4. Finish **B1-B8** before **T1**. T2 and T3 may run in parallel after T1. UI sections follow the order below; each is one pass, layout then motion (T11).
5. Update this document if reality diverges; add a **Plan changelog** row.

## Subtasks

Dependency notation: `Blocked by: B1` means start after B1 is done.

### Phase 1: Backend prerequisite slice

### B1 — Digest message metadata (F1 + F2)

- [x] **Do:** Expose the digest id and persisted connector warnings for digest messages and the live digest event.
- **Consumes:** `DigestStore.get_connector_warnings_for_run(run_id)`; `digests.id`/`digests.run_id`; `_message_out`; `DigestPayload`.
- **Produces:** `DigestStore.get_digest_id_for_run(run_id) -> int | None`; `MessageOut.digest_id: int | None`; `MessageOut.warnings: list[ConnectorWarning]` (empty list when none); `DigestPayload.digest_id: int` on the SSE `digest` event.
- **Acceptance:** A digest assistant message returns its `digest_id` and the warnings saved for its run. User messages and non-digest assistant messages return `null` and `[]`. A reloaded transcript shows the same warnings the live `digest` event carried. Replay SSE `digest` includes `digest_id`. `GET /messages` for a pre-existing digest with no warnings returns `[]`, not an error.
- **Compatibility:** All existing `MessageOut` and SSE fields unchanged.
- **Blocked by:** —
- **Plan mode:** skip
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_digest_bundle.py tests/test_api_sessions.py -q`

### B2 — Session digest count and active request (F3)

- [x] **Do:** Add per-session `digest_count` and `active_request_id` to every session response.
- **Consumes:** `session_requests` (status, run_id), `SessionRecord`, `_session_out`.
- **Produces:** `SessionOut.digest_count: int`, `SessionOut.active_request_id: str | None`; store query returning both for one or many sessions in a single pass.
- **Acceptance:** `digest_count` counts only `succeeded` requests that have a `run_id`; failed, cancelled, interrupted, and follow-up-only requests do not count. `active_request_id` is set only while a request is `active` and `null` after any terminal status or startup interruption. `GET /sessions` computes both without a query per session. Create, get, patch, and list return the same shape.
- **Compatibility:** Session ordering, cursors, and the 409 busy rules unchanged.
- **Blocked by:** —
- **Plan mode:** medium (named unknown: single-pass SQL vs a small aggregate query; decide against the existing `SessionStore` API)
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_session_store.py tests/test_api_sessions.py -q`

### B3 — Structured progress fields (F4)

- [x] **Do:** Add optional `source`, `status`, `count` to the SSE `progress` event while keeping `stage` exactly as sent today.
- **Consumes:** the formatters in `collect.py` (`Calling {name}…`, `Done {name}: Found {n} {name} result(s).`, `Tool failed {name}: collection failed.`); `ProgressEvent`; `_chat_event_payload`.
- **Produces:** `parse_connector_progress(line) -> tuple[source, status, count | None] | None` kept beside the formatters; `ProgressPayload.source: str | None`, `status: "running" | "done" | "failed" | None`, `count: int | None`.
- **Acceptance:** `Calling X…` gives `running`; `Done X: Found n …` gives `done` with `count=n` (singular and plural forms); `Tool failed X…` gives `failed`. Non-connector lines (`Parsing request…`, `Ranking candidates…`, `Collecting from sources…`) give all three fields `null` and still send `stage`. A round-trip test builds each line with the formatter and parses it, so a wording change fails the test. The Gradio and tool-agent strings are unchanged.
- **Compatibility:** `(progress, done, payload)` tuple pipeline and `stage` text unchanged.
- **Blocked by:** —
- **Plan mode:** high (shared string contract used by Gradio and the tool agent; parse vs thread structure must be settled against `chat.py` and `interface_router.py`)
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_chat.py tests/test_api_sessions.py -q` and a grep that no caller of the progress strings changed.

### B4 — Hugging Face base model (F5)

- [x] **Do:** Project the stored `base_model` on Hugging Face digest entries.
- **Consumes:** `source_evidence["base_model"]` from `connectors/huggingface.py`; `extract_huggingface_evidence`.
- **Produces:** `HuggingFaceDigestEntryView.base_model: str | None`.
- **Acceptance:** A representative with `base_model` evidence returns it; missing or blank returns `null`; the family representative's value wins (not an `Also` variant's). Old saved digests return `null`.
- **Blocked by:** —
- **Plan mode:** skip
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_digest_views.py tests/test_connectors_huggingface.py -q`

### B5 — History result topics (F6)

- [x] **Do:** Return the digest-level topics on each history search match.
- **Consumes:** `candidate["digest_topics"]` in `_candidate_to_match`; `HistorySearchMatch`.
- **Produces:** `HistorySearchMatch.topics: list[str]` (default `[]`); `HistorySearchMatchOut.topics: list[str]`.
- **Acceptance:** A match from a digest with topics returns them in saved order; a digest without topics returns `[]`. Topic filtering, scoring, refs, ordering, and rendered history text are identical to before.
- **Compatibility:** CLI, OpenClaw history text, and tool outputs unchanged.
- **Blocked by:** —
- **Plan mode:** skip
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_history_search.py tests/test_api_history.py tests/test_history.py -q`

### B6 — GitHub stars today (F7)

- [x] **Do:** Collect `stars_today` from GitHub's daily trending page and project it on GitHub digest entries.
- **Consumes:** `github_previews.py` fetch bounds (short timeout, redirect limit, off-host check); `GitHubConnector.collect`; `extract_github_evidence`.
- **Produces:** `github_trending.parse_trending_stars_today(html) -> dict[str, int]` (full name to count); `enrich_github_stars_today(items, client=) -> (items, warnings)`; evidence key `stars_today`; `GitHubConnector(trending_enrichment: bool = False)`; `GitHubDigestEntryView.stars_today: int | None`.
- **Fetch bounds:** the trending page is one whole HTML document, not one small repo page, so response size is capped separately at `TRENDING_MAX_RESPONSE_BYTES = 2_000_000` and enforced while streaming. The 5-second timeout and 3-redirect limit carry over from `github_previews.py`. The observed daily page was 585,999 bytes, which exceeds the 512,000-byte preview cap. `PREVIEW_MAX_CONCURRENT` does not apply: one page per collect.
- **Acceptance:** Parsing handles thousands separators, ignores "this week" and "this month" rows, and tolerates extra whitespace and missing rows. A collected repo on the page gets `stars_today`; one absent from the page stays `null`. A failed or oversized fetch adds one non-fatal warning and returns items unchanged. One trending GET per collect, regardless of item count. The default connector and all existing tests make no extra request. Names match case-insensitively. Stars-today never overwrites `stars` or changes ranking.
- **Compatibility:** `rendering.py` output, CLI, Gradio, and OpenClaw text unchanged.
- **Blocked by:** —
- **Plan mode:** high (scrapes a public HTML page; confirm selectors and the exact "stars today" text against a saved fixture before writing the parser)
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_github_trending.py tests/test_connectors_github.py tests/test_digest_views.py -q`

### B7 — Fake-mode presentation fixtures

- [x] **Do:** Make fake connectors return the new evidence so every UI feature is visible offline.
- **Consumes:** B4 `base_model`, B6 `stars_today`, existing owner and preview evidence keys; `FakeGitHubConnector`, `FakeHuggingFaceConnector`, `FakeJuyaConnector`.
- **Produces:** fake GitHub items with owner (org and person), `stars`, `language`, `preview_image_url`, `stars_today`; fake HF items with owner and one `base_model`; fake Juya issue cover and lead (stories already supported).
- **Acceptance:** A fake-mode digest over all sources returns non-null values for each new field and at least one null case per field (for example one repo without `stars_today`). Fake mode makes no network call. Existing fake-item ids and counts still satisfy current tests.
- **Compatibility:** `tests/test_sources.py` and fake end-to-end tests keep passing.
- **Blocked by:** B4, B6
- **Plan mode:** medium (named unknown: which existing tests pin fake item shapes)
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_sources.py tests/test_api_sessions.py -q`

### B8 — Contract check and docs

- [x] **Do:** Prove the final OpenAPI document contains F1-F7 and document the fields.
- **Consumes:** B1-B7.
- **Produces:** README local web API section updated; a test that the OpenAPI schema contains each new property; a full-suite green run.
- **Acceptance:** `GET /openapi.json` lists `digest_id`, `warnings`, `digest_count`, `active_request_id`, the progress fields, `base_model`, `stars_today`, and history `topics`. README describes them and notes which are nullable. The full offline suite passes with no network.
- **Blocked by:** B1, B2, B3, B4, B5, B6, B7
- **Plan mode:** skip
- **TDD suitable:** partial (the schema-presence test is test-first; README is verified by reading)
- **TDD suitable reason:** docs have no automated check.
- **Verification:** `uv run pytest -q`

### Phase 2: Frontend

### T1 — Scaffold `frontend/` and generated client

- [ ] **Do:** Create the Vite + Vue 3 + TypeScript + Tailwind + shadcn-vue + Vitest app, env config, and the OpenAPI client generation script.
- **Consumes:** B8 final `/openapi.json`; `VITE_API_BASE_URL` (default `http://127.0.0.1:8765`); CORS allowlist for `:5173`.
- **Produces:** runnable `npm run dev` on `:5173`; `npm run gen:api` writing `src/api/generated/`; `typecheck`, `test`, `build` scripts; the pre-paint theme script in `index.html` (`anra-theme`).
- **Acceptance:** Dev server loads a blank shell and a single call to `GET /api/v1/health` succeeds from the browser against `ai-news-agent service --fake` with no CORS error. Generated types include the F1-F7 fields. The repo `.gitignore` covers `frontend/node_modules` and build output.
- **Blocked by:** B8
- **Plan mode:** high (generator and package manager unchosen; shadcn-vue + Tailwind versions to verify)
- **TDD suitable:** no
- **TDD suitable reason:** scaffolding and generated code have no behavior to specify first.
- **Verification:** `npm --prefix frontend run typecheck` and `npm --prefix frontend run build`; manual health check in the browser.

### T2 — Tokens, theme, and app shell layout

- [ ] **Do:** Port the token blocks and the shell grid, breakpoints, and dock measurement; implement theme state and the circular reveal.
- **Consumes:** prototype lines 12-51 (tokens), 92-93, 380-410 (layout), 597-627 (theme).
- **Produces:** `styles/tokens.css`; `AppShell`, theme store `useTheme()` with `setTheme(next, {user, point})`.
- **Acceptance:** Light and dark values match the prototype tokens verbatim. Theme persists under `anra-theme`, follows the OS only while no stored choice exists, and is applied before first paint. The reveal runs 600 ms from the pointer or the control, and falls back to an instant switch with reduced motion or no `startViewTransition`. Layout matches the prototype at 1280, 1024, 800, and 400 px (history and sidebar become overlays at the specified breakpoints).
- **Blocked by:** T1
- **Plan mode:** medium (named unknown: Tailwind v-next token mapping without default shadcn chrome)
- **TDD suitable:** partial
- **TDD suitable reason:** theme storage and OS-follow rules are testable logic; layout and the reveal are verified against the OpenDesign preview.
- **Verification:** `npm --prefix frontend run test -- theme`; browser comparison at the four widths.

### T3 — SSE reader and request lifecycle

- [ ] **Do:** Implement the POST SSE frame parser, the request state machine, cancel, and reconnect polling.
- **Consumes:** the generated client; SSE contract (`started`, `progress`, `delta`, `digest`, `done`, `error`); `GET .../requests/{id}`; cancel 202/204; 409 codes.
- **Produces:** `parseSseStream(readable)`, `postMessageStream(sessionId, body)`, `createRequestLifecycle(...)` emitting states `idle | streaming | reconnecting | succeeded | failed | cancelled`.
- **Acceptance:** Parser handles frames split across chunks, several events per chunk, CRLF, and ignores unknown events. `delta` replaces text (cumulative, never appended). Cancel 202 waits for the terminal `cancelled` error; 204 triggers a status poll and shows the real outcome. A dropped stream enters `reconnecting`, polls with backoff up to 5 attempts, and on a terminal status reloads messages; exhaustion ends in `failed` with Run again. A 409 `session_busy` or `request_in_progress` surfaces the blocked state. The byte stream is never reopened.
- **Blocked by:** T1
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `npm --prefix frontend run test -- sse lifecycle`

### T4 — View-model layer

- [ ] **Do:** Define `Vm` types and `toVm` mappers; convert the prototype data into fixtures for visual comparison.
- **Consumes:** generated types; spec "Digest reply" and gap table; prototype `JUYA`, `HF`, `GH`, `HIST` data.
- **Produces:** `toVm(apiEntry)`, session, message, request, history, and warning mappers; `toVmFromFixture(raw)` used only by fixtures and the visual-compare route.
- **Acceptance:** Nulls are omitted without empty labels. Avatar choice is image, person initials, or neutral tile. Juya stories group under one issue cover by `issue.id` with no issue number. Entries group into contiguous source sections with the continuous `display_rank` range. GitHub meta line is `language · stars ★ · +N today` with any null part dropped. HF rows carry `base_model` and variants. Only `http(s)` URLs pass through. No production module imports a fixture.
- **Blocked by:** T1
- **Plan mode:** medium (named unknown: how to detect section boundaries when kinds interleave)
- **TDD suitable:** yes
- **Verification:** `npm --prefix frontend run test -- vm`

### T5 — Sessions store and sidebar

- [ ] **Do:** Port the sidebar: list, grouping, search, new conversation reuse, rename, delete confirm, backend status.
- **Consumes:** T2 shell, T4 session mappers, B2 fields, `GET /sessions`, `/sessions/search`, `PATCH`, `DELETE`, `POST /sessions`, `/health`.
- **Produces:** `useSessions()` store and `Sidebar` components.
- **Acceptance:** List paginates by cursor. Null title shows "New conversation" in the empty style. "N digests" and "Running" come from `digest_count` and `active_request_id`. New conversation reuses an existing empty session and flashes it. Rename saves on submit and cancels on Escape. Delete confirm uses `role="alertdialog"` and a `409 session_busy` keeps the session and explains why. Search shows excerpts and match kind. FAKE badge and status line follow `/health.fake`.
- **Blocked by:** T2, T4, B2
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** store behavior (reuse-empty, busy delete) is testable; styling is compared in the browser.
- **Verification:** `npm --prefix frontend run test -- sessions`; browser comparison of the sidebar.

### T6 — Thread, digest reply, and hover card

- [ ] **Do:** Port the chat head, thread, user bubble, markdown reply, and digest reply with source sections, Juya cover and stories, GitHub entries, HF table, and the preview hover card.
- **Consumes:** T4 view-models, B1 `digest_id` and `warnings`, B4, B6; spec digest reply rules.
- **Produces:** `Thread`, `DigestReply`, `EntryRow`, `HfTable`, `JuyaIssueCover`, `HoverPreview`, and a sanitized markdown renderer.
- **Acceptance:** Header shows `dN`, time, item count, and "X of Y sources returned results" from warnings. Warning alerts render per connector. Hover or focus preview appears after 400 ms, hides on scroll and Escape, and uses only `preview_image_url`. Markdown is sanitized and links use `rel="noopener"`. A reloaded digest looks identical to the live one (same `dN`, same warnings). Layout matches the prototype; motion is added in T9.
- **Blocked by:** T4, T2, B1
- **Plan mode:** medium (named unknown: markdown sanitizer choice)
- **TDD suitable:** partial
- **TDD suitable reason:** sanitizing and section rendering rules are testable; spacing and type are compared in the browser.
- **Verification:** `npm --prefix frontend run test -- digest`; browser comparison against the OpenDesign preview using fixtures, then against fake mode.

### T7 — Run progress, terminal states, and reconnect UI

- [ ] **Do:** Port the run card, segmented bar, cancelled, failed, interrupted, and reconnecting banner, wired to the lifecycle.
- **Consumes:** T3 lifecycle, B3 structured progress, T6 thread.
- **Produces:** `RunCard`, `CancelledReply`, `FailedReply`, `InterruptedReply`, `ReconnectBanner`.
- **Acceptance:** Per-source steps and bar update from `source/status/count`; with those fields absent the card falls back to the `stage` line. Digest runs show "Writing digest" with shimmer and no delta text. Follow-up runs show cumulative markdown with the caret and sheen. Cancelled shows how many sources finished when known. Interrupted and failed show the safe message with Run again, which only refills the composer. `role="progressbar"` and live regions match the spec.
- **Blocked by:** T3, T6, B3
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** the step reducer and fallback are testable; visuals are compared in the browser.
- **Verification:** `npm --prefix frontend run test -- run`; manual run against `ai-news-agent service --fake` including cancel and a forced stream drop.

### T8 — Composer

- [ ] **Do:** Port the composer: textarea, source checkboxes, per-source stepper, validation, busy and blocked notices, Cancel.
- **Consumes:** T3, T5, `PATCH /sessions/{id}`, `GET /sources`.
- **Produces:** `Composer` and `useComposer()`.
- **Acceptance:** Enter sends, Shift+Enter inserts a newline, IME composition does not send. Validation covers empty text, no source, and count outside 1-20, with the backend-aligned copy. Changing sources or count PATCHes the session preferences. Every send includes `juya_item_mode: "stories"` and a new `client_request_id`. During a request the inputs and Send are disabled and Cancel shows. A 409 shows the blocked notice. "Ask a follow-up" and suggestions prefill the composer.
- **Blocked by:** T3, T5
- **Plan mode:** skip
- **TDD suitable:** yes
- **Verification:** `npm --prefix frontend run test -- composer`

### T9 — History panel

- [ ] **Do:** Port the history panel with filters, results, opened result, and empty states.
- **Consumes:** B5 `topics`, `GET /history/search`, `GET /history/{token}`, T4 mappers, T6 entry component.
- **Produces:** `HistoryPanel`.
- **Acceptance:** With no criteria the panel shows the idle prompt and makes no request. Filters map to `text`, `sources`, `topics`, `since`, `until`. Count line shows results and filters, plus `caveats` and truncation. Opening a result renders `entry` with the shared entry component, or `markdown` when `entry` is null, and never changes the conversation. 400 messages show inline. Overlay and scrim behavior matches the breakpoints.
- **Blocked by:** T6, B5
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** the no-criteria rule and filter mapping are testable; layout is compared in the browser.
- **Verification:** `npm --prefix frontend run test -- history`; browser check with fake-mode history.

### T10 — Motion and accessibility pass

- [ ] **Do:** Port all keyframes literally and finish the accessibility and reduced-motion behavior.
- **Consumes:** prototype keyframes (`rise`, `fadeIn`, `collapse`, `sheen`, `segrun`/`segdone`, `stripes`, `shimmer`, `blink`, `spin`, `flash`); T5-T9 components.
- **Produces:** `styles/motion.css` and component hooks; cleanup on unmount.
- **Acceptance:** Durations, easing, delays, and stagger (capped at index 8) match the prototype. `prefers-reduced-motion` follows the prototype reduce block. Keyboard flow, focus ring, roles, `aria-live`, and `aria-current` match the spec. No timer or observer leaks after navigating between sessions.
- **Blocked by:** T5, T6, T7, T8, T9
- **Plan mode:** skip
- **TDD suitable:** no
- **TDD suitable reason:** motion and visual polish are verified by browser comparison, per the spec.
- **Verification:** Browser compare against the OpenDesign preview; keyboard-only walkthrough; reduced-motion emulation.

### T11 — End-to-end smoke and acceptance

- [ ] **Do:** Run the whole UI against the fake backend and check each spec acceptance item.
- **Consumes:** everything above.
- **Produces:** a short acceptance note in this plan's changelog; a Playwright (or equivalent) smoke test only if T1 added a runner.
- **Acceptance:** Spec acceptance 1-5 hold: all screens work offline in fake mode; a page reload during a running request recovers the outcome without reopening the stream; themes and the reveal match; layouts match at 1280, 1024, 800, 400 px; Gradio, CLI, and OpenClaw tests are unchanged and pass.
- **Blocked by:** T10
- **Plan mode:** skip
- **TDD suitable:** no
- **TDD suitable reason:** acceptance verification of the assembled app.
- **Verification:** `uv run pytest -q`, `npm --prefix frontend run test`, `npm --prefix frontend run build`, plus the manual checklist.

## TDD note (Agent mode)

Per subtask, obey `TDD suitable`: `yes` means strict RED/GREEN (scoped `uv run pytest -k` or `vitest -t`); `partial` applies it only to the logic slice and uses browser comparison for layout and motion; `no` uses the stated Verification. B3 and B6 are the riskiest backend subtasks: plan them in Plan mode first. Layout fidelity has no TDD cycle.

## Plan changelog

| Date | Change | Kind |
|---|---|---|
| 2026-10-06 | Initial plan. Backend slice (B1-B8) ordered before the frontend (T1-T11) | — |
| 2026-10-06 | B1 also adds `digest_id` to the SSE `digest` event (spec F1 said `MessageOut` only); the `dN` ref is needed before any reload. Spec F1 row patched to match | equivalent |
| 2026-10-06 | Added B7 (fake-mode fixtures): fake GitHub and HF connectors carry no presentation evidence, so spec acceptance 1 could not be met without it | equivalent |
| 2026-10-09 | B6 uses a separate streamed 2,000,000-byte cap; observed daily page is 585,999 bytes. Keep 5-second timeout/3 redirects and add offline HTML fixture | material (approved) |
