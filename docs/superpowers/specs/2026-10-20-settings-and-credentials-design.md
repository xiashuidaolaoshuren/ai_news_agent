# Settings panel, per-source settings, credentials, and access token

Status: agreed
Date: 2026-10-20
Review: agreed 2026-10-20. Vocabulary: [CONTEXT.md](../../../CONTEXT.md). Decisions: [ADR-0013](../../adr/0013-global-source-profiles.md), [ADR-0014](../../adr/0014-owner-access-and-credential-boundary.md).

## Goal

Give the app one Settings area where its single owner can configure each source, edit provider credentials, and protect a remotely reachable backend with an owner access token.

## Non-goals

- Multi-user accounts, roles, or per-user settings.
- The scheduled n8n delivery. It will add a Delivery tab here later and reuse the owner access token.
- Public visitor access. Remote mode is for the owner, not for anonymous visitors.

## UI

- A **Settings** button in the sidebar footer opens a panel with tabs **Sources** and **Keys**.
- Each visible source chip in the composer gets a gear icon that opens that source's section.
- The composer's **Per source** stepper is removed. Counts live in source profiles. This supersedes ADR-0010 decision 2. Source checkboxes remain session preferences.
- A sign-in screen appears when an owner access token is required and missing or rejected. A rejected token keeps the field masked and shows the inline error `That token was rejected.` with the app still locked.
- On the first run after session counts stop being active, show a one-time notice that new requests use the global source profiles. Historical messages keep the counts they ran with.

## Source profiles

One profile per source, shared by every conversation and by the web app and command-line interface when they use the same database. Explicit command-line options override a profile, just as explicit message options do. Stored as a JSON document per source in `source_settings`, validated by a Pydantic model per source.

| Source | Settings |
|---|---|
| Juya | `item_count`: 1 to 50 or `all` |
| GitHub | `item_count`: 1 to 50; `keywords: list[str]` (max 10); `min_stars: int >= 0`; `language: str or null` |
| Hugging Face | `item_count`: 1 to 50; `pipeline_tag: str or null` |
| OpenRouter | `item_count`: 1 to 50; `free_only: bool` |
| Zhihu | `item_count`: 1 to 50 |
| Bilibili | none. Hidden from discovery, but its section remains in Settings and says "Hidden from source selection" |

- Defaults reproduce today's behaviour: count 5, no keywords, OpenRouter `free_only` false.
- **Item count** means up to that many eligible display entries. Filters, timeframe, and Hugging Face model-family grouping still apply. Raise collection limits where the source supports it. If fewer eligible entries exist, show the shortfall in the resolved request line as returned of requested (for example `3 of 5`). Do not widen the timeframe, relax filters, or split packaging variants to fill the count.
- **Juya `all`** means every eligible story in the issues selected by that request, after topic and timeframe filtering. It removes the ordinary collection and selection caps for that bounded selection. It does not crawl an unlimited archive. Before summarizing more than 20 stories, ask for confirmation. Cancellation remains available. `all` is not offered for other sources.
- **Precedence:** an explicit message or command-line option beats the saved profile, which beats the built-in default. A count named for one source overrides only that source. "Each" overrides every selected source. An unqualified count means per selected source, not a total across sources. Show the resolved counts.
- **GitHub keywords** are topics for the GitHub query only when the message names no topic. A message topic wins. Keywords do not turn `topics_are_filters` on.
- A session's stored `items_per_source` is historical. New requests ignore it once global profiles exist. **Run again** still uses the count recorded on the original resolved request.
- The column stays so old rows and Run again can read it. Do not copy differing per-session counts into one global profile.

### Output language

Output language is a global digest preference, not a Juya setting: `source_default`, `en`, or `zh-CN`. The initial value is `source_default`, which keeps each source's current presentation language. English or Simplified Chinese applies to generated text and entry labels across the digest. Original titles, quotations, model names, and identifiers stay as collected.

A language named in the message or on the command line overrides the saved preference for that run. Each digest entry records the language it was generated in, so reopening it keeps those labels.

`GET /api/v1/settings/language` and `PUT /api/v1/settings/language` read and save this preference.

### API

- `GET /api/v1/settings/sources` returns every profile, including hidden sources, with defaults filled and a `hidden` flag.
- `PUT /api/v1/settings/sources/{name}` validates and saves one profile. Invalid values return `400`. An unknown source returns `404`. A hidden source remains configurable.
- The request builder reads profiles through a `SourceSettingsService` injected in the composition root. Connectors receive resolved values on `ConnectorRequest`, not the service. The command-line digest uses the same service when it opens that database.

## Credentials

### Scope

Editable provider credentials: LLM configuration (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` as one configuration), `GITHUB_TOKEN`, `HUGGINGFACE_TOKEN`, `ZHIHU_ACCESS_SECRET`, `BILIBILI_SESSDATA`, `BILIBILI_BILI_JCT`, `BILIBILI_BUVID3`.

Bilibili credentials stay editable while Bilibili is hidden.

### Storage

- Encrypted rows in a new `secrets` table (name, ciphertext, updated_at), using Fernet with a key from `AI_NEWS_AGENT_SECRET_KEY`.
- Without that variable the Keys tab is read-only and explains how to enable it. The API refuses writes with `409`.
- Effective value = saved override if it can be read, otherwise the environment or `.env` value. Clearing a UI value falls back to the environment.
- The LLM key, base URL, and model are saved and validated together. A request captures one configuration version at start and keeps it until it finishes. Later edits apply to later requests.
- In remote mode, an LLM base URL must be HTTPS on a public address. A redirect is checked the same way. Private-network or plain-HTTP endpoints are rejected unless server configuration outside the web UI explicitly allows them. Local development can enable a local model server through that same server-side switch.

### Write-only API

- `GET /api/v1/settings/credentials` returns per name: `status` (`ui`, `env`, `unset`, `unreadable`), `last4` for readable secrets, and the credential version. Never the value. LLM status describes the whole configuration.
- `PUT /api/v1/settings/credentials/llm` sets the LLM configuration atomically. `PUT /api/v1/settings/credentials/{name}` sets one other value. `DELETE` clears the UI override. Deleting an unreadable override is allowed and restores environment fallback.
- Values are never logged. Request logging redacts these bodies.
- `POST /api/v1/settings/credentials/{name}/test` checks the configured operation, not merely that a token parses. GitHub uses an authenticated rate-limit call. Hugging Face uses `whoami`. The LLM sends one minimal request to the configured model, and the UI says it may incur a small charge. Zhihu uses a minimal authenticated call. Tests are owner-initiated, time-bounded, and return `ok` or a short sanitized reason. They do not return keys or raw provider bodies. A source test distinguishes authentication failure from the source being unavailable.

### Applying changes

- A `CredentialsProvider` is the only place that resolves a provider credential. Connectors and both LLM clients receive values from it instead of reading `os.environ` at call time. This includes the command-line path for the same database.
- Connectors are already built per digest, so a readable token change applies on the next run.
- LLM clients are built lazily for the current configuration version. If no LLM configuration can be resolved, the process still starts. Settings, history, credential tests that do not need the LLM, and saved-evidence deep dives work. An operation that needs an LLM returns a clear "Configure an LLM in Settings" result. Fake mode remains an explicit offline mode, not an automatic fallback.
- A command-line run that needs an encrypted override requires `AI_NEWS_AGENT_SECRET_KEY`. The owner access token is not required for the command line.

### Unreadable override

If `AI_NEWS_AGENT_SECRET_KEY` is missing or wrong and a saved ciphertext cannot be decrypted, that credential's status is `unreadable`. It is not `unset`. Operations that depend on it fail with an explicit error. Other sources continue. The owner can restore the key, replace the override, or delete it. The app must not silently use the environment value while an unreadable override exists.

### Source health

Health is a list of observations, not one blended field. Each observation records the source, time, credential version, kind (`connector` or `test`), and result (`ok`, `auth_error`, `unavailable`, `rate_limited`, `timeout`, or another distinct failure).

- Changing a credential marks older observations for that credential stale. The UI shows "Not checked since update" until a new test or connector result exists.
- The newest observation for the current credential version determines current health.
- A successful authenticated call clears an earlier authentication error for that version.
- Timeout, rate limiting, and authentication failure stay distinct.
- `GET /api/v1/sources` includes this health summary. The composer chip shows a warning dot and tooltip. The Keys tab links to the matching field.

## Access token

Credential editing and owner-access protection ship together.

- **Remote mode** is an explicit server configuration. Startup fails when `AI_NEWS_AGENT_ACCESS_TOKEN` is missing. Every `/api/v1` route except `/health` requires `Authorization: Bearer <token>`, compared in constant time. A mismatch or missing header returns `401`.
- **Local mode** may run without a token. Credential writes then accept loopback clients only (`127.0.0.1`, `::1`). Local mode must not sit behind a reverse proxy that presents remote clients as loopback; that deployment uses remote mode, which does not trust the client address.
- The browser stores the token in `sessionStorage` and attaches it on API and SSE requests. Closing the tab ends that persistence. A persistent "Remember me" control is deferred. Script access on the page origin remains a risk and is accepted only for this single-owner deployment.
- CORS allowlist gains `AI_NEWS_AGENT_CORS_ORIGINS` for the deployed frontend. Wildcards stay forbidden. Allowed methods include `PUT`. Allowed headers include `Authorization`. CORS is not authentication.

### Remote deployment requirements

Supported remote mode also requires HTTPS, a bounded request body size, a bound on concurrent operations that can spend provider money, and throttling of failed authentication attempts. The backend or a documented reverse proxy may enforce the last three. Public visitor isolation remains out of scope.

## Data

The repository is already schema version 3. This change migrates v3 to v4 through the existing backup-then-transactional migration. It adds `source_settings`, `secrets`, the global language preference, and credential-health observations. Existing digest, session, and message rows stay. A backup failure aborts the migration.

## Error handling

| Case | Behaviour |
|---|---|
| Invalid setting | 400 with a field message; the panel shows it inline |
| Secret key missing | writes 409; panel read-only with instructions |
| Saved override cannot be decrypted | status `unreadable`; dependent operations fail until the owner resolves it |
| Test fails | sanitized message shown, value kept |
| Token wrong or missing in remote mode | 401; sign-in screen. A rejected token shows `That token was rejected.` and keeps the app locked |
| Remote mode without a configured token | process refuses to start |
| LLM endpoint fails the remote-mode network rule | 400; value not saved |
| LLM required but not configured | the operation explains that Settings must be completed; other operations continue |

## Testing (TDD; one failing test per behaviour)

Backend:

1. Settings validation per source, including GitHub `item_count`. Defaults reproduce current behaviour.
2. `PUT` and `GET` round-trip. Invalid values return 400. A hidden source remains readable and writable.
3. An unqualified count applies per selected source. A source-scoped count overrides only that source.
4. Count means up to N eligible entries. A shortfall is reported as returned of requested without relaxing filters or timeframe.
5. Juya `all` covers every eligible story in the selected issues and asks for confirmation above 20.
6. Output language defaults to source default. English or Chinese applies across the digest, and a message language overrides it. Entry language is stored.
7. GitHub keywords are used only when the message names no topic.
8. Web and command-line runs using the same database resolve the same profiles. An explicit command-line option wins.
9. Secrets encrypt and decrypt. `GET` never returns the value. Clear falls back to the environment. An undecryptable override is `unreadable` and blocks dependent work.
10. The LLM configuration saves atomically. A request keeps the version it started with.
11. Provider resolution prefers a readable UI override over the environment. Connectors and LLM clients take values from the provider.
12. The process starts with no LLM configured. An LLM operation returns the Settings guidance. Fake mode does not turn on by itself.
13. Credential tests cover the configured operation, including the minimal LLM call, and sanitize failures.
14. Health observations are versioned. Replacing a credential makes old observations stale.
15. Remote mode refuses startup without a token. Requests without the token return 401, and `/health` stays open. Local mode without a token refuses a non-loopback credential write.
16. A remote-mode private or plain-HTTP LLM endpoint is rejected, including by redirect.
17. Migration from the current v3 schema to v4 keeps data and creates a backup.

Frontend:

18. Settings renders sources from the API and saves, including inline errors and the hidden-source label.
19. Gear opens the right section. The stepper is gone. The composer does not send a shared count.
20. The one-time notice explains the move from session counts to global profiles.
21. Keys shows status only, write-only inputs, read-only mode, and the unreadable state.
22. The LLM fields save together. The test control discloses the possible small charge.
23. Sign-in on 401. The token is attached to requests and SSE and is stored in `sessionStorage`. A rejected token shows the inline error and keeps the app locked.
24. Entry labels follow the digest entry's recorded language.
25. The health dot follows the current credential version.

Verification: generated client compiles, existing suites pass, and a manual run covers fake mode, live mode, and remote-mode startup without a token.

## Open items

None blocking. Sequencing: ship source profiles and output language first. Ship credential editing and owner-access protection together after that.
