# OpenRouter source, source visibility, and related stories

Status: draft for review
Date: 2026-10-20

## Goal

Add OpenRouter as a news source, hide Bilibili from the web UI without removing it, and mark entries that cover the same model or product as related instead of dropping them.

## Non-goals

- OpenRouter usage rankings and price-change history (v2, see below).
- Removing the Bilibili connector, its credentials, or its tests.
- Merging or deleting near-duplicate stories.
- Per-source settings (see the settings spec).

## Source role

ADR-0001 gives each source one job. OpenRouter's job: **models you can call through one API: newly listed, free, and priced.** Hugging Face keeps its job: open-weight models that are trending. A model can legitimately appear in both.

## OpenRouter connector (v1)

- New `SourceKind.OPENROUTER = "openrouter"` and `connectors/openrouter.py`.
- One unauthenticated `GET https://openrouter.ai/api/v1/models`. The key is optional and unused in v1.
- Keep models whose `created` timestamp falls inside the request timeframe. The OpenRouter default timeframe is **7 days** when the request gives none, because "today" is often empty.
- When `topics_are_filters` is true, keep only models whose id, name or description match a topic (same rule as other connectors).
- Item fields: `source_id` = model id; `title` = model name; `url` = `https://openrouter.ai/<model id>`; `source_evidence` = provider (id prefix), created date, context length, input and output price per million tokens, `is_free` (id ends with `:free` or both prices are zero), input modalities.
- Failure (HTTP error, timeout, malformed JSON) returns zero items plus a `ConnectorWarning`; it never fails the digest.
- Unverified facts, to be confirmed against one live call during implementation and recorded in the plan: exact field names of the `/models` payload and whether prices are strings per token. The parser is written against a captured fixture, not against this spec's wording.

### Ranking

Kind-aware score: recency first, small boost for free models. Section order for mixed digests stays intent-first, otherwise Juya, Hugging Face, OpenRouter, GitHub, Zhihu (Bilibili last).

### API and frontend

- `OpenRouterDigestEntryView` joins the `DigestEntryView` union in `api/schemas/digests.py`; regenerate `frontend/openapi.json` and the generated client.
- Frontend: kind and label mapping, a logo, and an entry metrics line (context size, $/M in and out, "Free" badge).
- Typed-message detection: "openrouter" routes to the connector. Tool registry and follow-up context registration follow the Zhihu change as the checklist (about 25 backend files touch a source name).
- `FakeOpenRouterConnector` in `sources.py` plus a fixture file, matching the existing fake pattern.
- New ADR-0012 records the source role.

### Deferred (v2)

- **Price/context change detection:** needs a daily snapshot table; its own spec.
- **Usage rankings:** no documented API. A throwaway spike decides whether scraping is reliable; if not, drop it.

## Hiding Bilibili

- New env var `AI_NEWS_AGENT_HIDDEN_SOURCES`, comma list, **default `bilibili`**. Read at request time.
- `GET /sources` omits hidden names. The catalog order becomes: juya, huggingface, openrouter, github, zhihu, bilibili.
- `ALLOWED_SOURCES`, the connector, `SourceKind`, credentials and tests stay.
- Typed requests ("bilibili videos about X") still work: hiding is a UI catalog rule only.
- The composer drops hidden names from a loaded session's `connector_names` before display. If that leaves none, it falls back to the catalog defaults. The drop is local; it is not PATCHed until the user changes a preference.
- History filter's source dropdown uses the same catalog.
- Setting the variable to an empty string shows every source.

## Related stories

- After ranking, a pure function groups selected entries that share a normalised model or product token (for example "MiniMax M3.1 Flash"), using title tokens with version suffixes; threshold chosen conservatively to avoid false links.
- Each member gets `related_display_ranks: list[int]` on its API view (default empty). Nothing is removed and ranks are unchanged, so `dN:rN` tokens stay valid.
- Frontend shows a "Related: #1" chip that scrolls to the target entry.
- Markdown rendering is unchanged.

## Error handling

| Case | Behaviour |
|---|---|
| OpenRouter unreachable | warning, other sources unaffected |
| Zero models in window | normal empty result (the zero-results suggestion is in the follow-up spec) |
| Session lists only hidden sources | composer falls back to defaults |

## Testing (TDD; one failing test per behaviour)

1. Parser turns the fixture into items with correct evidence; free detection for `:free` and zero price.
2. Timeframe filter keeps only in-window models; 7-day default.
3. Topic filter applies only with `topics_are_filters`.
4. HTTP and JSON failure give a warning and no items.
5. Ranking boosts free models and orders sections.
6. Digest view maps OpenRouter evidence; OpenAPI regenerated and client compiles.
7. `/sources` hides names from the env var; empty value shows all; typed bilibili request still routes.
8. Composer drops hidden names from a session.
9. Related grouping links the MiniMax pair, leaves unrelated entries alone, never changes rank.
10. Verification: fake-mode digest with OpenRouter selected; one live call to the real endpoint.

## Open items

None blocking. The `/models` field names are verified in implementation against the captured fixture.
