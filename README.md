# AI News Research Agent

Local-first Python agent that generates **on-demand AI news digests** from **Juya** (default daily bulletin), optional **Hugging Face** trending models, optional **GitHub** trending-repo signals, optional **Zhihu** practitioner insights, and conservative **Bilibili**-oriented sources. It ranks candidates, summarizes them with an LLM (or offline fakes), persists runs to SQLite, and exposes a **CLI**, a local **HTTP API**, and a **browser UI**.

Design details: [AI News Research Agent design](docs/superpowers/specs/2026-05-02-ai-news-research-agent-design.md).

**Milestone 1 (Local Digest MVP)** is complete: LangGraph workflow, storage, connectors, ranking, summarization, chat follow-ups, CLI smoke mode, and tests.

**Milestone 2 (LLM tool usage layer)** is complete: bounded tool-calling for follow-up inspection and connector search; live browser sessions use a tool agent for open-ended follow-ups. Plan: [Milestone 2 implementation plan](docs/superpowers/plans/2026-05-21-llm-tool-usage-layer-plan.md).

**Milestone 3 (OpenClaw integration)** was removed in October 2026 together with the Gradio chat UI; the browser UI and CLI are the supported surfaces. See [ADR-0011](docs/adr/0011-remove-gradio-ui-and-openclaw-integration.md). The historical design remains at [OpenClaw integration design](docs/superpowers/specs/2026-06-08-openclaw-integration-design.md).

**Milestone 6 (AI ecosystem and practitioner signals)** is complete: opt-in Hugging Face trending-model and Zhihu practitioner-insight connectors, kind-aware ranking, CLI/API source names, and dedicated search tools. Bare digests stay Juya-only. Design: [Milestone 6 design](docs/superpowers/specs/2026-08-16-ai-ecosystem-and-practitioner-signals-design.md). ADR: [ADR-0002](docs/adr/0002-milestone-6-ecosystem-and-practitioner-signals.md).

## Prerequisites

- Python **3.11+** (see [.python-version](.python-version) for the pinned dev version)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip + venv

## Install

From the repo root:

```bash
uv sync --group dev
```

Without uv:

```bash
pip install -e .
pip install "pytest>=8.0"
```

If `import ai_news_agent` fails outside an editable install, use `PYTHONPATH=src` or install with `-e`.

## Environment variables

Copy [`.env.example`](.env.example) to `.env` and fill values as needed (never commit secrets).

**Local entrypoints auto-load `.env`** when you run `ai-news-agent`. Lookup order: `./.env` in the current working directory, then the first `.env` found in parent directories. Variables already exported in your shell are **not** overwritten.

| Variable | When needed | Purpose |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Live digest + live browser tool follow-ups | Digest summarization (`build_chat_model`) and tool-calling follow-ups (`build_tool_chat_model`) via [`llm.py`](src/ai_news_agent/llm.py) |
| `OPENAI_BASE_URL` | Optional | Custom gateway / compatible endpoint (applies to both summarization and tool agent) |
| `OPENAI_MODEL` | Optional | Model name (default `gpt-4o-mini`) |
| `GITHUB_TOKEN` | Optional | Higher GitHub API rate limits ([`connectors/github.py`](src/ai_news_agent/connectors/github.py)) |
| `HUGGINGFACE_TOKEN` | Optional | Higher Hugging Face Hub rate limits ([`connectors/huggingface.py`](src/ai_news_agent/connectors/huggingface.py)) |
| `ZHIHU_ACCESS_SECRET` | Live Zhihu practitioner search | Zhihu Developer Platform Access Secret, sent as Bearer ([`env.py`](src/ai_news_agent/env.py)) |
| `BILIBILI_SESSDATA` | Optional | Bilibili session token ([`env.py`](src/ai_news_agent/env.py)) |
| `BILIBILI_BILI_JCT` | Optional | Bilibili CSRF token (often required with `SESSDATA`) |
| `BILIBILI_BUVID3` | Optional | Bilibili device id cookie (helps avoid HTTP 412) |
| `BILIBILI_HTTP_CLIENT` | Optional | `curl_cffi`, `httpx`, or `aiohttp` (if installed in bilibili-api) |
| `BILIBILI_PROXY_URL` | Optional | HTTP proxy for bilibili-api requests |
| `BILIBILI_IMPERSONATE` | Optional | Browser TLS fingerprint for `curl_cffi` (e.g. `chrome131`) |
| `BILIBILI_TIMEOUT_SECONDS` | Optional | Request timeout override for bilibili-api |

SQLite defaults to `./digest.sqlite` in the current working directory unless you pass `--db-path`. Database files matching `*.db` are gitignored.

## Quick start (offline, no API keys)

Smoke acceptance tests (no network):

```bash
uv run pytest tests/test_mvp_smoke.py -q
```

One-shot fake digest (deterministic connectors + summarizer). Omitted `--sources` stays **Juya-only**:

```bash
uv run ai-news-agent digest --fake
uv run ai-news-agent digest --fake --sources huggingface
uv run ai-news-agent digest --fake --sources zhihu
uv run ai-news-agent digest --fake --sources huggingface,zhihu,github
```

Start the local service in offline (fake) mode, then use the web UI (see [Web frontend](#web-frontend-milestone-8b)):

```bash
uv run ai-news-agent service --fake
```

Try **“Give me today's AI digest”**, then **“show sources”** (structured follow-up). Try an open-ended question such as **“Why does the top item matter?”** to see fake tool-agent behavior (fixed offline reply, not live search).

## Live digest (network + LLM)

Requires `OPENAI_API_KEY` (in `.env` or your shell). Optionally set `GITHUB_TOKEN`, `HUGGINGFACE_TOKEN`, and `ZHIHU_ACCESS_SECRET` for reliability.

Bare request (Juya-only default):

```bash
uv run ai-news-agent digest --timeframe today
```

Explicit mixed sources (GitHub + Bilibili, no Juya):

```bash
uv run ai-news-agent digest --sources github,bilibili --topics "RAG,agents" --timeframe today
```

Hugging Face trending models (opt-in; Hub popularity is not model quality):

```bash
uv run ai-news-agent digest --sources huggingface --topics RAG --timeframe today
```

Zhihu practitioner insights (opt-in; official search only, no page crawl):

```bash
uv run ai-news-agent digest --sources zhihu --topics RAG --timeframe today
```

Useful flags:

- `--sources` — comma-separated: `juya`, `huggingface`, `github`, `zhihu`, `bilibili` (default: `juya`)
- `--topics` — comma-separated topic strings (omit for built-in defaults)
- `--timeframe` — passed through to connectors (e.g. `today`)
- `--top-n`, `--max-items` — ranking/collection limits
- `--db-path` — SQLite path for [`DigestStore`](src/ai_news_agent/storage.py)

### Historical digest search (CLI)

Search and reopen **persisted** digest items from SQLite (no live connector calls, no Hub enrich-on-open):

```bash
uv run ai-news-agent history-search \
  --query "RAG agents" \
  --sources huggingface,zhihu \
  --since 2026-08-01 \
  --db-path ./digest.sqlite

uv run ai-news-agent history-show d12:r3 --db-path ./digest.sqlite
```

`history-search` flags: `--query`, `--sources`, `--topics`, `--since`, `--until` (YYYY-MM-DD, UTC), `--limit` (default 10), `--db-path` (same default as `digest`). Exit **0** on success, including **zero matches**; **2** for validation errors (bad source, date range, or token); **1** for runtime failures.

`history-show` prints one saved item by `d<digest_id>:r<rank>` token. Exit **0** when found; **2** when not found or token invalid.

The web chat supports the same history prompts (`search history …`, `open history dN:rN`).

Console entrypoint: [`ai-news-agent`](pyproject.toml) → [`cli.main`](src/ai_news_agent/cli.py).

## Chat behaviour

The browser UI and the HTTP API delegate to [`ChatService`](src/ai_news_agent/services/chat.py):

- **Historical digest search** (`search history …`, `open history dN:rN`) — SQLite-only lookup; intercepts **before** the digest workflow and **before** latest-digest follow-up routing. Works in **`--fake`** mode (offline, no tool agent). Opening a hit is **persist-only** and does **not** change latest-digest follow-up context (structured prompts still refer to the most recent digest run).
- **Digest requests** (phrases like “digest”, URLs, source toggles) run the **deterministic LangGraph workflow** — collect, rank, summarize, persist — with streaming progress, then stream the final digest text.
- **Follow-ups** use the latest saved digest from SQLite. Routing order:
  1. **Structured** prompts → instant answers from persisted traces (no LLM tools): sources, ranking / study-first, caveats.
  2. **Open-ended** or source-exploration questions → **bounded tool agent** when configured (live browser sessions call `run_session_followup` in [`interface_router.py`](src/ai_news_agent/tools/interface_router.py)).
  3. **Legacy fallback** → `chat_model.generate_followup_reply` only if no tool agent is configured (not used by default live mode).
  4. **Guidance** message if neither tool agent nor chat model is available.

Digest responses show live workflow progress (collecting, ranking, summarizing, etc.), then stream the final digest text incrementally in the chat bubble.

### Milestone 2 — Follow-up tools

**Deterministic digest** (unchanged): LangGraph path for digest keywords, targeted URLs/channels, and session source toggles.

**Follow-up modes** after a digest is saved:

| Mode | What it does | Example |
|------|----------------|---------|
| Structured | Fast answers from SQLite traces | `show sources`, `Which item should I study first?`, `Any confidence caveats?` |
| Tool agent | Bounded LangGraph loop over six registry tools | `Why does the top item matter for RAG agents?`, `Search GitHub for langgraph agents` |
| Legacy LLM | Grounded reply via `generate_followup_reply` | Only when `tool_agent_runner` is not set |
| Guidance | Static hint to use structured prompts | When no model or tool agent is configured |

Registry tools (live mode): `load_latest_digest`, `get_digest_item`, `get_source_trace`, `get_ranking_explanation`, `search_juya_ai_news`, `search_github_ai_news`, `search_bilibili_ai_news`, `search_huggingface_trending_models`, `search_zhihu_practitioner_insights` (see [`tools/registry.py`](src/ai_news_agent/tools/registry.py)).

**Fake mode (`service --fake`):**

- Digest: `FakeDigestModel` + fake Juya/Hugging Face/GitHub/Zhihu/Bilibili connectors (no API keys).
- Structured follow-ups: work as in live mode (deterministic from stored traces).
- Open-ended follow-ups: return a **fixed offline message** from the fake tool agent (no real tool-calling model, no connector search). Use structured prompts for reliable offline demos.

**Live mode:** requires `OPENAI_API_KEY` for both digest summarization and tool-calling follow-ups (`build_chat_model` + `build_tool_chat_model`).

### Example prompts (after a digest)

| Category | Example |
|----------|---------|
| Digest | `Give me today's AI digest` |
| History search | `search history for RAG agents from huggingface,zhihu since 2026-08-01` |
| History open | `open history d12:r3` |
| Structured | `show sources`, `Which item should I study first?`, `Any confidence caveats?` |
| Open-ended | `Why does the top item matter for RAG agents?` |
| Source exploration | `Search Juya for agent news`, `Search Hugging Face for trending RAG models`, `Search GitHub for langgraph agents`, `Search Zhihu for practitioner insights on RAG`, `Search Bilibili for RAG tutorials` |

In **fake mode**, open-ended and source-exploration prompts return the offline tool-agent guidance string, not live search results.

### Source toggles and selection

The web composer shows **session-sticky** checkboxes for `juya`, `huggingface`, `github`, `zhihu`, and `bilibili` (**Juya selected by default**). Each digest run uses the current checkbox selection via `DigestRequest.connector_names`. Use **Items per source** (default 5, range 1–20) to cap how many ranked items appear from each enabled source in mixed digests.

Bare digest requests (no source toggles or explicit `--sources`) resolve to **Juya-only** via [`DEFAULT_SOURCE_NAMES`](src/ai_news_agent/sources.py). Select multiple checkboxes or pass a comma-separated `--sources` list for a **mixed digest**; section order is primary intent first, otherwise Juya → Hugging Face → GitHub → Zhihu → Bilibili (empty sections omitted).

You can override the toggles for a single request with natural-language phrases:

- `Give me today's AI digest` (Juya-only default)
- `Give me today's AI digest from github only`
- `huggingface only digest today`
- `trending RAG models on hugging face`
- `zhihu practitioner insights on RAG`
- `bilibili only digest today`
- `use juya and huggingface for today's digest`

CLI and the web API share the canonical source registry in [`sources.py`](src/ai_news_agent/sources.py).

### Targeted digests (URLs and channels)

In chat, you can include GitHub repo URLs, Bilibili video URLs, or channel hints in the same message as “digest”. The app parses them via [`intent.py`](src/ai_news_agent/intent.py) and skips broad topic keyword search when explicit targets are present.

Examples:

- `Digest https://daily.juya.uk/` (Juya daily bulletin; use `--output-style editorial --output-language zh-CN` for a compact Chinese issue index)
- `Digest https://github.com/langchain-ai/langgraph`
- `Digest https://www.bilibili.com/video/BV1xxxxx`
- `Digest bilibili channel 285286947`
- `Digest github user openai and https://www.bilibili.com/video/BV1demo0001`
- `Give me today's AI digest` (Juya-only default topics + timeframe when mentioned)

**Juya targeting is website-only.** The legacy GitHub repo `jujuyaya/juya-ai-daily` is **rejected** with an actionable error pointing to `https://daily.juya.uk/` (see [`intent.py`](src/ai_news_agent/intent.py)).

If Bilibili requests fail with HTTP 412:

1. Confirm startup log shows `bilibili env: ... credential_available=True`.
2. If cookies are missing, set `BILIBILI_SESSDATA`, `BILIBILI_BILI_JCT`, and `BILIBILI_BUVID3` in `.env` (from browser cookies).
3. If cookies are loaded but you still see `anti_bot_blocked`, tune network settings:
   - `BILIBILI_HTTP_CLIENT=curl_cffi` (when installed)
   - `BILIBILI_IMPERSONATE=chrome131`
   - `BILIBILI_PROXY_URL=http://127.0.0.1:7890` (or your proxy)
4. Prefer specific video URLs when channel feeds are blocked.
5. After a run, ask **show caveats** to distinguish `auth_required_*` (login) vs `anti_bot_blocked` (WAF/fingerprint).
6. Some videos have **no CC/AI subtitles** at all; follow-up enrichment will show `subtitle_unavailable` (not a network or login failure).

### Logging

The service and CLI share structured logging to **terminal** and a rotating file (default: `logs/ai-news-agent.log`).

| Variable | Default | Purpose |
|----------|---------|---------|
| `AI_NEWS_AGENT_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `AI_NEWS_AGENT_LOG_PATH` | `logs/ai-news-agent.log` | Log file location |
| `AI_NEWS_AGENT_LOG_MAX_BYTES` | `2000000` | Rotate when file exceeds this size |
| `AI_NEWS_AGENT_LOG_BACKUP_COUNT` | `3` | Number of rotated backups kept |

On failures, the web UI shows a short user-friendly message; full stack traces are written to the terminal and log file.

## Local web API (Milestone 8A.1)

**8A.1 is local-only.** There is no authentication, visitor isolation, quota, or public deployment. Browser CORS allows only `http://127.0.0.1:5173` and `http://localhost:5173`. Do not expose this process beyond loopback.

`ai-news-agent service` starts one FastAPI app. It serves the browser API under `/api/v1` on loopback.

Offline (no network, no API key):

```bash
uv run ai-news-agent service --fake --host 127.0.0.1 --port 8765 --db-path ./digest.sqlite
```

Live (requires `OPENAI_API_KEY`, same as the CLI):

```bash
uv run ai-news-agent service --port 8765 --db-path ./digest.sqlite
```

Flags: `--host` (default `127.0.0.1`), `--port` (default `8765`), `--db-path` (default `./digest.sqlite`), `--fake`.

OpenAPI is the generated FastAPI document at `http://127.0.0.1:8765/docs`.

Browser routes:

| Method and path | Purpose |
|---|---|
| `GET /api/v1/health` | `{"status": "ok", "fake": bool}` |
| `GET /api/v1/sources` | Canonical sources, defaults, and opt-in metadata |
| `POST /api/v1/sessions` | Create a session |
| `GET /api/v1/sessions` | List sessions, newest activity first, opaque cursor |
| `GET /api/v1/sessions/{id}` | Session metadata |
| `PATCH /api/v1/sessions/{id}` | Rename or update source preferences |
| `DELETE /api/v1/sessions/{id}` | Delete an inactive session (`409` while a request is active) |
| `GET /api/v1/sessions/{id}/messages` | Transcript page; digest-linked assistant messages include `DigestView` |
| `POST /api/v1/sessions/{id}/messages` | Send a message; response is `text/event-stream` |
| `GET /api/v1/sessions/{id}/requests/{request_id}` | Durable request status (reconnect without resuming the byte stream) |
| `POST /api/v1/sessions/{id}/requests/{request_id}/cancel` | `202` only before digest persistence; `204` afterward |
| `GET /api/v1/sessions/search?q=` | Lexical session search, one hit per session, opaque cursor |
| `GET /api/v1/history/search` | Existing historical digest search |
| `GET /api/v1/history/{dN:rN}` | Persist-only historical item (`markdown`, optional structured `entry`, plus the `dN:rN` token) |

**DigestView presentation metadata** (additive, nullable on old digests):

- GitHub / Hugging Face entries may include `owner` (`name`, `profile_url`, `avatar_url`, `type` where `type` is `organisation` or `person`).
- GitHub entries may include `preview_image_url`, `stars`, `language`, and `stars_today` (`int` or `null` when the repo is absent from the daily trending page or the fetch failed).
- Hugging Face entries may include `base_model` (`string` or `null` when missing or blank). The family representative's value is used.
- Juya entries include `item_type` (`issue` or `story`), optional `issue` block (`id`, `date`, `url`, `cover_url`, `lead_title`), and optional `story` block (`number`, `section`, `original_url`) when in story mode.

**Milestone 8B additive fields** (old clients ignore them):

| Field | Where | Nullability |
|---|---|---|
| `digest_id` | `MessageOut`; SSE `digest` event (`DigestPayload`) | `null` on user messages and non-digest assistant messages. Required integer on the live `digest` event. |
| `warnings` | `MessageOut`; SSE `digest` event | Always a list. `[]` when the run saved none. |
| `digest_count` | `SessionOut` | Integer, never null. Counts only succeeded requests that have a `run_id`. |
| `active_request_id` | `SessionOut` | `string` or `null`. Set only while a request is `active`. |
| `source`, `status`, `count` | SSE `progress` event (`ProgressPayload`) | All three are `null` for non-connector lines. `status` is `running`, `done`, or `failed` when set. `count` is an integer on `done`. `stage` is always sent. |
| `topics` | `HistorySearchMatchOut` | Always a list, in saved digest order. `[]` when the digest has no topics. |

**Juya story mode (web only):** `POST .../messages` accepts optional `"juya_item_mode": "stories"` (default `"issue"`). This applies to that message only; the CLI stays issue mode. Replaying a finished `client_request_id` returns the saved digest regardless of new options.

Chat SSE (`POST /api/v1/sessions/{id}/messages`) uses `fetch` and a `ReadableStream`, not `EventSource`. Frames are `event: <name>` plus one JSON `data:` line. Event names, in order: `started`, `progress`, `delta`, `digest` (digest results only), then terminal `done` or `error`. A dropped client does not stop persistence: the assistant message is still saved. Reconnect by polling request status and reloading the transcript; the server does not resume a partial byte stream. Reusing a finished `client_request_id` replays the stored outcome and does not start a new run.

Example (service already running in fake mode):

```bash
curl -s http://127.0.0.1:8765/api/v1/health
curl -s -X POST http://127.0.0.1:8765/api/v1/sessions
```

## Web frontend (Milestone 8B)

The Vue app lives in `frontend/`. It talks to the same local service on port `8765`. Vite serves the UI on `http://127.0.0.1:5173` (CORS is already allowlisted).

1. Start the API in fake mode (separate terminal):

```bash
uv run ai-news-agent service --fake --host 127.0.0.1 --port 8765 --db-path ./digest.sqlite
```

2. Install and run the dev server:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Optional: copy `frontend/.env.example` to `frontend/.env.local` to override `VITE_API_BASE_URL` (default `http://127.0.0.1:8765`).

Regenerate the typed client after backend OpenAPI changes:

```bash
npm --prefix frontend run gen:api:spec
npm --prefix frontend run gen:api
```

Scripts: `dev`, `build`, `typecheck`, `test`, `gen:api`, `gen:api:spec`. The client is generated with `@hey-api/openapi-ts` into `frontend/src/api/generated/`.

## Tests

Full suite:

```bash
uv run pytest
```

Milestone 1 smoke only:

```bash
uv run pytest tests/test_mvp_smoke.py -q
```

Optional live Bilibili URL smoke (network; uses a fixed public BV id):

```bash
RUN_LIVE_BILIBILI=1 uv run pytest -m live tests/test_connectors_bilibili_live.py -q
```

Set `BILIBILI_SESSDATA`, `BILIBILI_BILI_JCT`, and `BILIBILI_BUVID3` in `.env` if the live test reports HTTP 412.

## Known limits

**Connectors:**

- **Juya** is the **default bare digest** source (`daily.juya.uk` RSS + per-issue markdown enrichment). Target the website URL only; the legacy GitHub repo alias is rejected.
- **Hugging Face** is an **opt-in** Hub-native **trending models** source (global or topic/task-filtered). Ranking uses Hub `trending_score` plus downloads/likes tie-breakers; Hub popularity is **not** model quality. Models only — not datasets or Spaces.
- **GitHub** opt-in collection ranks repositories with a **momentum** score (star count × recency). This is a transparent heuristic for trending signal, **not** historical star velocity or true growth rate.
- **Zhihu** is an **opt-in practitioner-insight** source. Collection uses the official search API only (deterministic 实战/踩坑, 部署/成本, 评测/对比 lenses; max three calls). Rankable evidence is API relevance, lens match, and returned-text completeness — not popularity or freshness. Linked pages are never fetched. Thin results are discovery-only.
- **Bilibili** is **metadata-first** at digest time; follow-up enrichment can add transcripts when subtitle tracks exist. Many videos have no published CC/AI subtitles (`subtitle_unavailable`). Items are labeled lower confidence when content is thin (see [`connectors/bilibili.py`](src/ai_news_agent/connectors/bilibili.py)).

**Milestone 2 tool layer:**

- Tool agent has a **bounded iteration cap**; very complex multi-step questions may hit the fallback message.
- **Fake mode** does not run a real tool-calling model or live connector search for open-ended prompts.
- **Out of scope:** scheduled runs, cloud deployment, arXiv / generic RSS connectors, Hugging Face datasets/Spaces, Zhihu hotlist/direct-answer/page crawl, vector RAG (see design spec milestones).

**Milestone 8A.1 web API:**

- Local loopback only. No accounts, quotas, or public fake backend.
- Session search is lexical. Embeddings and memory RAG are later work.
- The CLI remains available for one-shot digests and history search.

## Documentation

- [Milestone 8A.1 web API and sessions plan](docs/superpowers/plans/2026-09-11-milestone-8a1-web-api-and-sessions-plan.md)
- [Milestone 8A.1 web API and sessions design](docs/superpowers/specs/2026-09-11-milestone-8a1-web-api-and-sessions-design.md)
- [Implementation plan (T1–T14, Milestone 1)](docs/superpowers/plans/2026-05-02-ai-news-research-agent-plan.md)
- [Milestone 2 LLM tool usage layer plan](docs/superpowers/plans/2026-05-21-llm-tool-usage-layer-plan.md)
- [ADR-0011 Remove Gradio UI and OpenClaw integration](docs/adr/0011-remove-gradio-ui-and-openclaw-integration.md)
- [Design spec](docs/superpowers/specs/2026-05-02-ai-news-research-agent-design.md)
- [Milestone 6 AI ecosystem and practitioner signals design](docs/superpowers/specs/2026-08-16-ai-ecosystem-and-practitioner-signals-design.md)
- [Milestone 6 implementation plan](docs/superpowers/plans/2026-08-16-ai-ecosystem-and-practitioner-signals-plan.md)
- [ADR-0002 Milestone 6 source roles](docs/adr/0002-milestone-6-ecosystem-and-practitioner-signals.md)
