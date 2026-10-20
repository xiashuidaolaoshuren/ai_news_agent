# Remove the Gradio UI and the OpenClaw integration

Status: accepted

ADR-0008 kept Gradio as a transitional interface and retained the unversioned OpenClaw `/health`, `/digest`, and `/followup` routes alongside `/api/v1`. Milestone 8B has since delivered the Vue application on the session API, so both surfaces are now duplicate entrypoints that maintain their own routing, fallbacks, and tests while the browser UI is the supported chat interface.

The Gradio UI was a thin wrapper over `ChatService`'s non-session methods: `handle_message`, `handle_message_async`, and `handle_message_streaming_async`, with `InterfaceToolRouter.route` and `route_streaming` behind them. The OpenClaw integration added an unversioned HTTP router, a CLI client, an adapter for validating hint strings, and two skill documents, all of which mapped prompts onto flags and delegated back into `DigestServiceRuntime` and the same non-session router. Neither surface had a consumer left after the Vue application became the chat interface.

The removal deletes the Gradio application and its compatibility re-export module, the `adapters` package, the OpenClaw router, the `openclaw-digest` and `openclaw-followup` CLI subcommands, the `openclaw/` skill directory, the latency benchmark, the `gradio` dependency, and the tests that covered them. The now-dead shared paths are pruned as well: the non-session `ChatService` methods, `InterfaceToolRouter.route` / `route_streaming` with their `allow_digest` branch and OpenClaw guidance text, `OPENCLAW_GUIDANCE_FALLBACK`, and `handle_openclaw_structured_followup`. `DigestServiceRuntime` and the request-payload builders leave `app/digest_service.py`, which keeps only the `ai-news-agent service` uvicorn entry point. The output-style and output-language normalizers move from the deleted adapter into `digest_request_builder.py`, because the plain `digest` CLI command still uses them.

What remains is one supported chat surface: browser sessions over `/api/v1` with `ChatService.stream_events`, session-scoped structured follow-ups, and `InterfaceToolRouter.run_session_followup` for open-ended tool-agent answers. The CLI continues to provide one-shot digests, history search, and the service entry point. Shared-interface context stays for CLI structured follow-ups.

## Considered options (rejected)

- **Keep Gradio behind a `--legacy-ui` flag** — it would preserve a second presentation layer, a second streaming contract, and a UI dependency for no remaining user.
- **Keep the unversioned OpenClaw routes as compatibility aliases** — the external gateway configuration that used them is being retired, and the routes duplicate `/api/v1` composition and error handling.
- **Keep the OpenClaw client commands but drop the server routes** — the commands would have no reachable endpoint.
- **Keep the non-session `ChatService` and router paths for tests only** — production callers disappeared with the interfaces; keeping dead code behind tests extends the maintenance surface and hides real coverage gaps.
- **Delete `app/digest_service.py` entirely** — `main()` is still the process entry point for `ai-news-agent service`; only its OpenClaw runtime moves out.
- **Delete `interface_router.py` and `digest_request_builder.py`** — both remain in the live browser path and CLI request resolution.
- **Rewrite or delete historical design specs and ADRs** — they record past decisions; only this ADR and the README reflect the current surface.

## Consequences

- `frontend/openapi.json` and the generated client lose `GET /health`, `POST /digest`, and `POST /followup`; the Vue application needs no behavioral change.
- `pyproject.toml` no longer depends on `gradio`; the lockfile drops Gradio and its transitive packages.
- `ChatService` exposes only the session entry point and helpers used by `stream_events`; the tool agent is reached only through `run_session_followup`.
- `InterfaceToolRouter` keeps a narrower constructor (store, tool model, connector factories, interface name) and one method.
- The CLI keeps `digest`, `history-search`, `history-show`, `demo-db`, and `service`; the service now hosts only `/api/v1` and `/`.
- User-facing guidance no longer refers to Gradio; the Bilibili proxy warning asks for a service restart.
- Historical OpenClaw design documents remain in `docs/superpowers/specs/` for reference.
