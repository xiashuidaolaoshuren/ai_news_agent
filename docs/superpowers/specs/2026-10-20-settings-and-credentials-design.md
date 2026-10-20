# Settings panel, per-source settings, credentials, and access token

Status: draft for review
Date: 2026-10-20

## Goal

Give the web app one Settings area where a single user can configure each source, edit self-host API keys, and protect the backend with an access token, so the app can be deployed (frontend on Vercel, backend on a persistent host).

## Non-goals

- Multi-user accounts, roles, or per-user settings.
- The scheduled n8n delivery. It will add a Delivery tab here later and reuse the access token.
- Public visitor access, quotas and rate limiting (still a separate deployment decision per the 8A.1 spec).

## UI

- A **Settings** button in the sidebar footer opens a panel with tabs **Sources** and **Keys**.
- Each source chip in the composer gets a gear icon that opens that source's section in the panel.
- The composer's **"Per source" stepper is removed**. Counts live in per-source settings. This supersedes ADR-0010 decision 2 (the stepper); the source checkboxes remain session preferences. A new ADR-0013 records this.
- Sign-in screen when an access token is required and missing.

## Per-source settings (global profile)

One profile per source, shared by every conversation. Stored as a JSON document per source in a new `source_settings` table, validated by a Pydantic model per source.

| Source | Settings |
|---|---|
| Juya | `item_count`: 1 to 50 or `all`; `language`: `zh-CN` or `en` |
| GitHub | `keywords: list[str]` (max 10); `min_stars: int >= 0`; `language: str or null` |
| Hugging Face | `item_count`; `pipeline_tag: str or null` |
| OpenRouter | `item_count`; `free_only: bool` |
| Zhihu | `item_count` |
| Bilibili | none (hidden source) |

- Defaults reproduce today's behaviour: count 5, Juya `zh-CN`, no keywords.
- **Precedence:** values in the user's message (named count, topic, language) beat saved settings, which beat built-in defaults.
- **Juya `all`:** no cap on stories in the issue. Digest summarisation cost grows with story count, so the panel warns above 20.
- **Juya language** controls both the summary language (`DigestRequest.output_language`) and the entry labels (摘要 / 为什么重要 / 背景知识 versus Summary / Why it matters / Background). Labels come from the digest's language, via a small label table in the frontend `vm`, replacing the hard-coded strings in `EntryRow.vue`.
- **GitHub keywords:** used as topics for the GitHub query only when the message names no topic; a message topic wins. Keywords do not turn `topics_are_filters` on.
- `item_count` replaces `items_per_source` as the effective count. A session's stored `items_per_source` is ignored once a source has a setting; the column stays for old rows.

### API

- `GET /api/v1/settings/sources` returns all profiles with defaults filled.
- `PUT /api/v1/settings/sources/{name}` validates and saves one profile; `400` on invalid values; unknown or hidden source `404`.
- The request builder reads profiles through a `SourceSettingsService` injected in the composition root; connectors receive resolved values on `ConnectorRequest`, not the service.

## Credentials

### Scope

Editable: LLM (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`), `GITHUB_TOKEN`, `HUGGINGFACE_TOKEN`, `ZHIHU_ACCESS_SECRET`, `BILIBILI_SESSDATA`, `BILIBILI_BILI_JCT`, `BILIBILI_BUVID3`.

### Storage

- Encrypted rows in a new `secrets` table (name, ciphertext, updated_at), using Fernet with a key from `AI_NEWS_AGENT_SECRET_KEY`.
- Without that variable the Keys tab is read-only and explains how to enable it; the API refuses writes with `409`.
- Effective value = UI value if present, otherwise the environment/.env value. Clearing a UI value falls back to `.env`.
- Base URL and model are not secret but are stored in the same table for one code path.

### Write-only API

- `GET /api/v1/settings/credentials` returns per name: `status` (`ui`, `env`, `unset`) and `last4` for secrets. Never the value.
- `PUT /api/v1/settings/credentials/{name}` sets a value; `DELETE` clears the UI override.
- Values are never logged; request logging redacts these bodies.
- `POST /api/v1/settings/credentials/{name}/test` runs one cheap check: GitHub rate-limit call, Hugging Face `whoami`, LLM model list, Zhihu minimal authenticated call. Returns `ok` or a short reason.

### Applying changes

- A `CredentialsProvider` is the only place that resolves a credential. Connectors receive tokens from it instead of reading `os.environ` (replacing the reads in `connectors/github.py`, `connectors/huggingface.py`, `env.py`).
- Connectors are already built per digest, so token changes apply on the next run.
- The LLM model objects in `services/composition.py` are built once today. They become lazily rebuilt when the provider's LLM version counter changes, so no restart is needed. In fake mode the LLM settings are ignored.
- Bilibili credentials are editable even though the source is hidden.

### Source health

- `GET /api/v1/sources` gains a `health` field per source from the last digest's connector warnings (for example GitHub HTTP 401 gives `auth_error`) and the last `test` result.
- The composer chip shows a warning dot with a tooltip; the Keys tab links to the matching field. Observed in the running app: GitHub currently fails with HTTP 401.

## Access token

- `AI_NEWS_AGENT_ACCESS_TOKEN` set: every `/api/v1` route except `/health` requires `Authorization: Bearer <token>`; compared in constant time; `401` otherwise.
- The frontend stores the token in `localStorage` and attaches it through the generated client's headers. Trade-off recorded in ADR-0013: `localStorage` is readable by script on the page (XSS), acceptable for one user on one origin. SSE requests send the same header.
- Not set: behaviour as today, and all `/settings/credentials` write routes accept loopback clients only (`127.0.0.1`, `::1`), so a remote backend without a token cannot have keys changed.
- CORS allowlist gains a configurable origin list (`AI_NEWS_AGENT_CORS_ORIGINS`) for the deployed frontend; wildcards stay forbidden.

## Data

SQLite schema v2 to v3 via the existing backup-then-transactional migration: adds `source_settings` and `secrets`. Existing data untouched.

## Error handling

| Case | Behaviour |
|---|---|
| Invalid setting | 400 with field message; panel shows it inline |
| Secret key missing | writes 409; panel read-only with instructions |
| Wrong `AI_NEWS_AGENT_SECRET_KEY` (cannot decrypt) | credential treated as `unset` with a warning; no crash |
| Test fails | message shown, value kept |
| Token wrong or missing | 401; sign-in screen |

## Testing (TDD; one failing test per behaviour)

Backend:
1. Settings model validation per source; defaults reproduce current behaviour.
2. `PUT` and `GET` round-trip; invalid values 400.
3. Precedence: message count beats setting beats default.
4. Juya `all` removes the cap; language sets `output_language`.
5. GitHub keywords used only when message names no topic.
6. Secrets: encrypt/decrypt round trip; `GET` never returns the value; `last4`; clear falls back to env; wrong key degrades.
7. Provider resolves UI before env; connectors take tokens from it.
8. LLM client rebuilds when LLM credentials change.
9. Credential test endpoint maps success, 401, timeout.
10. Access token: 401 without header, 200 with, `/health` open; no token and non-loopback write is refused.
11. Migration v2 to v3 keeps data and creates a backup.

Frontend:
12. Settings panel renders sources from API and saves; inline errors.
13. Gear opens the right section; stepper removed; composer count not sent.
14. Keys tab shows status only, write-only inputs, read-only mode.
15. Sign-in on 401; token attached to requests and SSE.
16. Entry labels follow digest language.
17. Health dot appears for `auth_error`.

Verification: generated client compiles, existing suites pass, manual run in fake and live mode.

## Open items

None blocking. Sequencing: ship per-source settings first, then credentials, then access token, since each is independently usable.
