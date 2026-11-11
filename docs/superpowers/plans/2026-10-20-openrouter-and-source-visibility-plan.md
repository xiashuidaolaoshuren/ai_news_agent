# Implementation plan: OpenRouter source, source visibility, and related coverage

**Spec:** [docs/superpowers/specs/2026-10-20-openrouter-and-source-visibility-design.md](../specs/2026-10-20-openrouter-and-source-visibility-design.md)
**ADR:** [docs/adr/0012-openrouter-source-role-and-related-coverage.md](../../adr/0012-openrouter-source-role-and-related-coverage.md)
**Created:** 2026-10-20
**Goal scope:** One coherent feature: OpenRouter as a callable-model digest source, Bilibili hidden from discovery without being disabled, and related-coverage links for entries that name the same model or product. Backend and frontend ship in this one plan. Backend tasks come first.

## Summary

OpenRouter joins the digest as its own source kind. v1 is one unauthenticated `GET https://openrouter.ai/api/v1/models`, filtered by the request window, optional topic filter, and optional free-token-pricing filter. A provider key is unused. Free token pricing means both prices are known zeroes; a `:free` suffix is metadata only. Failure is a collection warning, not an empty digest. Mixed-section order becomes Juya, Hugging Face, OpenRouter, GitHub, Zhihu, Bilibili last.

Hiding is an environment list, default `bilibili`, read at request time. `GET /sources` omits hidden names from the discovery catalog and still reports them as hidden. Typed requests, settings, credentials, and `ALLOWED_SOURCES` stay. The composer drops hidden names from a loaded session's displayed selection and does not save that drop.

After ranking, a pure function links entries that confidently name the same model or product. Version, parameter size, and product variant must match. Nothing is removed or reranked. Every entry view carries `related_display_ranks`. The chip appears on the digest row and on the deep-dive card.

Out of scope: usage rankings, price-change history, removing the Bilibili connector, merging near-duplicate stories, and the settings storage or credential UI (already shipped; OpenRouter's profile facts already exist as `OpenRouterProfile`).

## Discovery notes

- Reuse: `SourceKind`, `ALLOWED_SOURCES`, `build_connectors` / `Fake*Connector` in `sources.py`. A new kind follows Hugging Face and Zhihu: enum value, connector module, fake, factory branch, fixture under `tests/fixtures/`.
- Reuse: `ConnectorRequest.topics_are_filters` and `strict_timeframe`. Topic matching follows the Juya rule (`_matches_topics` / `_text_matches_topic`: a topic hits when it appears in id, name, or description). Do not copy the Hugging Face substring matcher, which also searches tags.
- Reuse: `OpenRouterProfile.free_only` and `item_count` in `source_settings.py`. Settings already persist them and mark Bilibili `hidden` from a hardcoded `HIDDEN_SOURCES`. This plan does not change the profile schema. It wires `free_only` onto the collect request and replaces the hardcoded hide set with the environment variable for discovery.
- Reuse: `collection_outcome`. A connector warning whose code is in `SOURCE_FAILURE_CODES` makes a zero-entry digest `failed` rather than `no_eligible`. OpenRouter's HTTP, timeout, and malformed-JSON warning must use a code already in that set (`request_failed`) or the set must grow in the same task. A completed call with nothing in the window emits no failure warning.
- Reuse: `_timeframe_bounds_at` and `within_timeframe` in `ranking.py`. `last_7_days` is already a window. The 7-day fallback is applied to the OpenRouter request only, before collect, and only when `DigestRequest.timeframe` is unset. Other sources keep a null timeframe.
- Reuse: `_FALLBACK_KIND_ORDER` and `order_selected_for_digest`. Insert OpenRouter after Hugging Face and before GitHub. Kind-aware score is a branch in `_score_item`, same shape as Zhihu and Hugging Face.
- Reuse: `DigestEntryView` union and `build_digest_view_payload`. Hugging Face already has `related_display_ranks`, filled by `family_key`. That is family grouping, not this feature. Related coverage is a new pure function over selected entries and does not call `family_key`. The field moves to the common entry view so every kind can carry it. HF family grouping in `ranking.py` stays.
- Reuse: `request_metadata` / `ResolvedRequestOut`. The resolved request gains each source's effective window. Run again stores the full `DigestRequest` via `request_payload` and re-evaluates the fallback at the new run time, because the stored timeframe stays null when the user did not set one.
- Reuse: typed-source routing in `services/conversation.py` (`_SOURCE_WORDS`). Add an `openrouter` pattern the way `zhihu` was added. Tool registry follows `search_zhihu_practitioner_insights`: schema, pure search in `tools/connectors.py`, factory in `tools/registry.py`.
- Reuse: frontend `EntryKind`, `SOURCE_LABELS`, `SourceLogo`, `toEntryVm`, and the existing Related chip in `EntryRow.vue` (today HF-only). `SHOW_BILIBILI` and `HIDDEN_SOURCES` are the current hide switches; discovery becomes the API catalog plus `hidden`.
- Constraints: parser is written against a captured fixture, not against the spec's field wording. Exact `/models` field names and whether prices are strings per token are unverified until one live call. No schema migration: evidence lives on `NewsItem.source_evidence`, and `related_display_ranks` is computed at view time.
- Constraints: markdown rendering of digests is unchanged. The badge text is **Free token pricing** and does not claim availability, rate limits, or the absence of other charges.
- Anti-goals: no usage-ranking scrape, no price-snapshot table, no Bilibili connector or credential deletion, no near-duplicate merge, no drive-by edits to Hugging Face family grouping, no change to settings storage.

## File map

### Goal: OpenRouter connector and digest

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|------|---------------|----------------|----------------|----------------------|
| `src/ai_news_agent/models.py` | modify | Source kind | `SourceKind.OPENROUTER = "openrouter"` | verified |
| `src/ai_news_agent/connectors/openrouter.py` | create | Fetch, parse, filter `/models` | `OpenRouterConnector.collect`; module helpers for price and window | provisional |
| `src/ai_news_agent/connectors/base.py` | modify | Carry the profile flag into collect | `ConnectorRequest.free_only: bool = False` | verified |
| `src/ai_news_agent/request.py` | modify | Carry the profile flag on the digest request | `DigestRequest.free_only: bool = False` | verified |
| `src/ai_news_agent/sources.py` | modify | Allow the name; fake and live factories | `ALLOWED_SOURCES`; `FakeOpenRouterConnector`; `_connector_for_name` | verified |
| `src/ai_news_agent/source_settings.py` | modify | Apply `free_only` when OpenRouter is selected and the request did not set it | `SourceSettingsService.apply` | verified |
| `src/ai_news_agent/graph/nodes/parse.py` | modify | Map the flag onto the connector request | `parse_request_node` | verified |
| `src/ai_news_agent/services/conversation.py` | modify | Route the word "openrouter"; apply the 7-day fallback; report effective windows | `_SOURCE_WORDS`; digest decision; `request_metadata` | verified |
| `src/ai_news_agent/api/schemas/sessions.py` | modify | Public window per source | `ResolvedRequestOut.windows: dict[str, str]` | verified path; field name provisional |
| `src/ai_news_agent/ranking.py` | modify | Recency-first score plus a free-price boost; section order | `_score_item`, `_source_base`, `_FALLBACK_KIND_ORDER` | verified |
| `src/ai_news_agent/rendering.py` | modify | Section label for markdown | source label map | verified |
| `src/ai_news_agent/collection_outcomes.py` | modify | OpenRouter abort counts as collection failure | `SOURCE_FAILURE_CODES` only if the new warning code is not already listed | verified |
| `src/ai_news_agent/services/digest_views.py` | modify | Map OpenRouter evidence, including the narrower pricing claim | `extract_openrouter_evidence` | verified |
| `src/ai_news_agent/api/schemas/digests.py` | modify | Entry DTO | `OpenRouterDigestEntryView` on `DigestEntryViewUnion` | verified |
| `src/ai_news_agent/tools/schemas.py` | modify | LLM search args | `OpenRouterSearchArgs` | provisional |
| `src/ai_news_agent/tools/connectors.py` | modify | Tool search | `search_openrouter_models` | verified |
| `src/ai_news_agent/tools/registry.py` | modify | Register the tool from a factory | `build_tools(..., openrouter_factory=)` | verified |
| `src/ai_news_agent/tools/__init__.py` | modify | Export the tool name | public re-export | verified |
| `src/ai_news_agent/services/composition.py` | modify | Pass the OpenRouter factory into the tool registry | `build_application` | verified |
| `tests/fixtures/openrouter_models_sample.json` | create | Parser contract, captured from one live call | fixture JSON | provisional |
| `tests/test_connectors_openrouter.py` | create | Parser, window, topic, free-only, failure | pytest | provisional |
| `tests/test_ranking.py` | modify | Boost and section order | pytest | verified |
| `tests/test_digest_views.py` | modify | Evidence mapping | pytest | verified |
| `tests/test_conversation.py` | modify | Routing, fallback, windows | pytest | verified |
| `tests/test_tools_connectors.py` | modify | Tool search | pytest | verified |

### Goal: Source visibility

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|------|---------------|----------------|----------------|----------------------|
| `src/ai_news_agent/env.py` | modify | Read the hide list at call time | `hidden_source_names() -> frozenset[str]` from `AI_NEWS_AGENT_HIDDEN_SOURCES` | verified |
| `src/ai_news_agent/api/routers/meta.py` | modify | Discovery catalog omits hidden names and reports them | `GET /sources` adds `hidden: list[str]`; `sources` is the visible catalog, order juya, huggingface, openrouter, github, zhihu, bilibili | verified |
| `src/ai_news_agent/source_settings.py` | modify | Settings `hidden` follows the same env read, not the hardcoded set | `HIDDEN_SOURCES` becomes a function or is read at profile-dump time | verified |
| `tests/test_api_meta.py` | modify | Hide, empty value, still-hidden report | pytest | verified path |
| `frontend/src/vm/composer.ts` | modify | Drop hidden names from displayed selection; fall back to visible defaults; do not write the drop | `prefsFor(session, sources, hidden)` | verified |
| `frontend/src/stores/composer.ts` | modify | Pass the catalog's hidden list into `prefsFor` | `load` / `syncPrefs` | verified |
| `frontend/src/vm/history.ts` | modify | History source dropdown uses the visible catalog, not `SHOW_BILIBILI` | `historySourceOptions(catalog)` | verified |
| `frontend/src/components/thread/EmptyConversation.vue` | modify | Orbit uses the visible catalog | orbit list | verified |
| `frontend/src/lib/features.ts` | modify | Stop being the discovery switch | `SHOW_BILIBILI` removed once every caller reads the catalog | verified |
| `frontend/src/vm/composer.test.ts`, `stores/composer.test.ts`, `vm/history.test.ts`, `components/thread/empty-conversation.test.ts` | modify | Hide-list acceptance | vitest | verified |

### Goal: Related coverage

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|------|---------------|----------------|----------------|----------------------|
| `src/ai_news_agent/related_coverage.py` | create | Link confidently identical model or product identities | `related_display_ranks(entries) -> dict[int, list[int]]` | provisional |
| `src/ai_news_agent/services/digest_views.py` | modify | Attach the new links on every entry; stop using HF family keys for this field | `build_digest_view_payload` | verified |
| `src/ai_news_agent/api/schemas/digests.py` | modify | Field on the common view, default empty | `DigestEntryView.related_display_ranks` | verified |
| `tests/test_related_coverage.py` | create | Identical pair, Flash vs Pro, uncertain overlap, stable rank | pytest | provisional |
| `frontend/src/vm/entries.ts` | modify | Map the field for every kind, not only Hugging Face | `toVm` | verified |
| `frontend/src/components/thread/EntryRow.vue` | modify | Chip already renders `relatedRanks`; keep it for every kind | existing chip | verified |
| `frontend/src/components/thread/Thread.vue` | modify | Same chip on the deep-dive follow-up card | follow-up markdown block gains a chip row when the targeted entry has ranks | verified path; card mount provisional |
| `frontend/src/vm/entries.test.ts`, `frontend/src/components/thread/thread.test.ts` | modify | Chip presence and absence | vitest | verified |

### Goal: Frontend OpenRouter presentation

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|------|---------------|----------------|----------------|----------------------|
| `frontend/openapi.json` | modify | Regenerated spec | generated | verified |
| `frontend/src/api/generated/*` | modify | Regenerated client | generated | verified |
| `frontend/src/vm/types.ts` | modify | Kind union | `EntryKind` includes `'openrouter'` | verified |
| `frontend/src/vm/digest.ts` | modify | Label and section subtitle | `SOURCE_LABELS`, `SECTION_SUBTITLES` | verified |
| `frontend/src/vm/entries.ts` | modify | Metrics line and badge | `openRouterMeta`; `EntryVm` badge field | verified |
| `frontend/src/components/thread/SourceLogo.vue` | modify | Logo lookup | `LOGOS.openrouter` | verified |
| `frontend/src/assets/sources/openrouter.svg` | create | Logo asset | static file | provisional |
| `frontend/src/components/thread/EntryRow.vue` | modify | Render the metrics line and the Free token pricing badge | existing meta line | verified |
| `frontend/src/vm/digest.test.ts`, `entries.test.ts` | modify | Kind, metrics, badge | vitest | verified |

### Blast radius

| Path | Why sensitive | Behavior that must stay intact |
|------|----------------|-------------------------------|
| `models.py` `SourceKind` | Every connector, view, and generated client | Existing kinds and their string values stay `github`, `bilibili`, `juya`, `huggingface`, `zhihu` |
| `sources.py` `ALLOWED_SOURCES` and `normalize_source_names` | CLI, chat, and settings all reject unknown names | Unknown names still raise; empty selection still raises; fake mode stays explicit |
| `ranking.py` `_FALLBACK_KIND_ORDER` and `_score_item` | Digest section order and scores | Existing kind order stays Juya, Hugging Face, GitHub, Zhihu, Bilibili, with OpenRouter inserted; HF family collapse still runs before display; Bilibili newest-in-window still leads its own section |
| `api/schemas/digests.py` union | Generated client and every entry renderer | GitHub, Hugging Face, Juya, Zhihu, and Bilibili payloads still validate; HF `family_variants` stays |
| `services/digest_views.py` related ranks | HF follow-up cards already print family siblings | Family grouping still collapses packaging variants; the new linker does not call `family_key` and does not change who is selected |
| `api/routers/meta.py` `GET /sources` | Composer, history, and empty-state catalogs | Defaults stay `juya`; health payloads stay; a hidden source is omitted from `sources` and listed in `hidden` |
| `source_settings.py` `HIDDEN_SOURCES` | Settings already labels Bilibili hidden | Profile fields do not change; an empty env value shows every source, including in Settings |
| `services/conversation.py` source routing | Typed requests select connectors | Existing juya, github, huggingface, zhihu, and bilibili patterns still match; a typed Bilibili request still selects Bilibili while it is hidden |
| `collection_outcomes.py` | Empty-state copy | A completed empty collect stays `no_eligible`; only an abort warning becomes `failed` |

## Workflow (for implementers)

1. **writing-plans** produced this file (type-1 decomposition).
2. Per subtask: **Plan mode** + **planning-subtasks** → type-2 plan in the session plan file, approved with **ExitPlanMode**, when **Plan mode** is `high` (or `medium` with a real remaining unknown).
3. **Implementation** (after plan approval): **test-driven-development** when **`TDD suitable: yes`** (or the TDD slice of **`partial`**); follow **Verification** when **`no`**.
4. Order: **B1** → **B2** → **B3**. **B4** is blocked by **B1** only. **B5** is blocked by **B2** and **B3**. **F1** is blocked by **B3** and **B5** (it regenerates the client those tasks change). **F2** is blocked by **F1** and **B4**. **F3** is blocked by **F1** and **B5**. Frontend tasks do not start before the backend contract they render exists.
5. Equivalent internal changes: record and continue. A subtask split or merge updates the subtasks (ids, **Consumes**/**Produces**, partitioned **Acceptance**, rewired **Blocked by**) and logs a row. Material changes: pause and confirm, then log a **Plan changelog** row.

## Subtasks

Dependency notation: `Blocked by: B1` means start after B1 is done.

### B1 — OpenRouter parser, filters, and fixture

- [x] **Do:** Turn one captured `/models` payload into news items, and keep only the rows the request allows.
- **Consumes:** `NewsItem`, `ConnectorRequest`, `ConnectorResult`, `ConnectorWarning`, `SourceKind`. Juya topic match rule (`_text_matches_topic`): a topic matches when it appears in the model's id, name, or description. `within_timeframe` / `_timeframe_bounds_at` for the window.
- **Produces:** `SourceKind.OPENROUTER`. `OpenRouterConnector.collect(request) -> ConnectorResult`. `ConnectorRequest.free_only: bool = False`. Evidence keys on each item: `provider` (id prefix), `created` (date), `context_length`, `prompt_price_per_million`, `completion_price_per_million`, `free_token_pricing` (true only when both prices are known zeroes), `free_route_suffix` (present or absent), `input_modalities`. `source_id` is the model id, `title` is the model name, `url` is `https://openrouter.ai/<model id>`. Warning code `request_failed` with connector `openrouter` on HTTP error, timeout, or malformed JSON, and zero items. `tests/fixtures/openrouter_models_sample.json` is the parser contract.
- **Acceptance:**
  - The parser maps the fixture onto those evidence keys. Both prices explicitly zero sets `free_token_pricing` true. A `:free` suffix with missing or non-zero prices does not. Missing or unparseable prices stay unknown and do not become zero.
  - Only models whose `created` falls inside the request timeframe are kept. The connector applies timeframe `last_7_days` when the request timeframe is unset. An explicit timeframe is used as given and is not widened.
  - When `topics_are_filters` is false, topics do not drop models. When true, a model is kept only if its id, name, or description matches a topic.
  - `free_only` true keeps only rows with `free_token_pricing` true.
  - HTTP error, timeout, and malformed JSON each return no items and one `request_failed` warning. A completed payload with nothing in the window returns no items and no failure warning.
- **Compatibility:** No other connector's collect signature changes. `free_only` defaults false, so existing `ConnectorRequest(...)` call sites keep current behavior.
- **Blocked by:** —
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_connectors_openrouter.py -q`. The fixture file is the recorded live response; the test does not call the network.

### B2 — OpenRouter on the digest path

- [x] **Do:** Select, rank, and section OpenRouter like the other sources, with the 7-day fallback limited to it and the free-price boost applied.
- **Consumes:** B1 `SourceKind.OPENROUTER`, `OpenRouterConnector`, `ConnectorRequest.free_only`. `OpenRouterProfile.free_only`. `SourceSettingsService.apply`. `parse_request_node`. `_score_item`, `_FALLBACK_KIND_ORDER`, `order_selected_for_digest`. `request_metadata`, `ResolvedRequestOut`. `collection_outcome`.
- **Produces:** `"openrouter"` in `ALLOWED_SOURCES`. `FakeOpenRouterConnector` returns at least one in-window item with known-zero prices and one priced item, so fake-mode digests are non-empty. `SourceSettingsService.apply` sets `DigestRequest.free_only` from the OpenRouter profile when OpenRouter is selected and the request left it false. `parse_request_node` copies `free_only` onto the connector request. Typed text matching `openrouter` (case-insensitive) selects the connector, including while the source is hidden. When `DigestRequest.timeframe` is unset and OpenRouter is selected, the connector request for OpenRouter uses `last_7_days` and every other selected source keeps a null timeframe. `request_metadata` includes `windows: dict[str, str]` mapping each selected source to its effective timeframe (`last_7_days` or the explicit value, or empty when that source has none). `_score_item` for OpenRouter is freshness first, plus a small positive term when `free_token_pricing` is true, and no engagement term. `_FALLBACK_KIND_ORDER` is Juya, Hugging Face, OpenRouter, GitHub, Zhihu, Bilibili. Markdown section label is `OpenRouter`.
- **Acceptance:**
  - A fake-mode digest with OpenRouter selected completes and includes the fake items.
  - An explicitly free-priced OpenRouter row scores above an otherwise identical priced row.
  - A mixed digest with no primary source orders sections Juya, Hugging Face, OpenRouter, GitHub, Zhihu, Bilibili, omitting empty kinds. A primary source still leads.
  - No timeframe, OpenRouter plus GitHub selected: OpenRouter is filtered to 7 days; GitHub is not given a timeframe.
  - Explicit timeframe: every selected source uses it. Run again of a request whose stored timeframe is null applies the fallback again at the new run time rather than replaying a baked window.
  - The resolved request payload shows each source's effective window.
  - An OpenRouter `request_failed` warning and zero entries classifies as `failed`. Zero entries and no failure warning classifies as `no_eligible`.
- **Compatibility:** Existing section-order test for Juya, Hugging Face, GitHub, Zhihu, Bilibili gains OpenRouter in the new slot and otherwise stays. HF family collapse is unchanged. Typed Bilibili, Zhihu, GitHub, Hugging Face, and Juya requests still route.
- **Blocked by:** B1
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_ranking.py tests/test_conversation.py tests/test_sources.py tests/test_source_settings.py tests/test_collection_outcomes.py -q --tb=line`, plus the existing fake-mode digest test module if one covers `build_connectors(fake=True)`. Add the OpenRouter fake assertion there rather than a new harness.

### B3 — OpenRouter digest view and tool

- [x] **Do:** Expose OpenRouter entries on the digest view and register the search tool the way Zhihu is registered.
- **Consumes:** B1 evidence keys. B2 `SourceKind.OPENROUTER` and the factory. `DigestEntryView` union, `build_digest_view_payload`, `search_zhihu_practitioner_insights`, `build_tools`.
- **Produces:** `OpenRouterDigestEntryView` with `source_kind: Literal[SourceKind.OPENROUTER]`, `context_length: int | None`, `prompt_price_per_million: str | None`, `completion_price_per_million: str | None`, `free_token_pricing: bool`, `input_modalities: list[str]`, `provider: str | None`. `free_token_pricing` is true only when both prices are known zeroes. `search_openrouter_models(*, connector, args) -> ToolObservation`. `OpenRouterSearchArgs` with `max_results`, `free_only: bool = False`, and `topics: list[str]`. `build_tools(..., openrouter_factory=)` appends the tool when the factory is set. `build_application` passes that factory.
- **Acceptance:**
  - A saved OpenRouter entry round-trips through `build_digest_view` with those fields. Unknown prices stay null and `free_token_pricing` is false. The view does not add a field that claims availability, rate limits, or other charges.
  - The union still validates a GitHub, Hugging Face, Juya, Zhihu, and Bilibili entry.
  - The tool calls `collect` and returns the observation shape Zhihu uses (`connector`, `item_count`, `items`, `warnings`). A connector warning becomes a caveat and does not raise.
- **Compatibility:** `DigestEntryView.source_kind` stays the Bilibili | Zhihu literal until B5 moves the shared field. OpenRouter is its own variant, discriminated by `source_kind`.
- **Blocked by:** B2
- **Plan mode:** medium — the named unknown is which existing tool-registry branch (`register_structured_tools` versus the per-factory closures) the Zhihu checklist actually uses for a new connector. Read `tools/registry.py` and copy that branch; do not invent a second registration path.
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_digest_views.py tests/test_tools_connectors.py tests/test_tools_registry.py -q --tb=line -k "openrouter or digest_view or zhihu"`.

### B4 — Hidden sources

- [x] **Do:** Hide sources named by the environment from discovery, without disabling them.
- **Consumes:** `GET /sources` in `api/routers/meta.py`. `HIDDEN_SOURCES` and `_profile_to_dict` in `source_settings.py`. `normalize_source_names` (still allows every `ALLOWED_SOURCES` name, including after B2 adds OpenRouter).
- **Produces:** `hidden_source_names() -> frozenset[str]`, read from `AI_NEWS_AGENT_HIDDEN_SOURCES` on each call. Unset or missing variable defaults to `{"bilibili"}`. An empty value (the variable is set and blank) returns an empty set. Names are stripped and lowercased; unknown tokens are ignored. `GET /sources` returns `sources` in catalog order minus hidden names, and `hidden: list[str]` of the hidden names in that same order. Settings profile payloads use the same function for `hidden`. `ALLOWED_SOURCES` is not filtered.
- **Acceptance:**
  - Default (variable unset): `sources` omits `bilibili` and `hidden` is `["bilibili"]`. After B2, `openrouter` is in `sources`.
  - Variable set to empty: every catalog name is in `sources` and `hidden` is `[]`.
  - Variable set to `bilibili,zhihu`: both are omitted from `sources` and listed in `hidden`.
  - A typed "bilibili videos about X" request still resolves `connector_names` containing `bilibili`.
  - `GET /api/v1/settings/sources` still returns a Bilibili profile, with `hidden` true under the default.
  - Changing the variable between two requests changes the next response without a restart.
- **Compatibility:** Health payloads and `defaults: ["juya"]` stay. Settings profile field shapes stay. Credentials for a hidden source stay readable.
- **Blocked by:** B1
- **Plan mode:** medium — the named unknown is whether Settings and `GET /sources` should call one helper or keep two lists. They must call `hidden_source_names()` so the two cannot drift.
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_api_meta.py tests/test_source_settings.py tests/test_conversation.py -q --tb=line -k "hidden or sources or bilibili"`.

### B5 — Related coverage

- [x] **Do:** Link selected entries that confidently name the same model or product, without changing rank or membership.
- **Consumes:** B3 digest view union. Selected `DigestEntry` rows plus their `NewsItem` titles and source ids. `family_key` is not an input.
- **Produces:** `related_display_ranks(entries) -> dict[int, list[int]]` in `related_coverage.py`. Keys and values are 1-based display ranks. Each list is the other members of a confident identity group, sorted, and is empty when the entry has no link. `build_digest_view_payload` writes that map onto every entry. `DigestEntryView.related_display_ranks: list[int]` defaults to empty, so GitHub, Juya, Zhihu, Bilibili, Hugging Face, and OpenRouter views all carry it. The Hugging Face family-key filler for this field is removed.
- **Acceptance:**
  - Two entries whose identity tokens match, including the same version, parameter size, and product variant, list each other's display ranks. A third unrelated entry lists none.
  - "M3.1 Flash" and "M3.1 Pro" produce no link. The same title with different parameter size ("M3.1 7B" and "M3.1 70B") produces no link. Different version ("M3" and "M3.1") produces no link.
  - Shared words that are not an identity ("both are reasoning models", overlapping topic words, one side missing a version or size the other has) produce no link.
  - Display order and the set of entries are unchanged. `dN:rN` tokens stay valid because rank and membership do not move.
  - A Hugging Face packaging pair that `family_key` would group is not given a related link by this function unless the identity rule matches. Family collapse in ranking still runs.
- **Compatibility:** Markdown rendering does not grow a related section. HF `family_variants` stays. Follow-up cards that today print HF family sibling ranks need a new source for that sentence: they read `related_display_ranks` from the view, which may now be empty for a packaging pair. That is the spec's split, not a regression to paper over inside `family_key`.
- **Blocked by:** B3
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_related_coverage.py tests/test_digest_views.py tests/test_huggingface_followup.py -q --tb=line`.

### F1 — OpenRouter entry presentation

- [ ] **Do:** Show OpenRouter entries with a logo, a metrics line, and the Free token pricing badge.
- **Consumes:** B3 `OpenRouterDigestEntryView` and B5 `related_display_ranks` on the common view (regenerate the client once, after both).
- **Produces:** Regenerated `frontend/openapi.json` and `frontend/src/api/generated/*`. `EntryKind` includes `'openrouter'`. `sourceLabel('openrouter')` is `OpenRouter`. Section subtitle is `Models you can call`. `SourceLogo` resolves `frontend/src/assets/sources/openrouter.svg`. `toEntryVm` sets `meta` to the metrics line: context length, input price per million, output price per million, omitting any segment whose value is null. `EntryVm.badge` is `Free token pricing` when `free_token_pricing` is true and absent otherwise. `EntryRow` renders `badge` beside the meta line.
- **Acceptance:**
  - An OpenRouter fixture entry renders the metrics line and, only when both prices are known zeroes, the badge text `Free token pricing`.
  - A `:free` suffix is not shown as the badge and does not invent prices.
  - Missing prices omit those segments and show no badge.
  - GitHub, Hugging Face, Juya, Zhihu, and Bilibili entries still render, and none of them gains the badge.
  - `npm run typecheck` (or the repo's `vue-tsc` script) passes after regeneration.
- **Compatibility:** Generated files change only by the new schema. Do not hand-edit `frontend/src/api/generated/*`.
- **Blocked by:** B3, B5
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** Metrics line, badge condition, label, and kind mapping are testable in `vm/entries.test.ts` and `vm/digest.test.ts` and go first. The logo asset and its CSS are visual; check them by rendering the entry row, not by a new pixel test.
- **Verification:** `cd frontend && npm run gen:api:spec && npm run gen:api && npm test -- src/vm/entries.test.ts src/vm/digest.test.ts && npm run typecheck`.

### F2 — Composer, history, and empty state follow the hidden list

- [ ] **Do:** Stop using `SHOW_BILIBILI` as the discovery switch. Displayed source lists come from the visible catalog.
- **Consumes:** B4 `GET /sources` shape: `sources` is the visible catalog, `hidden` names the rest. `prefsFor`, `historySourceOptions`, `EmptyConversation` orbit, `NoEligibleResults` (already filters the catalog it is given).
- **Produces:** `prefsFor(session, sources, hidden)` drops any session `connector_names` that are in `hidden`. If none remain, the selected list is the visible catalog's defaults. The function does not return a write. `load` in the composer store passes `hidden` and does not PATCH. `historySourceOptions` lists the visible catalog only. The empty-state orbit lists the visible catalog only. `SHOW_BILIBILI` is deleted, and settings or keys tests that flipped it assert against the profile `hidden` flag instead.
- **Acceptance:**
  - A session stored as `["bilibili"]` with `hidden` `["bilibili"]` displays the visible defaults, and no preference PATCH is sent by the load.
  - A session stored as `["juya", "bilibili"]` displays `["juya"]` only.
  - The history dropdown and the empty-state orbit omit `bilibili` under that hidden list and include it when `hidden` is empty.
  - Empty-result suggestions receive the visible catalog, so a hidden source is not offered.
  - Settings still renders a profile with `hidden: true`, including its credential group.
- **Compatibility:** The drop is display-only. The stored `connector_names` stay until the user changes a preference. Typed Bilibili send behavior is backend (B4) and is not reimplemented here.
- **Blocked by:** F1, B4
- **Plan mode:** medium — the named unknown is which components still import `SHOW_BILIBILI` after the composer and history move. Grep it and switch each caller in this task; do not leave a second switch.
- **TDD suitable:** yes
- **Verification:** `cd frontend && npm test -- src/vm/composer.test.ts src/stores/composer.test.ts src/vm/history.test.ts src/components/thread/empty-conversation.test.ts src/components/settings/source-settings.test.ts`.

### F3 — Related chip on the digest row and the deep-dive card

- [ ] **Do:** Show the Related chip wherever the entry is shown, and hide it when the list is empty.
- **Consumes:** B5 `related_display_ranks` on every entry view. F1 generated client. Existing `EntryRow` chip and `goto-related` emit.
- **Produces:** `toVm` copies `related_display_ranks` onto `relatedRanks` for every kind, not only Hugging Face. The deep-dive follow-up card (the `Thread.vue` follow-up markdown block for the targeted entry) renders the same chip row when that entry's `relatedRanks` is non-empty, and emits `goto-related` with the same `RefVm` shape `EntryRow` uses. No chip when the list is empty or missing.
- **Acceptance:**
  - A digest row of any kind with `related_display_ranks: [2]` shows a button `Related: #2` that emits the rank-2 ref. An entry with `[]` or an omitted field shows no chip.
  - The deep-dive card for that same entry shows the same chip and emits the same event. A deep-dive card whose entry has no ranks shows none.
  - Clicking the chip still only asks the thread to scroll; it does not send a message.
  - Hugging Face family variants stay in the comparison table and are not turned into Related chips.
- **Compatibility:** Markdown body of the follow-up is unchanged. Rank display and entry order are unchanged.
- **Blocked by:** F1, B5
- **Plan mode:** medium — the named unknown is where the deep-dive card gets its entry view model. The follow-up reply is markdown today, so the chip has to mount from the targeted entry, not from the markdown. Find that entry in the thread store before adding a parser.
- **TDD suitable:** partial
- **TDD suitable reason:** Chip presence, absence, and the emitted ref are component tests and go first. Scroll position after the emit is the existing thread behavior; confirm it manually, do not add a scroll-position test.
- **Verification:** `cd frontend && npm test -- src/vm/entries.test.ts src/components/thread/thread.test.ts src/components/thread/digest.test.ts`.

## TDD note (implementation)

Per subtask, obey **`TDD suitable`**. **`yes`** means strict **test-driven-development** (red/green/refactor). **`partial`** applies it only to the testable slice named in that subtask; the rest is **Verification**. **`no`** is not used in this plan. A behavior-preserving refactor with a covering suite is stay-green, not a new RED/GREEN pair. Type-2 planning uses **planning-subtasks**.

B1 starts from the fixture. If the first live call shows different field names or per-token string prices, update the fixture and the parser tests, then log an equivalent changelog row. Do not treat the spec's field wording as the contract.

## Plan changelog

| Date | Change | Kind |
|------|--------|------|
| 2026-10-20 | Initial plan. Backend B1–B5, frontend F1–F3, one plan. | — |
| 2026-11-11 | Review-driven corrections to B3/B4/B5: `SOURCE_CATALOG_ORDER` reordered to the spec catalog order (juya, huggingface, openrouter, github, zhihu, bilibili); related-coverage signatures now include the product name (with version/size/variant), so different products with equal attributes no longer link; the OpenRouter search tool sets `topics_are_filters`, and the connector honors `max_items` (newest kept). | equivalent internal fix |
