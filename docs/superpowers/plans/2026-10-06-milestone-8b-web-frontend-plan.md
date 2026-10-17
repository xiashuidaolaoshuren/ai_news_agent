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

- [x] **Do:** Create the Vite + Vue 3 + TypeScript + Tailwind + shadcn-vue + Vitest app, env config, and the OpenAPI client generation script.
- **Consumes:** B8 final `/openapi.json`; `VITE_API_BASE_URL` (default `http://127.0.0.1:8765`); CORS allowlist for `:5173`.
- **Produces:** runnable `npm run dev` on `:5173`; `npm run gen:api` writing `src/api/generated/`; `typecheck`, `test`, `build` scripts; the pre-paint theme script in `index.html` (`anra-theme`).
- **Acceptance:** Dev server loads a blank shell and a single call to `GET /api/v1/health` succeeds from the browser against `ai-news-agent service --fake` with no CORS error. Generated types include the F1-F7 fields. The repo `.gitignore` covers `frontend/node_modules` and build output.
- **Blocked by:** B8
- **Plan mode:** high (generator and package manager unchosen; shadcn-vue + Tailwind versions to verify)
- **TDD suitable:** no
- **TDD suitable reason:** scaffolding and generated code have no behavior to specify first.
- **Verification:** `npm --prefix frontend run typecheck` and `npm --prefix frontend run build`; manual health check in the browser.

### T2 — Tokens, theme, and app shell layout

- [x] **Do:** Port the token blocks and the shell grid, breakpoints, and dock measurement; implement theme state and the circular reveal.
- **Consumes:** prototype lines 12-51 (tokens), 92-93, 380-410 (layout), 597-627 (theme).
- **Produces:** `styles/tokens.css`; `AppShell`, theme store `useTheme()` with `setTheme(next, {user, point})`.
- **Acceptance:** Light and dark values match the prototype tokens verbatim. Theme persists under `anra-theme`, follows the OS only while no stored choice exists, and is applied before first paint. The reveal runs 600 ms from the pointer or the control, and falls back to an instant switch with reduced motion or no `startViewTransition`. Layout matches the prototype at 1280, 1024, 800, and 400 px (history and sidebar become overlays at the specified breakpoints).
- **Blocked by:** T1
- **Plan mode:** medium (named unknown: Tailwind v-next token mapping without default shadcn chrome)
- **TDD suitable:** partial
- **TDD suitable reason:** theme storage and OS-follow rules are testable logic; layout and the reveal are verified against the OpenDesign preview.
- **Verification:** `npm --prefix frontend run test -- theme`; browser comparison at the four widths.

### T3 — SSE reader and request lifecycle

- [x] **Do:** Implement the POST SSE frame parser, the request state machine, cancel, and reconnect polling.
- **Consumes:** the generated client; SSE contract (`started`, `progress`, `delta`, `digest`, `done`, `error`); `GET .../requests/{id}`; cancel 202/204; 409 codes.
- **Produces:** `parseSseStream(readable)`, `postMessageStream(sessionId, body)`, `createRequestLifecycle(...)` emitting states `idle | streaming | reconnecting | succeeded | failed | cancelled`.
- **Acceptance:** Parser handles frames split across chunks, several events per chunk, CRLF, and ignores unknown events. `delta` replaces text (cumulative, never appended). Cancel 202 waits for the terminal `cancelled` error; 204 triggers a status poll and shows the real outcome. A dropped stream enters `reconnecting`, polls with backoff up to 5 attempts, and on a terminal status reloads messages; exhaustion ends in `failed` with Run again. A 409 `session_busy` or `request_in_progress` surfaces the blocked state. The byte stream is never reopened.
- **Blocked by:** T1
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `npm --prefix frontend run test -- sse lifecycle`

### T4 — View-model layer

- [x] **Do:** Define `Vm` types and `toVm` mappers; convert the prototype data into fixtures for visual comparison.
- **Consumes:** generated types; spec "Digest reply" and gap table; prototype `JUYA`, `HF`, `GH`, `HIST` data.
- **Produces:** `toVm(apiEntry)`, session, message, request, history, and warning mappers; `toVmFromFixture(raw)` used only by fixtures and the visual-compare route.
- **Acceptance:** Nulls are omitted without empty labels. Avatar choice is image, person initials, or neutral tile. Juya stories group under one issue cover by `issue.id` with no issue number. Entries group into contiguous source sections with the continuous `display_rank` range. GitHub meta line is `language · stars ★ · +N today` with any null part dropped. HF rows carry `base_model` and variants. Only `http(s)` URLs pass through. No production module imports a fixture.
- **Blocked by:** T1
- **Plan mode:** medium (named unknown: how to detect section boundaries when kinds interleave)
- **TDD suitable:** yes
- **Verification:** `npm --prefix frontend run test -- vm`

### T5 — Sessions store and sidebar

- [x] **Do:** Port the sidebar: list, grouping, search, new conversation reuse, rename, delete confirm, backend status.
- **Consumes:** T2 shell, T4 session mappers, B2 fields, `GET /sessions`, `/sessions/search`, `PATCH`, `DELETE`, `POST /sessions`, `/health`.
- **Produces:** `useSessions()` store and `Sidebar` components.
- **Acceptance:** List paginates by cursor. Null title shows "New conversation" in the empty style. "N digests" and "Running" come from `digest_count` and `active_request_id`. New conversation reuses an existing empty session and flashes it. Rename saves on submit and cancels on Escape. Delete confirm uses `role="alertdialog"` and a `409 session_busy` keeps the session and explains why. Search shows excerpts and match kind. FAKE badge and status line follow `/health.fake`.
- **Blocked by:** T2, T4, B2
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** store behavior (reuse-empty, busy delete) is testable; styling is compared in the browser.
- **Verification:** `npm --prefix frontend run test -- sessions`; browser comparison of the sidebar.

### T6 — Thread, digest reply, and hover card

- [x] **Do:** Port the chat head, thread, user bubble, markdown reply, and digest reply with source sections, Juya cover and stories, GitHub entries, HF table, and the preview hover card.
- **Consumes:** T4 view-models, B1 `digest_id` and `warnings`, B4, B6; spec digest reply rules.
- **Produces:** `Thread`, `DigestReply`, `EntryRow`, `HfTable`, `JuyaIssueCover`, `HoverPreview`, and a sanitized markdown renderer.
- **Acceptance:** Header shows `dN`, time, item count, and "X of Y sources returned results" from warnings. Warning alerts render per connector. Hover or focus preview appears after 400 ms, hides on scroll and Escape, and uses only `preview_image_url`. Markdown is sanitized and links use `rel="noopener"`. A reloaded digest looks identical to the live one (same `dN`, same warnings). Layout matches the prototype; motion is added in T9.
- **Blocked by:** T4, T2, B1
- **Plan mode:** medium (named unknown: markdown sanitizer choice)
- **TDD suitable:** partial
- **TDD suitable reason:** sanitizing and section rendering rules are testable; spacing and type are compared in the browser.
- **Verification:** `npm --prefix frontend run test -- digest`; browser comparison against the OpenDesign preview using fixtures, then against fake mode.

### T7 — Run progress, terminal states, and reconnect UI

- [x] **Do:** Port the run card, segmented bar, cancelled, failed, interrupted, and reconnecting banner, wired to the lifecycle.
- **Consumes:** T3 lifecycle, B3 structured progress, T6 thread.
- **Produces:** `RunCard`, `CancelledReply`, `FailedReply`, `InterruptedReply`, `ReconnectBanner`.
- **Acceptance:** Per-source steps and bar update from `source/status/count`; with those fields absent the card falls back to the `stage` line. Digest runs show "Writing digest" with shimmer and no delta text. Follow-up runs show cumulative markdown with the caret and sheen. Cancelled shows how many sources finished when known. Interrupted and failed show the safe message with Run again, which only refills the composer. `role="progressbar"` and live regions match the spec.
- **Blocked by:** T3, T6, B3
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** the step reducer and fallback are testable; visuals are compared in the browser.
- **Verification:** `npm --prefix frontend run test -- run`; manual run against `ai-news-agent service --fake` including cancel and a forced stream drop.

### T8 — Composer

- [x] **Do:** Port the composer: textarea, source checkboxes, per-source stepper, validation, busy and blocked notices, Cancel.
- **Consumes:** T3, T5, `PATCH /sessions/{id}`, `GET /sources`.
- **Produces:** `Composer` and `useComposer()`.
- **Acceptance:** Enter sends, Shift+Enter inserts a newline, IME composition does not send. Validation covers empty text, no source, and count outside 1-20, with the backend-aligned copy. Changing sources or count PATCHes the session preferences. Every send includes `juya_item_mode: "stories"` and a new `client_request_id`. During a request the inputs and Send are disabled and Cancel shows. A 409 shows the blocked notice. "Ask a follow-up" and suggestions prefill the composer.
- **Blocked by:** T3, T5
- **Plan mode:** skip
- **TDD suitable:** yes
- **Verification:** `npm --prefix frontend run test -- composer`

### T9 — History panel

- [x] **Do:** Port the history panel with filters, results, opened result, and empty states.
- **Consumes:** B5 `topics`, `GET /history/search`, `GET /history/{token}`, T4 mappers, T6 entry component.
- **Produces:** `HistoryPanel`.
- **Acceptance:** With no criteria the panel shows the idle prompt and makes no request. Filters map to `text`, `sources`, `topics`, `since`, `until`. Count line shows results and filters, plus `caveats` and truncation. Opening a result renders `entry` with the shared entry component, or `markdown` when `entry` is null, and never changes the conversation. 400 messages show inline. Overlay and scrim behavior matches the breakpoints.
- **Blocked by:** T6, B5
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** the no-criteria rule and filter mapping are testable; layout is compared in the browser.
- **Verification:** `npm --prefix frontend run test -- history`; browser check with fake-mode history.

### T10 — Motion and accessibility pass

- [x] **Do:** Port all keyframes literally and finish the accessibility and reduced-motion behavior.
- **Consumes:** prototype keyframes (`rise`, `fadeIn`, `collapse`, `sheen`, `segrun`/`segdone`, `stripes`, `shimmer`, `blink`, `spin`, `flash`); T5-T9 components.
- **Produces:** `styles/motion.css` and component hooks; cleanup on unmount.
- **Acceptance:** Durations, easing, delays, and stagger (capped at index 8) match the prototype. `prefers-reduced-motion` follows the prototype reduce block. Keyboard flow, focus ring, roles, `aria-live`, and `aria-current` match the spec. No timer or observer leaks after navigating between sessions.
- **Blocked by:** T5, T6, T7, T8, T9
- **Plan mode:** skip
- **TDD suitable:** no
- **TDD suitable reason:** motion and visual polish are verified by browser comparison, per the spec.
- **Verification:** Browser compare against the OpenDesign preview; keyboard-only walkthrough; reduced-motion emulation.

### T11 — End-to-end smoke and acceptance

- [x] **Do:** Run the whole UI against the fake backend and check each spec acceptance item.
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
| 2026-10-11 | T1 done: `frontend/` scaffold with npm, Tailwind v4, shadcn-vue init, Vitest; OpenAPI client via `@hey-api/openapi-ts` from committed `frontend/openapi.json` | — |
| 2026-10-11 | T3 done: `frontend/src/api/sse.ts` (frame parser, `postMessageStream`, `SseHttpError`) and `lifecycle.ts` (`createRequestLifecycle`, cancel 202/204, reconnect backoff, `resume`, 409 `blocked`, superseded-run guard, `defaultLifecycleDeps`); 15 vitest cases with injected deps, no network | — |
| 2026-10-12 | T4 done: `frontend/src/vm/` (`types`, `entries`, `digest`, `session`, `history` plus `fixtures/`) with pure `toVm`, section grouping, Juya issue grouping, digest and warning vms, message/session/history mappers, and a fixtures-import guard test; 30 new vitest cases | — |
| 2026-10-12 | T6 done: markdown-it + DOMPurify renderer (`lib/markdown.ts`), hover-preview composable (`lib/useHoverPreview.ts`), `components/thread/**` (Thread, EmptyConversation, DigestReply, DigestSection, EntryRow, JuyaIssueCover, HfTable, SourceTag, SourceLogo, AvatarTile, AppIcon, HoverPreview, MarkdownReply) and `styles/thread.css` ported from the prototype; source logos copied to `src/assets/sources/`; `dev/visual-compare.html` renders fixtures outside the bundle; 39 new vitest cases | — |
| 2026-10-12 | T6 drops prototype UI not in the spec: the hover card caption ("Preview card · github.com"), the Juya "Lead story" label, and the prototype review strip. User-message source chips stay for T8 (spec: current page session only), so T4's `MessageVm` is unchanged | equivalent |
| 2026-10-12 | Supersedes the drop row above for the caption and the label: the hover card captions itself `Preview card · {host of the previewed link}` (`hoverPreview.caption`, empty when the link is not a parseable http(s) URL) and the Juya cover shows "Lead story" above the lead title when `issue.lead_title` is present. Both needed no backend change. The review-only state strip returns in `dev/visual-compare.*` with Digest reply and Empty conversation active and the other seven disabled until T7-T9 | equivalent |
| 2026-10-12 | T5 done: `stores/sessions.ts` (cursor paging, reuse-empty with `flashId`, rename plus Escape, busy-safe delete, search, health) with `components/sidebar/**` (Sidebar, SessionRow, SessionSearchHit, DeleteConfirm, BackendStatus), `components/shell/ChatHead.vue`, and `styles/controls.css`; 12 vitest cases with injected deps. Search hits reuse T4's existing `toSessionHitVm` rather than adding a duplicate type. Also folds in three small host fixes: `AppIcon` moves to `components/ui/`, `.chat-body` stops nesting a second scroller, and selecting a conversation dismisses the sidebar overlay | — |
| 2026-10-12 | T5 page size is left at the API default through `limit=50`. The row shows "no messages" from `digest_count === 0`, because `GET /sessions` returns no message count and the prototype's `!msgs.length` test has no server equivalent | equivalent |
| 2026-10-13 | T7 done: `vm/run.ts` (`toRunVm`, `toCancelledVm`, `sourceKind`; steps from `source/status/count` with the `stage` fallback, writing phase, follow-up mode, reconnect banner, clock labels) with 14 vitest cases; `components/thread/{RunCard,ReconnectBanner,CancelledReply,FailedReply,InterruptedReply}.vue`, `styles/run.css`, the `alert-info/danger/ok` variants in `thread.css`, a `streaming` prop on `MarkdownReply`, and `stores/thread.ts` (transcript load, `resume` on `active_request_id`, live run clocks, reconnected dwell, `visibleMessages`, `runAgain`). Browser-compared against the prototype: `.run` 880x204 with the same grid rows, the 204px reconnecting card and 256px banner card, `.steps li` columns `20px 16px 110px 1fr auto` dropping to four columns with the mono hidden under 560px, `.writing` 847x48 with 779/660/542px lines, and identical dark-theme colours | — |
| 2026-10-13 | T7 keeps `FailedReply` and `InterruptedReply` as two components, as planned, though they differ only in the alert variant (`danger` vs `info`) and their copy; both render from T4's existing `toRequestStateVm`, so no second request-state type was added | equivalent |
| 2026-10-13 | T7 extends T3's `RequestSnapshot` with `terminalStatus` (5 new lifecycle cases) because the poll path collapses `failed` and `interrupted` into one `failed` state, and the Interrupted alert needs the difference | equivalent |
| 2026-10-13 | T7 fixes a wiring gap found against `service --fake`: the transcript never refreshed when a run reached an outcome, so a completed digest never appeared (the lifecycle's own `reloadMessages` dep discards its response). The store now reloads on the terminal transition and hides the transcript copy of an outcome the live reply is already showing | equivalent |
| 2026-10-13 | T8 done: `vm/composer.ts` (`parseSources`, `prefsFor`, `validateComposer`, `toComposerVm`) with 10 vitest cases, `stores/composer.ts` (`load`, `send`, `cancel`, `toggleSource`, `commitCount`, `stepCount`, `setText`, `prefill`, `prefillFollowUp`, `runAgain`, `focusToken`) with 20 injected-deps cases, `components/composer/Composer.vue` with 7 mount cases, and `styles/composer.css` ported from prototype lines 302-345; `AppShell` gains a `#composer` slot and `App.vue` fills it. Browser-compared against `/dev/prototype.html` at 1440/768/390: composer 749/733/355-370, `.c-bar` 748/733, chips `[81,134,97,89,91]`, the same two-line wrap (`sources` alone, then `per` + `c-actions`), `--dock-h` 217/181px feeding the thread's `calc(var(--dock-h) + 12px)` bottom padding, dock `right` = the thread's scrollbar width, `0 10px` dock padding and a hidden second hint span under 899px, and identical dark-theme notice, disabled-chip, Cancel and error colours | — |
| 2026-10-13 | T8 takes the spec's 1-20 stepper range and its copy over the prototype's `N_MAX = 10`; the prototype's per-message sources/count are session-sticky preferences through `PATCH /sessions/{id}` instead, and the prototype's demo `blocked` flag is replaced by the send attempt and the lifecycle's `blocked` snapshot | material (planned) |
| 2026-10-13 | T8 reads "while a request is active: inputs disabled" as the source checkboxes, the stepper and Send, and keeps the textarea editable, because both the spec's own notice copy ("You can draft your next message") and the prototype's busy state leave it enabled. That is also what makes "a send attempt shows the blocked notice" reachable: Enter during a run refuses the send, keeps the draft, and swaps the info notice for the warn one | equivalent |
| 2026-10-13 | T8 never PATCHes an empty `connector_names` (the backend answers 400), so unchecking the last source leaves the send blocked by the client-side validation instead; a refused PATCH keeps the UI state and shows inline copy. A send call that throws is caught and reported inline rather than as an unhandled rejection | equivalent |
| 2026-10-13 | T8 adds an optimistic user bubble to `stores/thread.ts` (`markUserSent` + `pendingUser`, 2 new cases): without it a sent message is invisible until the terminal reload, which does not match the prototype. The bubble clears on the terminal transition and on opening another conversation | material (unplanned) |
| 2026-10-13 | Open after T8: when the `POST /messages` call itself throws (backend down, or a stream that rejects mid-flight instead of ending cleanly) the lifecycle keeps its `streaming` snapshot, so the composer stays busy with a Cancel that cannot cancel. The T3/T7 state machine has this hole; the composer only avoids the unhandled rejection. Worth a follow-up that emits a failed state or reconnects on a rejected stream | open |
| 2026-10-14 | T9 done: `vm/history.ts` gains `HistoryFilters`/`EMPTY_HISTORY_FILTERS`, `historySourceOptions`, `toHistoryQuery` (no criterion gives `null`, so the API is never called empty; `sources`/`topics` as csv, `since`/`until` from From/To, `limit` 10), `filterCount`, `toHistoryResultVm` ("N result(s) · M filter(s)", caveats plus a truncation note, and it drops the backend's own no-match caveat while the list is empty), `noMatchBody`, `toOpenedVm` and `toHistoryPanelVm` (18 new vitest cases on top of T4's 6); new `stores/history.ts` (`createHistoryController` with 250ms debounce, a request sequence that drops stale answers, `setFilters`, `clearFilters`, `retry`, `open`, `closeResult`, `askInChat`, plus `defaultHistoryDeps` and `useHistoryStore`) with 17 injected-deps cases; new `components/history/HistoryPanel.vue` and `styles/history.css`; `App.vue` fills the `#history` slot and `AppShell` gains `closeHistoryIfOverlay`. Browser-compared against `/dev/prototype.html` at 1920 with identical boxes: panel 372x1040, `.hist-head` 371x52 with `0 10px 0 16px` and `gap: 8px`, `.hist-filters` 371x177 (`padding: 12px 16px`, `gap: 8px`), `.hist-row` 339 with two 165.667px columns, `.hist-bar` 371x45, `.hit` 371x85 (grid, `gap: 4px`, `padding: 10px 16px`), `.hit-title` 13px/500, `.hit-meta` 11.5px, `.hits .ext` 12px, the `.ref` chip (12px mono, `3px 6px`, `--surface` fill) and the 32px/13px filter inputs. Live against `service --fake`: `?limit=10&text=qwen` returned 10 rows that render with the real `dNNN:rN` tokens, and opening `d118:r1` rendered its Hugging Face entry without touching the thread | — |
| 2026-10-14 | T9 takes the spec's free-text Topic input over the prototype's fixed topic `<select>`, and the prototype's `hf` source value is normalized to the API's `huggingface` in `toHistoryQuery` (the select itself already offers API names). With every filter empty the panel makes no request and shows "Search past digests / Enter text, a source, a topic or a date range." — the spec states the rule but not the copy, so it is new text in the prototype's `.hist-empty` shape | equivalent |
| 2026-10-14 | T9 renders the opened result with T6's `EntryRow` rather than the prototype's `h3` + summary + "Open source page"/"Ask in chat" pair, as the approved type-2 plan decided: the shared entry component already carries the title link, the `.ext` host link and its own follow-up button, so there is no second button. Keeping the two-column `.entry-body` inside a 372px column wrapped every line, so `history.css` narrows it to one column there. Two rows the prototype had no UI for: the spec's excerpt line on each result, and a `.hist-notes` block under the count for `caveats`/`archive_truncated`. The planned static note "Opened from history. The current conversation is unchanged." replaces the prototype's live-digest variant, which needed the thread | equivalent |
| 2026-10-14 | T9 fixes a wiring bug found in the browser: "Ask in chat" closed the panel at desktop width, collapsing the 372px column instead of leaving it. `AppShell` now exposes `closeHistoryIfOverlay`, which dismisses only under 1280px where the panel is an overlay | equivalent |
| 2026-10-14 | T9 dark theme and breakpoints checked against the real app: 1100px and 390px both give the fixed overlay (`width: min(392px, 92vw)` = 392/359px, `top: 0`, frost plus blur, scrim shown), 820px matches with the sidebar also overlaying, and Escape and the scrim both dismiss it. `dev/visual-compare` now covers six history states (results, opened entry, markdown fallback, opened loading, no matches, failed search) beside the thread | — |
| 2026-10-14 | T9 shows the backend's 400 `detail` inline as-is. A rejected source list arrives as a multi-line pydantic dump; the UI's source `<select>` cannot produce one, and the reachable client-side 400 ("since must not be after until", from From > To) is a single clean line | equivalent |
| 2026-10-14 | Open after T9: `HistoryMatchVm.topics` is mapped and tested but no longer rendered — the spec's result-row list has no topics field, and the API's digest-level topic set does not generalize the prototype's one-topic chip, so the opened result shows the token, date and source tag only. If a topic list is wanted there, it needs its own row rather than a chip per topic | open |
| 2026-10-14 | T10 done, layout free: new `styles/motion.css` holds every keyframe and animation rule (`rise`, `fadeIn`, `flash`, `spin`, `sheen`, `segrun`, `segdone`, `stripes`, `shimmer`, `blink`), the `.rise`/`.fade-in` classes, the `.collapse` and `.sess-li` shells, the hover-card fade, and the prototype's `prefers-reduced-motion` block verbatim; `.spin`/`@keyframes spin` moved out of `controls.css` and `.collapse` out of `run.css`, which keeps the gradients, state colors and layout. `lib/motion.ts` adds `MAX_STAGGER_INDEX` 8, `riseStyle` and the shared `prefersReducedMotion` (now also used by `stores/theme.ts`). Browser-compared against `/.tmp-prototype.html` at 1440 (byte-identical motion CSS): `.run` and `.md.streaming` sheen 2.6s linear infinite, `.segbar .s-run i` segrun 1.4s `cubic-bezier(0.2,0,0,1)` 1 iteration, `.segbar .enter i` segdone 0.2s, `.segbar.paused .s-run i` stripes 1s linear, `.writing .line` shimmer 1.4s linear, `.caret` blink 1s `steps(1)`, `.run-head .ic` spin 1s linear, `.sess.flash` flash 1.2s, `.hovercard` fadeIn 0.2s, `.sess-li` `grid-template-rows 0.32s, opacity 0.2s`, `.rc-wrap`/`.collapse` the same pair, and the staggered entries' `--i` 1/2 giving 40/80ms delays — value for value | — |
| 2026-10-14 | T10 keeps the reveal to live arrivals only, as the prototype does, which needed a freshness rule the host did not have: `stores/thread.ts` tracks `freshIds` (plus `PENDING_MESSAGE_ID`) and the reload that follows a terminal state passes `markFresh: true`, so the first run in an *empty* conversation animates too (a `messages.length > 0` test did not) while a plain open and an already-shown row stay still. `Thread` takes `freshIds` and passes `animate`/`startIndex` down; the stagger counts across the whole digest (head 0, then warnings, then entries and HF rows in section order, capped at 8) instead of restarting per component | equivalent |
| 2026-10-14 | T10's row motion needed one departure from the prototype's mechanism: mounting the row `shut` and dropping that class on the second animation frame leaves it stuck collapsed whenever frames are throttled (observed live), so the arriving row carries `.sess-li.enter` and animates `sessEnter` from `0fr`/opacity 0 over the same `--d3`/`--ease`, with the class dropped after 360ms. The delete path keeps the prototype's transition verbatim (measured 49.79px → 11.46 → 1.66 → 1px, opacity 1 → 0.27 → 0.05 → 0, row removed at 330ms) and both paths are skipped outright under reduced motion | equivalent |
| 2026-10-14 | T10 puts the reconnect banner's dismissal collapse in the store, not the banner: `RunVmInput`/`RunVm` gain `reconnectLeaving`, which the store sets one collapse (`--d3` + 20ms) before the dwell ends, so the banner's `.rc-wrap.collapse` can shut before the reconnect clears, as the prototype's shut-then-clear step does. Under reduced motion the flag lands with the dwell, so the banner vanishes whole. Verified through the harness: the shell is `.collapse` with `grid-template-rows`/`opacity` 0.32s/0.2s and reaches 0px/opacity 0 when shut | equivalent |
| 2026-10-14 | T10 ports the cancel height tween (measure, freeze the old height, reflow, `transition: height var(--d3) var(--ease)`, set the new height, clear on `transitionend` with a 400ms settle guard, skipped when reduced). Fake mode finishes a run in under a second, so the Cancel button never coexisted with a run card; the wiring was exercised by driving the thread store's snapshot from `streaming` to `cancelled`, which measured the run slot at 262px, applied `height: 79px; overflow: hidden; transition: height var(--d3) var(--ease)` and then cleared the inline styles, leaving the 79px cancelled alert | equivalent |
| 2026-10-14 | T10 closes the a11y gaps the walkthrough found: the composer's error paragraphs now carry `err-text`/`err-sources`/`err-n`/`err-send`/`err-prefs` and the fieldset wires `aria-describedby="err-sources"` (as the prototype does) while the count input wires `err-n` (an addition — the prototype sets only `aria-invalid` there). Everything else already matched: `role="switch"`+`aria-checked`, `role="alertdialog"`, `role="progressbar"` with `aria-valuenow/min/max` and "Sources finished", `aria-live="polite"` on the run card and history count, `role="alert"` on warnings and validation, `aria-current` on the active row, `aria-pressed`/`aria-controls="history"`, labelled inputs, the `--ring` focus ring. Escape order was re-checked live: at 1440 it leaves the history column (`app hist-open`) and at 1100 it dismisses the overlay (`app`, panel off-screen, scrim hidden) | equivalent |
| 2026-10-14 | T10 leak pass: the reconnect dwell timers are now guarded by the session id, and `loadMessages` drops a reload whose conversation is no longer open — without that guard a terminal event for the old conversation could write its rows into the new one, which `freshIds` would then animate. Verified live: three session switches with a search debounce pending left the header, transcript and 14 messages on the last-clicked conversation, with no errors. Sidebar search, delete-collapse, `ReconnectBanner`, spinner and the hover cards clear their timers/listeners on unmount | equivalent |
| 2026-10-14 | Open after T10: focus follows the prototype, so dismissing the delete confirm leaves focus on the body (the focused button unmounts). Worth a follow-up that returns focus to the sidebar (the row's neighbour or New conversation). Also worth noting: the reveal animations depend on the page producing frames, so in a throttled tab an animation can land in its end state instead of playing — the end state is always the correct one | open |
| 2026-10-15 | T11 done (acceptance note, no code change). Suites on the assembled branch: `uv run pytest -q` 1006 passed and 2 skipped; `npm --prefix frontend run test` 254 passed in 22 files; `npm --prefix frontend run build` clean (`vue-tsc -b` typecheck plus Vite, 290.08 kB js / 45.59 kB css). T1 added no browser-test runner, so T11 adds no Playwright spec. Live walkthrough against `ai-news-agent service --fake` on `:8765` with `npm run dev` on `:5173`: sidebar grouped under the real month with per-session digest counts, session search (`GET /sessions/search?q=tooling` → two `title` hits), chat head with the real title, "6 digests", the FAKE MODE badge and "Backend running in fake mode", dark theme restored from `anra-theme` before paint, a digest carrying Juya, Hugging Face, GitHub and Zhihu sections (the GitHub meta line with `+42 today` on one repo and without it on two), the composer showing the session's stored preferences (five sources, count 5) after a reload, history search (`GET /history/search?limit=10&text=qwen` → "10 results · 1 filter", ten `dNNN:rN` rows), an opened result rendering the shared entry row with its caveat note, and composer validation (a whitespace-only draft on Enter gives `.err-msg#err-text` "Type a question or topic first.", `aria-invalid` and `aria-describedby="err-text"` on the textarea, no run started, the draft kept) | — |
| 2026-10-15 | T11 acceptance 2 verified live: a run started from the composer was reloaded mid-stream, with the page recording `snapshot.state` as `streaming` immediately before the unload. The reloaded page re-opened the conversation, polled `GET /sessions/{id}/requests/40f628a8-84c0-485b-a860-00ca5e874630`, then reloaded the transcript (`GET .../messages`); the service log shows no second POST for that request, so the byte stream was never reopened. The run finished server-side during the page load, and the digest row it persisted (`digest_id` 135) is in the reloaded transcript with `digest_count` matching | — |
| 2026-10-15 | T11 acceptance 3 and 4 verified against the prototype on the same dev server (`/.tmp-prototype.html`) with matched `Emulation.setDeviceMetricsOverride` viewports. Tokens: `--bg`, `--surface`, `--muted`, `--border`, `--accent`, `--ring`, `--d1`/`--d2`/`--d3`, `--stagger` and `--ease` are identical in both themes (the prototype's `cubic-bezier(.2,0,0,1)` and the app's `cubic-bezier(0.2, 0, 0, 1)` are the same curve). Layout, app against prototype: 1280 gives sidebar 264 with the history column at 372 (`264px minmax(0,1fr) 372px`, measured 264/1284/372 at 1920 on load); 1024 gives sidebar 264, chat 760, thread 705 at x=284, dock 745, `.c-bar` 704×90, history 392 wide and `position: fixed`; 800 makes the sidebar a 300px overlay at x=-315 with the menu button shown, chat 800, thread 761, dock 785, `.c-bar` 764×90, `.per` 148×28; 400 gives thread 361, dock 385×215, `.c-bar` 364×124, history 368 (= 92vw) fixed, and `.c-actions` 77×34 at the same coordinates with 13px labels. Every compared box matches; the only offsets are the prototype's 40px review strip and the history column, which the prototype had open where the app's had been dismissed | — |
| 2026-10-15 | T11 acceptance 3, reveal: the store's reveal path runs — a call to the same `setTheme` the theme control uses reported `document.startViewTransition` entered once, with `vt-theme`/`vt-shrink`/`theme-snap` applied and then cleared — but the clip-path animation cannot play in this pass because the automation tab is hidden (`document.hidden` true) and Chrome skips view transitions for hidden documents, so `vt.ready` rejects, the store's `.catch(() => {})` swallows it and `vt.finished` resolves at once. The animation itself keeps its T2 unit tests and browser comparison. Under `prefers-reduced-motion: reduce` the store takes the instant path (no second `startViewTransition`) and still flips and persists the theme | — |
| 2026-10-15 | T11 harness note, for the record: mouse-activated controls could not be driven in this pass. The browser tool's ref clicks and raw coordinate clicks reached the page but never ran Vue's `@click` handlers (on Send the button took focus without submitting; on the theme toggle, focus without a flip), and a `MouseEvent`/`.click()` dispatch from the page behaved the same, while keyboard events did reach the app (Enter in the composer sent a run). Checks that need a click were therefore driven through the same store actions the components call (`theme.setTheme`/`toggleTheme`, `history.open`), and these keep their subtask verification: new conversation, rename, delete confirm, Cancel, the hover card, and the cancelled/failed/interrupted replies (T7). The connector-warning alert also stays with T6's fixtures, because fake mode produces no failing connector | open |
