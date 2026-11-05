# Implementation plan: Follow-ups and settings, backend

**Piece:** 1 of 2. Frontend: `docs/superpowers/plans/2026-10-20-followups-settings-frontend-plan.md`
**Specs:** `docs/superpowers/specs/2026-10-20-targeted-followups-design.md`, `docs/superpowers/specs/2026-10-20-settings-and-credentials-design.md`
**ADRs:** `docs/adr/0015-targeted-followups-and-request-identity.md`, `docs/adr/0006-huggingface-live-model-card-on-rank-followup.md`, `docs/adr/0013-global-source-profiles.md`, `docs/adr/0014-owner-access-and-credential-boundary.md`
**Created:** 2026-10-30
**Goal scope:** One backend piece: targeted follow-ups, collection outcomes, global source profiles, output language, credential storage, and owner-access protection. The Vue work is the other piece. OpenRouter as a digest source is a separate spec. Research records are a separate plan and use schema 5 after this piece's schema 4.

## Summary

Follow-ups gain `{digest_id, display_rank}` and `followup_action: "deep_dive" | "ask"`. A request id replays only the same submission. Deep dive and Ask about this stay on that entry. Finished collects distinguish no eligible results, source failure, and partial results.

Settings then replace the session item-count. Profiles and output language ship first. Credential editing and the owner access token ship together after that, as the settings spec requires. Schema moves from 3 to 4. The Keys API is not usable from a non-loopback client until the access token is in place.

## Discovery notes

- Reuse: `PostMessageBody`, `MessageOut`, `ResolvedRequestOut`, and `interpretation_json` projected by `request_interpretations`. Follow-up target and action use that projection. No new `session_messages` column.
- Reuse: `get_followup_context_for_digest` and `get_followup_context_for_session`. `enrich_huggingface_for_rank` currently reloads `get_latest_followup_context()` after a README fetch. B2 reloads the targeted digest.
- Reuse: `interpret_message`. Intents stay `"digest" | "followup" | "general" | "clarify"`.
- Reuse: `begin_request` replays a terminal row with the same `client_request_id` and does not compare the body. B1 adds that comparison.
- Reuse: `SCHEMA_VERSION = "3"` and the backup-then-transactional migration in `repositories/digest_store.py`. B5 is v3 to v4. Research records are not part of v4.
- Reuse: `build_chat_model` and `build_tool_chat_model` read `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` from the environment when no argument is passed. Connectors read `GITHUB_TOKEN`, `HUGGINGFACE_TOKEN`, and the Zhihu and Bilibili secrets the same way. B9 introduces `CredentialsProvider` and stops those call sites from reading `os.environ` themselves.
- Reuse: `digest_request_builder.py` and `_apply_session_defaults` in `services/chat.py`. New requests stop copying `sessions.items_per_source`. The column stays for old rows and Run again.
- Reuse: `create_app` mounts routers and loopback CORS. Methods today are GET, POST, PATCH, DELETE, OPTIONS. Headers today are Accept and Content-Type. B11 adds PUT and Authorization. There is no auth dependency yet.
- Constraint: digest-entry `follow_up_action` (`read | watch | try | build`) is not `followup_action`.
- Constraint: `cryptography` is not a project dependency. Fernet comes in with B9.
- Constraint: OpenRouter's connector, ranking, and digest section are out of this piece. B6 still stores the OpenRouter profile the settings spec defines (`item_count`, `free_only`).
- Anti-goals: no research runner, no research record, no OpenRouter collect path, no multi-user accounts, no Remember-me token, no drive-by edits to `tools/agent.py`.

## File map

### Goal: Follow-ups

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|---|---|---|---|---|
| `src/ai_news_agent/api/schemas/sessions.py` | modify | Targeted follow-up and repeat fields | `FollowupTarget`, `FollowupAction`, `PostMessageBody.followup_target`, `followup_action`, `repeat_of_user_message_id`, `replace_source`, `MessageOut.followup_target`, `followup_action`, `collection_outcome` | verified path |
| `src/ai_news_agent/api/routers/sessions.py` | modify | 400/409 and message projection | existing message routes | verified |
| `src/ai_news_agent/services/session_service.py` | modify | Submission comparison before replay | `begin_request` | verified |
| `src/ai_news_agent/services/chat.py` | modify | Targeted follow-up and repeat dispatch | `ChatService.stream_events` | verified |
| `src/ai_news_agent/services/conversation.py` | modify | Untargeted routing | `interpret_message` | verified |
| `src/ai_news_agent/collection_outcomes.py` | create | Classify a digest run from entries and warnings | `SOURCE_FAILURE_CODES`, `collection_outcome` | provisional |
| `src/ai_news_agent/followup_structured.py` | modify | Card for the targeted entry | existing formatters | verified |
| `src/ai_news_agent/followup_enrich.py` | modify | README reload uses the targeted digest | `enrich_huggingface_for_rank` | verified |
| `src/ai_news_agent/huggingface_followup.py` | modify | `Not saved` and snippet labels | `format_huggingface_family_card` | verified |
| `src/ai_news_agent/services/digest_views.py` | modify | Related ranks | `related_display_ranks: list[int]` | verified path; grouping rule provisional |
| `src/ai_news_agent/api/schemas/digests.py` | modify | Related ranks on HF entry DTO | `HuggingFaceDigestEntryView.related_display_ranks` | verified |
| `src/ai_news_agent/llm.py` | modify | Entry-only Ask follow-up | `OpenAIChatModel.generate_followup_reply` | verified |
| `src/ai_news_agent/services/composition.py` | modify | HF connector factory for targeted fetch | `ChatService` wiring in `build_application` | verified |
| `tests/test_api_sessions.py`, `tests/test_chat.py`, `tests/test_conversation.py`, `tests/test_huggingface_followup.py`, `tests/test_digest_views.py`, `tests/test_followup_context.py`, `tests/test_llm.py`, `tests/test_session_service.py` | modify | Follow-up acceptance | pytest | verified |
| `tests/test_collection_outcomes.py` | create | Outcome classification and repeat acceptance | pytest | provisional |

### Goal: Settings, keys, and sign-in

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|---|---|---|---|---|
| `src/ai_news_agent/repositories/digest_store.py` | modify | v3 to v4 tables; persist `digest_entries.language` | `source_settings`, `secrets`, language preference, credential-health rows; entry language write/read | verified path; DDL provisional |
| `src/ai_news_agent/source_settings.py` | create | Per-source profile models and global output language | `SourceSettingsService`, `get_language`, `save_language` | provisional |
| `src/ai_news_agent/models.py` | modify | Per-entry generated language on `DigestEntry` | `DigestEntry.language` | verified |
| `src/ai_news_agent/summarizer.py` | modify | Resolve and attach entry language at summarize time | `summarize_ranked_items` | verified |
| `src/ai_news_agent/services/digest_views.py` | modify | Expose stored entry language on view payload | `_entry_common_fields` | verified |
| `src/ai_news_agent/api/schemas/digests.py` | modify | Entry DTO carries generated language | `DigestEntryView.output_language` | verified |
| `src/ai_news_agent/api/routers/settings.py` | create | Profiles, language, credentials | `/api/v1/settings/sources`, `/settings/language`, `/settings/credentials` | provisional |
| `src/ai_news_agent/api/schemas/settings.py` | create | Profile, language, and credential DTOs | Pydantic models | provisional |
| `src/ai_news_agent/credentials.py` | create | Encrypt, resolve, and version credentials | `CredentialsProvider` | provisional |
| `src/ai_news_agent/credential_health.py` | create | Versioned health observations in `credential_health` | `CredentialHealthStore` | provisional |
| `src/ai_news_agent/credential_tests.py` | create | Bounded provider probes and outcome classification | `classify_probe_outcome`, probe runners | provisional |
| `src/ai_news_agent/api/routers/meta.py` | modify | Composer catalog includes credential health summary | `GET /api/v1/sources` health field | provisional |
| `src/ai_news_agent/sources.py` | modify | Pass provider-resolved tokens into `build_connectors` / `build_connector_factory` | `build_connectors(..., credentials=None)` | provisional |
| `src/ai_news_agent/api/deps.py` | modify | FastAPI dependency for credentials | `get_credentials_provider` | provisional |
| `pyproject.toml` | modify | Fernet dependency | `cryptography>=42` | provisional |
| `src/ai_news_agent/llm.py` | modify | Callers pass provider values; env fallback retained for direct use (signatures unchanged) | `build_chat_model`, `build_tool_chat_model` | verified |
| `src/ai_news_agent/connectors/github.py`, `huggingface.py`, `zhihu.py`, `bilibili.py` | modify | Take tokens from the caller, not `os.environ` | constructors | verified |
| `src/ai_news_agent/digest_request_builder.py` | modify | Profile, then explicit message option | `build` path already used by chat | verified |
| `src/ai_news_agent/request.py` | modify | Per-source caps and GitHub profile fields | `source_item_counts`, profile overrides | verified path |
| `src/ai_news_agent/services/conversation.py` | modify | Count phrase parsing | `_digest_decision` | verified |
| `src/ai_news_agent/services/chat.py` | modify | Apply profiles; drop session count default | `_apply_session_defaults`, `apply` | verified |
| `src/ai_news_agent/services/session_service.py` | modify | Apply profiles in `build_request` | stop copying `items_per_source` | verified |
| `src/ai_news_agent/ranking.py`, `graph/nodes/rank.py` | modify | Per-source display caps; Juya all selects every story row | `rank_items`, `juya_item_count_all` | verified |
| `src/ai_news_agent/graph/nodes/parse.py`, `connectors/base.py`, `connectors/github.py` | modify | Profile fields on connector request | `ConnectorRequest`, GitHub query | verified |
| `src/ai_news_agent/connectors/juya.py` | modify | Unbounded story collect when `juya_collect_all_stories` | `fetch_juya_daily_items`, `enrich_juya_items_with_markdown` | verified |
| `src/ai_news_agent/graph/workflow.py` | modify | Gate summarize when Juya all unconfirmed | digest graph edge | verified path |
| `src/ai_news_agent/services/chat.py` | modify | Juya all confirmation gate and continue | `continue_juya_all`, `_stream_session_digest_events` | verified |
| `src/ai_news_agent/services/session_service.py` | modify | Pending Juya confirmation vs session busy | `begin_request`, `is_pending_juya_confirmation` | verified |
| `src/ai_news_agent/api/routers/sessions.py`, `api/schemas/sessions.py` | modify | Continue/cancel route and `MessageOut.juya_confirmation` | `POST .../juya-confirmation` | verified |
| `src/ai_news_agent/request.py` | modify | Confirm flag for second digest pass | `juya_all_confirmed`, `juya_item_count_all` | verified |
| `src/ai_news_agent/source_settings.py` | modify | Juya all apply and confirmation payload helper | `juya_all_confirmation`, `apply` | verified |
| `src/ai_news_agent/api/schemas/sessions.py` | modify | Resolved counts on public request | `ResolvedRequestOut.counts` | verified path |
| `src/ai_news_agent/cli.py` | modify | Same profiles; explicit CLI flags win | digest command | verified |
| `src/ai_news_agent/services/composition.py` | modify | Inject settings and credentials | `build_application` | verified |
| `src/ai_news_agent/api/app.py` | modify | Mount settings router; later bearer auth and CORS | `create_app` | verified |
| `tests/test_source_settings.py`, `tests/test_credentials.py`, `tests/test_api_settings.py`, `tests/test_access_token.py` | create | Settings acceptance | pytest | provisional |

### Blast radius

| Path | Why sensitive | Behavior that must stay intact | Plan mode |
|---|---|---|---|
| `services/session_service.py` `begin_request` | Every session send | Busy and in-progress 409; identical replay | high |
| `services/chat.py` `stream_events` | Digest and follow-up dispatch | Untargeted branches until B3; history show stays persist-only | high |
| `followup_enrich.py` | ADR-0006 | One README fetch, latest successful digest only | high |
| `repositories/digest_store.py` | Schema 3 databases | Existing digest, session, and message rows; backup failure aborts | high |
| `llm.py` and connector constructors | Every live collect | A missing provider still fails that source only; fake mode stays explicit | high |
| `api/app.py` | Every `/api/v1` route | `/health` stays open; local mode without a token still serves loopback | high |
| `tools/agent.py` | Listing short-circuit | No edit | skip |

## Workflow (for implementers)

1. **writing-plans** produced this file (type-1 decomposition only).
2. **B1**, **B3**, and **B5** may start together. **B6** and **B7** follow **B5**. **B8** follows **B6**. **B9** follows **B5**. **B10** and **B11** follow **B9**. Do not treat **B9** as shippable without **B11**: the frontend Keys tab waits for both.
3. Per subtask: **Plan mode** + **planning-subtasks** when **Plan mode** is `high` or `medium` with a named unknown.
4. **Agent mode** uses **test-driven-development** when `TDD suitable: yes`.
5. The frontend piece consumes this piece's HTTP contracts. The research plan's **R1** consumes **B1**, and its **R6** consumes schema 4 from **B5**.

## Subtasks

### B1 — Entry target and submission identity

- [x] **Do:** Bind a follow-up to one session entry and replay a request id only when the submission is the same.

- **Consumes:** `get_followup_context_for_digest`; `get_followup_context_for_session`; `begin_request`; `interpretation_json`.
- **Produces:** `FollowupTarget { digest_id: int, display_rank: int }`. `FollowupAction = "deep_dive" | "ask"`. Both body fields absent, or both present. `MessageOut.followup_target` and `followup_action` on the user message and the assistant message of that request, stored under interpretation `followup`. Submission match compares content, target, action, and `juya_item_mode`.
- **Acceptance:** The target's digest is used even when a newer digest exists, and the latest successful digest is unchanged. Another session's digest or an unknown rank returns 400. A target without an action, or an action without a target, returns 400. `interpret_message` is not called. Untargeted messages still use the latest digest. Reload returns the same target and action. An identical `client_request_id` replays. The same id with a different message, target, action, or `juya_item_mode` returns 409 `request_conflict` and runs nothing. A targeted action replaces a pending clarification, and reload does not restore it. A change to global settings alone does not invalidate an identical retry. Session-busy and in-progress 409s stay.
- **Compatibility:** History commands and untargeted follow-ups keep their current results. `follow_up_action` on digest entries is unchanged.
- **Blocked by:** —
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_api_sessions.py tests/test_chat.py tests/test_session_service.py -q`

### B2 — Deep dive and Ask about this

- [x] **Do:** Answer the targeted entry from its saved card, with the existing latest-digest Hugging Face README exception.

- **Consumes:** B1's resolved context. `followup_structured`, `enrich_huggingface_for_rank`, `format_huggingface_family_card`, `build_digest_view_payload`.
- **Produces:** Deep-dive text is the deterministic card. Ask-about-this text uses that entry only and says when evidence is insufficient, without fetching and without a research offer. `related_display_ranks: list[int]` for other entries in the same digest that share the saved model identity.
- **Acceptance:** Deep dive returns the Juya, Hugging Face, Zhihu, or generic card, including a comparison-table row. Ask about this does not search other sources. With no model, Deep dive is the card only, and Ask about this adds that question-specific answering is unavailable. A Hugging Face target in the session's latest successful digest may fetch the representative README once, reloading that digest rather than `get_latest_followup_context()`. Older targets and history show do not fetch. A missing stat is `Not saved`. A fetched-after snippet and a saved-with-digest snippet are labelled differently. An entry with no news item still returns the generic card.
- **Compatibility:** ADR-0006 stays latest-digest-only. Ranking and untargeted cards stay.
- **Blocked by:** B1
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_huggingface_followup.py tests/test_chat.py tests/test_digest_views.py tests/test_followup_context.py -q`

### B3 — Untargeted routing

- [x] **Do:** Make the same untargeted sentence take the same branch with or without a digest, a model, or a session source list.

- **Consumes:** `interpret_message`. B1 already replaces a pending clarification when the body is targeted.
- **Produces:** No new intent.
- **Acceptance:** "Tell me about Qwen" is `general` with and without a digest, and the reply is labelled general knowledge. An explicit entry reference is `followup`. "Recent Qwen updates" is `digest`. No model does not turn a general explanation into a digest or a clarification. A short reply completes a pending clarification and keeps its topic. A self-contained new request replaces it, and reload shows the replacement. The branch is logged.
- **Compatibility:** Targeted bodies never reach `interpret_message`.
- **Blocked by:** —
- **Plan mode:** medium (named unknown: which current `interpret_message` branches already accept these sentences)
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_conversation.py tests/test_chat.py -q`

### B4 — Collection outcomes and repeat

- [x] **Do:** Distinguish a finished empty collect, a source failure, and a partial digest, and start a new digest from the stored resolution.

- **Consumes:** B1's submission comparison. `MessageOut.request`. Stored connector warnings and entry counts.
- **Produces:** `MessageOut.collection_outcome: "results" | "no_eligible" | "failed" | "partial" | None`. `PostMessageBody.repeat_of_user_message_id: int | None` and `replace_source: str | None`. A repeat loads the stored resolution, skips the interpreter, and starts a new request. `replace_source` is valid only with the repeat id and replaces the source list with that one catalog source. Both fields join the submission comparison.
- **Acceptance:** A completed no-match is `no_eligible`. A source that did not complete, with no entries, is `failed`. Entries plus a failed source is `partial`. A suggestion keeps topic, timeframe, language, and audience, and changes only the source. Run again keeps the stored resolution, collects fresh data, and uses the credentials current at the new run. Neither is a replay. A repeat id with no stored resolution returns 400. Suggested sources are the composer catalog, excluding a source marked hidden. The interpreter does not rebuild the options from the old text.
- **Compatibility:** Existing warning text still ships on the digest. Identical replay from B1 still returns the stored request.
- **Blocked by:** B1
- **Plan mode:** medium (named unknown: which existing `ConnectorWarning` codes already separate a finished empty collect from a source that did not complete)
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_api_sessions.py tests/test_chat.py tests/test_digest_views.py tests/test_collection_outcomes.py -q`

### B5 — Settings schema

- [x] **Do:** Migrate schema 3 to schema 4 with the settings tables, and leave existing rows in place.

- **Consumes:** `DigestStore.init_schema`, `SCHEMA_VERSION = "3"`, the v1 backup path.
- **Produces:** `SCHEMA_VERSION = "4"`. Tables for `source_settings`, `secrets` (name, ciphertext, updated_at), the global language preference (`app_settings`), and credential-health observations. Nullable `digest_entries.language` column (NULL on pre-v4 entries). A failed backup aborts the migration and leaves the v3 file usable.
- **Acceptance:** A v3 database gains the new tables and keeps digests, sessions, messages, and requests. A fresh database is created at version 4. A backup failure does not write version 4. Version 1 and 2 still migrate forward through the existing steps. Research-record tables are not created here.
- **Compatibility:** Current session and digest reads keep working.
- **Blocked by:** —
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_digest_bundle.py tests/test_source_settings.py -q -k schema`

### B6 — Source profiles

- [x] **Do:** Store one global profile per source and use it for new web and command-line digests.

- **Consumes:** B5 tables. `digest_request_builder.py`. `_apply_session_defaults`.
- **Produces:** `GET /api/v1/settings/sources` and `PUT /api/v1/settings/sources/{name}`. Profiles: Juya `item_count` 1–50 or `all`; GitHub `item_count`, `keywords` (max 10), `min_stars >= 0`, `language`; Hugging Face `item_count`, `pipeline_tag`; OpenRouter `item_count`, `free_only`; Zhihu `item_count`; Bilibili no fields and `hidden: true`. Defaults are count 5, no keywords, `free_only` false. Unknown source is 404. Invalid values are 400. `SourceSettingsService` is what the request builder and the CLI call. Connectors receive resolved values on the request, not the service.
- **Acceptance:** GET returns every profile, including hidden Bilibili, with defaults filled. PUT round-trips. An unqualified count applies per selected source. A count named for one source overrides only that source. "Each" overrides every selected source. The count is a cap on eligible display entries. A shortfall is reported as returned of requested and does not widen timeframe, relax filters, or split packaging variants. GitHub keywords apply only when the message names no topic and do not turn `topics_are_filters` on. Web and CLI against the same database resolve the same profile. An explicit message or CLI option wins over the profile, which wins over the default. New requests ignore `sessions.items_per_source`. That column remains for old rows and for Run again. OpenRouter's profile can be saved; this task does not collect from OpenRouter.
- **Compatibility:** Fake mode stays offline. Existing explicit message counts still win.
- **Blocked by:** B5
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_source_settings.py tests/test_api_settings.py tests/test_chat.py -q`

### B7 — Output language

- [x] **Do:** Save a global output language and record the language each digest entry was generated in.

- **Consumes:** B5 tables and `digest_entries.language`. B6's precedence rule (explicit message or CLI wins).
- **Produces:** `GET /api/v1/settings/language` and `PUT /api/v1/settings/language`. Values `source_default`, `en`, and `zh-CN`. Initial value `source_default`. Each digest entry stores the language it was generated in.
- **Acceptance:** `source_default` keeps each source's current presentation language. `en` or `zh-CN` applies to generated text and entry labels. Original titles, quotations, model names, and identifiers stay as collected. A language named in the message or on the CLI overrides the saved preference for that run. Reopening an entry shows the labels from the language stored on it.
- **Compatibility:** Existing digests without a stored language still render.
- **Blocked by:** B5
- **Plan mode:** medium (named unknown: which current render path owns entry labels, so the stored language is read there and not in a second formatter)
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_api_settings.py tests/test_digest_views.py -q`

### B8 — Juya all confirmation

- [x] **Do:** When a request would summarize more than 20 Juya stories, wait for confirmation before writing the digest.

- **Consumes:** B6 Juya `item_count: "all"`. The selected issues after topic and timeframe filtering.
- **Produces:** A pending confirmation on the session request with the story count, issue, and issue number. Confirm continues that same request into the digest. Cancel stores the cancellation and does not collect. `all` is rejected for every source except Juya.
- **Acceptance:** `all` includes every eligible story in the issues that request selected, and it does not crawl an unlimited archive. More than 20 stories asks for confirmation and does not summarize first. Twenty or fewer proceeds. Cancellation still works. A later message that is a new request replaces the pending confirmation.
- **Compatibility:** Numeric Juya counts are unchanged. This is not the clarify intent from B3.
- **Blocked by:** B6
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_chat.py tests/test_source_settings.py -q`

### B9 — Credential storage

- [x] **Do:** Store provider overrides encrypted, and resolve them only through `CredentialsProvider`.

- **Consumes:** B5 `secrets`. Environment and `.env` values used today by `llm.py` and the connectors.
- **Produces:** Fernet encryption with `AI_NEWS_AGENT_SECRET_KEY`. `GET /api/v1/settings/credentials` returns per name `status` (`ui`, `env`, `unset`, `unreadable`), `last4` for a readable secret, and the credential version. It never returns the value. `PUT /api/v1/settings/credentials/llm` saves `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` atomically. `PUT /api/v1/settings/credentials/{name}` saves one of `GITHUB_TOKEN`, `HUGGINGFACE_TOKEN`, `ZHIHU_ACCESS_SECRET`, `BILIBILI_SESSDATA`, `BILIBILI_BILI_JCT`, `BILIBILI_BUVID3`. `DELETE` clears the UI override. Names and bodies are redacted in logs. Without `AI_NEWS_AGENT_SECRET_KEY`, writes return 409. A ciphertext that cannot be decrypted is `unreadable`, not `unset`, and blocks that credential's work. Clearing a readable override falls back to the environment. A request keeps the credential version it started with.
- **Acceptance:** GET never contains the secret. A readable UI override wins over the environment. An unreadable override does not silently use the environment. Deleting an unreadable override restores the environment fallback. The LLM triple is saved or rejected together. Connectors and both LLM builders receive values from the provider. The process starts when no LLM configuration exists. An operation that needs an LLM says to configure it in Settings. Fake mode does not turn on by itself. Bilibili credentials stay editable while Bilibili is hidden. A command-line run that needs an encrypted override requires `AI_NEWS_AGENT_SECRET_KEY` and does not require the access token.
- **Compatibility:** Env-only deployments keep working when no UI override exists. Local loopback write rules arrive in B11; until then, do not document B9 as remotely safe.
- **Blocked by:** B5
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_credentials.py tests/test_api_settings.py -q`

### B10 — Credential tests and health

- [x] **Do:** Test a configured credential with a real provider call, and record health against the credential version.

- **Consumes:** B9 `CredentialsProvider` and version.
- **Produces:** `POST /api/v1/settings/credentials/{name}/test`. GitHub uses an authenticated rate-limit call. Hugging Face uses `whoami`. The LLM sends one minimal request to the configured model. Zhihu uses a minimal authenticated call. The result is `ok` or a short sanitized reason, with no key and no raw provider body. Health observations store source, time, credential version, kind (`connector` or `test`), and result (`ok`, `auth_error`, `unavailable`, `rate_limited`, `timeout`, or another distinct failure). `GET /api/v1/sources` includes the current-version summary. Replacing a credential marks older observations stale.
- **Acceptance:** A test distinguishes authentication failure from the source being unavailable. Timeout, rate limiting, and authentication failure stay distinct. The newest observation for the current version is the current health. A successful authenticated call clears an earlier authentication error for that version. After a credential change, health is stale until a new test or connector result exists. Tests are time-bounded.
- **Compatibility:** A failed test does not change the saved value.
- **Blocked by:** B9
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_credentials.py tests/test_api_settings.py -q`

### B11 — Owner access token

- [x] **Do:** Require a bearer token in remote mode, and limit unauthenticated credential writes to loopback in local mode.

- **Consumes:** B9 credential routes. `create_app` CORS middleware.
- **Produces:** Remote mode is an explicit server setting. Startup fails in remote mode when `AI_NEWS_AGENT_ACCESS_TOKEN` is missing. Every `/api/v1` route except `/health` requires `Authorization: Bearer`, compared in constant time. A missing or wrong token is 401. Local mode may run without a token. Credential writes in local mode accept only `127.0.0.1` and `::1`. CORS origins come from `AI_NEWS_AGENT_CORS_ORIGINS` when set, with no wildcards. Allowed methods include PUT. Allowed headers include Authorization. A remote-mode LLM base URL must be HTTPS on a public address, including after a redirect, unless a server-side switch allows a local endpoint. The browser contract is `sessionStorage`; this task does not add a Remember-me flag.
- **Acceptance:** Remote startup without a token refuses to start. `/health` answers without a token. Other routes without a token return 401. A mismatch returns 401. Local mode without a token still serves loopback reads, and a non-loopback credential write is refused. A private or plain-HTTP LLM base URL is 400 in remote mode and is not saved. Failed-authentication throttling, body size, and concurrent-spend bounds are either enforced here or named in the README as reverse-proxy duties. CORS is not treated as authentication.
- **Compatibility:** Local fake-mode and the existing loopback dev origins keep working without a token.
- **Blocked by:** B9
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_access_token.py tests/test_api_settings.py -q`

### B12 — Backend contract check

- [ ] **Do:** Prove the follow-up fields, the settings routes, and the v4 migration in one offline run.

- **Consumes:** B1–B11.
- **Produces:** OpenAPI lists the follow-up fields, the settings routes, and `followup_action` limited to `deep_dive` and `ask`.
- **Acceptance:** `GET /openapi.json` contains those contracts. `uv run pytest -q` passes with no network. A v3 fixture migrates to v4.
- **Blocked by:** B1, B2, B3, B4, B5, B6, B7, B8, B9, B10, B11
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** the schema-presence test is test-first; the rest is the existing suite.
- **Verification:** `uv run pytest -q`

## TDD note (Agent mode)

Per subtask, obey `TDD suitable`. `yes` means strict test-first. **B9** without **B11** is an unfinished security boundary: do not point the frontend Keys tab at it early.

## Plan changelog

| Date | Change | Kind |
|---|---|---|
| 2026-10-30 | Split from `2026-10-20-targeted-followups-plan.md`. Backend follow-ups are B1–B4. Settings, keys, and sign-in from the settings spec are B5–B11. | material |
| 2026-10-30 | Add digests.py, llm.py, composition.py to B2 map | equivalent |
| 2026-10-31 | Add collection_outcomes.py and its test file to B4 map | equivalent |
| 2026-11-02 | Assign `digest_entries.language` column to B5 v4 DDL; B7 consumes it | equivalent |
| 2026-11-02 | B6 file map includes request, ranking, conversation, session_service, parse, github, ResolvedRequestOut | equivalent |
| 2026-11-02 | B7 file map includes models, summarizer, digest_views, digests DTO; source_settings language API; digest_store entry language | equivalent |
| 2026-11-02 | B8 file map includes juya connector, parse/workflow, ranking, chat, session_service, sessions API, request confirm flag | equivalent |
| 2026-11-02 | B9 file map adds sources, deps, pyproject cryptography; llm.py unchanged | equivalent |
| 2026-11-02 | B10 file map adds credential health store, probes, and sources summary | equivalent |
| 2026-11-05 | B11 file map adds `access.py`, `api/auth.py`, `test_access_token.py`; service gains `--remote`; env vars `AI_NEWS_AGENT_REMOTE`, `AI_NEWS_AGENT_ACCESS_TOKEN`, `AI_NEWS_AGENT_CORS_ORIGINS`, `AI_NEWS_AGENT_ALLOW_LOCAL_LLM`; reverse-proxy duties documented in README | equivalent |
