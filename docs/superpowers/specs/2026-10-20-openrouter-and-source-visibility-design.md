# OpenRouter source, source visibility, and related stories

Status: agreed
Date: 2026-10-20
Review: agreed 2026-10-20. Vocabulary: [CONTEXT.md](../../../CONTEXT.md). Decisions: [ADR-0012](../../adr/0012-openrouter-source-role-and-related-coverage.md).

## Goal

Add OpenRouter as a news source, hide Bilibili from discovery without disabling it, and mark entries that cover the same model or product as related instead of dropping them.

## Non-goals

- OpenRouter usage rankings and price-change history (v2, see below).
- Removing the Bilibili connector, its credentials, or its tests.
- Merging or deleting near-duplicate stories.
- The settings storage and credential UI (see the settings spec). This spec defines the OpenRouter facts those settings use.

## Source role

ADR-0001 gives each source one job. OpenRouter's job: **models you can call through one API: newly listed, free-priced, and priced.** Hugging Face keeps its job: open-weight models that are trending. A model can legitimately appear in both. ADR-0012 records this split.

## OpenRouter connector (v1)

- New `SourceKind.OPENROUTER = "openrouter"` and `connectors/openrouter.py`.
- One unauthenticated `GET https://openrouter.ai/api/v1/models`. A provider key is optional and unused in v1.
- Keep models whose `created` timestamp falls inside the request timeframe.
- The OpenRouter fallback timeframe is **7 days** only when the request gives no timeframe. It does not widen any other selected source. An explicit timeframe applies to every selected source. The resolved request shows each source's effective window. Run again preserves those window rules and evaluates them at the new run time.
- When `topics_are_filters` is true, keep only models whose id, name, or description match a topic, using the same rule as other connectors.
- `free_only` keeps models whose input and output token prices are both explicitly zero. A `:free` suffix is stored as metadata and is not enough. Missing or invalid prices are unknown, not zero.
- Item fields: `source_id` = model id; `title` = model name; `url` = `https://openrouter.ai/<model id>`; `source_evidence` = provider (id prefix), created date, context length, input and output price per million tokens, whether both prices are explicitly zero, the free-route suffix when present, and input modalities.
- The entry badge says **Free token pricing**. It does not claim availability, rate limits, or the absence of other charges.
- Failure (HTTP error, timeout, malformed JSON) returns zero items plus a `ConnectorWarning`. It never fails the rest of the digest. The conversation treats this as a **collection failure**, not as no eligible results. A completed call with nothing inside the window is no eligible results. See the follow-up spec for the two empty states.
- Unverified facts, to be confirmed against one live call during implementation and recorded in the plan: exact field names of the `/models` payload and whether prices are strings per token. The parser is written against a captured fixture, not against this spec's wording.

### Ranking

Kind-aware score: recency first, with a small boost for listings whose token prices are explicitly zero. Section order for mixed digests stays intent-first; otherwise Juya, Hugging Face, OpenRouter, GitHub, Zhihu, and Bilibili last.

### API and frontend

- `OpenRouterDigestEntryView` joins the `DigestEntryView` union in `api/schemas/digests.py`. Regenerate `frontend/openapi.json` and the generated client.
- Frontend: kind and label mapping, a logo, and an entry metrics line (context size, price per million tokens in and out, and the Free token pricing badge when both prices are known zeroes).
- Typed-message detection: "openrouter" routes to the connector. Tool registry and follow-up context registration follow the Zhihu change as the checklist.
- `FakeOpenRouterConnector` in `sources.py` plus a fixture file, matching the existing fake pattern.

### Deferred (v2)

- **Price/context change detection:** needs a daily snapshot table and its own spec.
- **Usage rankings:** no documented API. A throwaway spike decides whether scraping is reliable; if not, drop it.

## Hiding Bilibili

Hidden means hidden from discovery, not disabled.

- New environment variable `AI_NEWS_AGENT_HIDDEN_SOURCES`, a comma-separated list, default `bilibili`. Read it at request time.
- `GET /sources` omits hidden names from the discovery catalog. The full catalog order is juya, huggingface, openrouter, github, zhihu, bilibili. The response still identifies hidden sources so Settings can label them.
- `ALLOWED_SOURCES`, the connector, `SourceKind`, credentials, tests, and source settings stay.
- A typed request such as "bilibili videos about X" still selects Bilibili. Hiding does not reject it.
- The composer drops hidden names from a loaded session's `connector_names` before display. If that leaves none, it falls back to the visible catalog defaults. The drop is local and is not saved until the user changes a preference.
- Empty-result suggestions and the history filter's source dropdown use the visible catalog.
- An empty variable shows every source in discovery.

## Related coverage

After ranking, a pure function links selected entries that confidently name the same model or product. The match preserves version, parameter size, and product variant: "M3.1 Flash" and "M3.1 Pro" are not the same identity. Uncertain overlap produces no link. Broader similarity, such as "both are reasoning models," is not this feature.

- Each member gets `related_display_ranks: list[int]` on its API view. The default is empty.
- Nothing is removed or reranked, so `dN:rN` tokens stay valid.
- The frontend shows a "Related: #1" chip that scrolls to the other entry. The chip appears wherever the entry is shown — its digest row and its deep-dive card — and is absent when the list is empty.
- Markdown rendering is unchanged.
- This is not Hugging Face model-family grouping. Family grouping still collapses packaging variants before display. Related coverage links entries that remain separate.

## Error handling

| Case | Behaviour |
|---|---|
| OpenRouter unreachable or malformed | collection failure warning; other sources unaffected |
| Zero models in the effective window | no eligible results |
| Prices missing or invalid | not free; `free_only` excludes the listing |
| Session lists only hidden sources | composer falls back to visible defaults for display; explicit requests can still name the hidden source |
| Two titles share words but not version, size, or variant | no related link |

## Testing (TDD; one failing test per behaviour)

1. The parser turns the fixture into items with the agreed evidence. Explicit zero input and output prices qualify as free token pricing. A `:free` suffix without known zero prices does not. Unknown prices do not become zero.
2. The timeframe filter keeps only in-window models. The 7-day fallback applies only to OpenRouter when the request has no timeframe. An explicit timeframe applies to every selected source.
3. The topic filter applies only when `topics_are_filters` is true. `free_only` applies the zero-price rule.
4. HTTP and JSON failure produce a warning and no items, and the digest outcome is a collection failure rather than no eligible results.
5. Ranking boosts explicitly free-priced listings and orders sections with OpenRouter after Hugging Face and before GitHub.
6. The digest view maps OpenRouter evidence, including the narrower pricing claim. OpenAPI is regenerated and the client compiles.
7. `/sources` hides names from the environment variable and still reports that they are hidden. An empty value shows all. A typed Bilibili request still routes. Settings for a hidden source stay available.
8. The composer drops hidden names from a session's displayed selection.
9. Related grouping links a confidently identical pair, leaves "M3.1 Flash" and "M3.1 Pro" unlinked, leaves uncertain overlap unlinked, and never changes rank or membership.
10. Verification: a fake-mode digest with OpenRouter selected, plus one live call whose captured fixture is the parser's contract.

## Open items

None blocking. The `/models` field names are verified in implementation against the captured fixture.
