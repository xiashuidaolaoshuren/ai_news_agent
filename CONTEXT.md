# AI News Research Agent

Local-first on-demand digest of AI learning signals from distinct source kinds. Language here is product/domain vocabulary only.

## Language

### Sources

**Juya**:
A first-class curated daily AI bulletin source identified by the website (`daily.juya.uk`), separate from GitHub and from generic RSS. It is the default digest source when the user does not name platforms. The old GitHub repo URL is not a Juya target; using it should fail with guidance to the website.
_Avoid_: GitHub special case, `github_manual_urls` alias as the conceptual or operational home, generic RSS, treating `github.com/jujuyaya/juya-ai-daily` as Juya, silently turning that URL into a repo news item

**Bilibili**:
A source whose digest items are video learning signals from Bilibili. Opt-in unless the user asks for it or names it in sources. It is hidden from discovery by default, which does not disable explicit requests or past results.
_Avoid_: Transcript-first news (until that milestone exists), a removed source, hiding historical Bilibili entries

**GitHub (ecosystem signal)**:
A source whose digest items are open-source momentum signals (trending repos), not article-like news or curated bulletins. Opt-in unless the user asks for ecosystem/repo signals or names it in sources.
_Avoid_: Primary news feed, Juya host, generic RSS, default always-on platform feed

**Hugging Face (model momentum signal)**:
A source for currently notable model repositories, using Hub-native momentum evidence such as trending score, recent downloads, likes, and activity rather than treating models as article-like news. **Search and digest** both present Hugging Face as a **comparison table** of model families for quick Hub stat scanning; other search tools keep the numbered Source/Link list.
_Avoid_: Primary news feed, calling popularity model quality, claiming precise adoption velocity from cumulative counters, article-like HF entry blocks, LLM paraphrase of Hub stats in the HF table

**Hugging Face comparison table**:
The Hugging Face presentation for **search and digest** — one GFM table row per **model family** with Rank, Model, Link, Trending, Downloads (30d), Likes, Pipeline, and Also columns (emoji-prefixed labels in the default renderer). Hub stats come from collected `NewsItem` evidence; digest HF skips per-item LLM summarize. Mixed digests keep entry blocks for other sources; only the Hugging Face section is a table. **Display rank** in the Rank column is the global digest index in mixed digests; search ranks are 1-based family order.
_Avoid_: `###` summary blocks for Hugging Face, treating each table row as a raw Hub repo rather than a family, restarting rank at 1 inside the Hugging Face section in mixed digests

**Digest presentation chrome**:
Optional emoji prefixes on the default digest title, metadata lines, mixed-section labels, entry field labels, and HF table column headers — presentation only, not domain entities. Applies to default `render_digest_*` and HF search table output; the Chinese editorial Juya bulletin style is unchanged.
_Avoid_: Emoji in editorial digest output, emoji on non-HF search lists, treating emoji labels as follow-up vocabulary

**Zhihu (practitioner insight signal)**:
A source for Chinese-language practitioner lessons, trade-offs, and pitfalls about AI topics, distinct from primary academic evidence.
_Avoid_: arXiv substitute with equivalent evidence, generic web search, claiming relevance-ranked results are trending

**OpenRouter (callable-model signal)**:
A source for models you can call through one API: newly listed, free-priced, and priced. It is distinct from Hugging Face model momentum. The same model may legitimately appear in both.
_Avoid_: Usage rankings, price-change history, a quality ranking, a Hugging Face substitute

**Callable model**:
The atomic OpenRouter digest item — one model listing with its provider, context length, token prices, and input modalities.
_Avoid_: A Hugging Face model family, a usage ranking, inferring availability or limits from token prices

**Free token pricing**:
An OpenRouter listing whose input and output token prices are both explicitly zero. A free-route name is supporting metadata, not proof of zero prices. Missing or invalid prices are unknown.
_Avoid_: Treating an unknown price as zero, a claim about availability, limits, or other charges

**Hidden source**:
A source omitted from discovery, empty-result suggestions, and source-selection lists. Explicit requests, its settings, its credentials, and its historical results remain available.
_Avoid_: Disabled source, removed connector, hiding past entries

**Related coverage**:
Different digest entries that confidently name the same model or product, including its version, size, and product variant. The link does not merge, delete, or rerank those entries.
_Avoid_: Topical similarity, grouping different sizes or variants, treating uncertain name overlap as the same identity

**Practitioner insight**:
The atomic Zhihu digest item — one traceable search result framed for its practical experience, trade-off, or pitfall value.
_Avoid_: Uncited multi-result synthesis, treating a relevance score as popularity, inferring claims not supported by the returned content

**Trending repo**:
The atomic GitHub digest item — a repository under a topic that scores as notable momentum via a transparent heuristic (e.g. stars combined with recent activity).
_Avoid_: Release-as-primary-item, README snippet as the story, treating every matching repo as equally newsworthy, claiming a star delta the source did not report

**Stars today**:
The star gain GitHub prints for a repository on its daily trending list. A GitHub digest row shows it only when that list includes the repository.
_Avoid_: A delta computed from total stars, a change since the last digest labeled as today, showing it on every GitHub row

**Trending model**:
The atomic Hugging Face digest item — one **model family** with notable current Hub momentum, represented by the family’s highest-trending Hub repository. It may be global or constrained to a user-named topic or task.
_Avoid_: Dataset or Space, “best model,” benchmark winner, equating popularity with technical quality, treating every packaging variant (GGUF, MLX, quant, Instruct) as its own slot when it shares version, size, and product SKU

**Model family**:
The Hugging Face presentation unit: Hub repositories that share architecture version, parameter size, and product SKU (e.g. `27B` vs other sizes; `pro` vs `flash`), regardless of publisher or packaging format.
_Avoid_: Grouping different sizes or product SKUs together, splitting the same size/version across multiple visible rows because of GGUF/MLX/quant/Instruct/Chat/Uncensored suffixes

**Family representative**:
The Hub repository shown for a model family — the member with the highest Hub trending score. Other format or packaging variants may appear on an **Also:** line but do not occupy their own slot.
_Avoid_: Picking a representative by downloads alone when trending score is available, hiding that sibling variants exist when they were collected

**Display rank**:
The 1-based position shown before each digest entry or search row. In digests it is the continuous index across the full entry list (mixed sections do not restart at 1). In search lists it is the order of rows actually shown after any Hugging Face family collapse.
_Avoid_: Raw Hub list index as the user-facing number, per-section rank that disagrees with follow-up `rank`, rank numbers that skip after grouping

**Release**:
A later optional enrichment on a GitHub item (what shipped), not the primary digest row.
_Avoid_: Using releases as the only way a repo can appear in the digest

### Follow-up

**Follow-up action**:
The suggested next learning move stored on a digest row (read, watch, try, or build). It is not chat follow-up.
_Avoid_: Structured follow-up, rank deep-dive, “follow-up section”

**Structured follow-up**:
Deterministic inspection of the current follow-up context via fixed phrases: show sources, study first, caveats, and rank. An untargeted browser follow-up uses that Session's latest successful digest; the CLI uses Shared-interface context.
_Avoid_: New path strings for removed interfaces, treating open-ended chat as structured follow-up, inventing Hub quality or Zhihu freshness beyond saved evidence

**Targeted follow-up**:
A follow-up bound to one saved entry in the current conversation, identified by digest identity and display rank. It does not change which digest untargeted follow-ups use.
_Avoid_: Free-text rank phrasing as the only way to select an entry, switching the conversation's latest digest, a historical search that leaves the conversation

**Deep dive**:
The targeted action that returns the source-specific rank deep-dive for the selected entry.
_Avoid_: Using it to answer an arbitrary typed question

**Ask about this**:
The targeted action that answers the typed question from the selected entry's evidence. It says when that evidence is insufficient.
_Avoid_: Repeating the full deep dive as the answer, searching other sources to fill a gap

**Rank deep-dive**:
The structured reply for one 1-based **display rank**. Kind-specific cards from saved digest evidence: Juya **issue deep-dive**, Hugging Face **family card**, Zhihu **practitioner-insight card**; other kinds stay a generic entry reprint. On the conversation's latest successful digest, Hugging Face may live-fetch the representative model-card README once (ADR-0006). A targeted follow-up on an older digest, and history show, stay persist-only. Zhihu stays persist-only.
_Avoid_: A digest-renderer “follow-up section”, giving Also variants their own ranks, synthesizing multiple Zhihu results, changing show-sources / study-first / caveats in the same change, git clone, Also-variant READMEs, Zhihu page fetch, treating history show or an older target as latest-digest enrich

**Issue deep-dive**:
The Juya rank deep-dive — one daily issue expanded into sub-news from persisted website markdown. Chinese chrome.
_Avoid_: Inventing sub-items not in persisted evidence, using this shape for Hugging Face families or Zhihu search snippets

**Juya daily issue**:
The default Juya digest item — one row per daily bulletin (RSS/markdown issue), with optional cover and lead metadata in the API view.
_Avoid_: Treating every Juya row as a single bulletin story, assuming story mode without an explicit web request

**Juya bulletin story**:
An opt-in Juya digest item — one numbered story from a daily issue when the web client requests story mode. It has its own display rank, history reference, and story-specific summary.
_Avoid_: Silent story mode on the CLI, inferring story identity from title alone, giving Also variants their own story ranks

**Digest presentation metadata**:
Whitelisted API fields derived from persisted connector evidence: publisher owner (name, profile, avatar, account type), GitHub preview image, Juya issue cover, and Juya story/issue structure. Not raw `source_evidence`.
_Avoid_: Exposing raw evidence, inventing daily star deltas or issue numbers, treating UI initials as a backend field

**Hugging Face family card**:
The Hugging Face rank deep-dive — the **model family** at that display rank: representative, comparison-table Hub stats, Also variants, publisher, card snippet, and the popularity-not-quality caveat. English chrome matching the comparison table. Snippet may come from collect-time card data or a once-fetched live model-card README (ADR-0006).
_Avoid_: Repeating only the table with no snippet, dumping every Hub key, git clone, Also-variant READMEs, treating the row as a raw weights repo rather than a family, inventing description from HTML

**Zhihu practitioner-insight card**:
The Zhihu rank deep-dive — that rank’s single **practitioner insight**: Chinese chrome, evidence-first snippet/lens/author, 搜索相关性 labeled as search relevance not 热度, optional labeled LLM 摘要 / 为什么值得看, thin-evidence and no-freshness caveats.
_Avoid_: Related-insight synthesis, parsing a snippet as Juya sub-news, fetching the linked page, treating relevance as 热度 or trending

**Historical digest search**:
Finding past saved digest entries by text, source, topic, and/or date. It is not latest-digest follow-up and not a search of unselected collected candidates.
_Avoid_: Vector memory, conversation memory, trend synthesis, searching NewsItems that never made a digest

**Historical item reference**:
A stable pointer to one saved digest entry by digest identity and original **display rank**, shown as `dN:rN`.
_Avoid_: Rank without digest identity, nearest-match guessing, treating the token as a latest-digest rank

**History show**:
Opening one historical item by **historical item reference** as a read-only **rank deep-dive** of that saved digest, without changing latest-digest follow-up context.
_Avoid_: Making the old digest the active follow-up context, live connector enrichment on historical open

**Session**:
A durable browser conversation thread that owns ordered chat messages, session-sticky source selection, and its own latest digest context. It permits one active **Session Request** at a time. Untargeted structured follow-ups inspect its latest successful digest. A targeted follow-up may inspect an older entry in that same conversation without changing the latest context. Historical digest search still spans the shared digest archive.
_Avoid_: An HTTP cookie/session token, an ephemeral browser tab, a user account or authorization boundary, multiple simultaneous requests in one session, treating all sessions as one global latest-digest context, using a session to limit historical digest search, making an older targeted digest the latest context

**Shared-interface context**:
The latest saved digest that does not belong to a browser session. CLI structured follow-ups inspect this context, independently of every browser Session.
_Avoid_: Global latest across every interface, a Session's context, a browser-created digest changing CLI follow-up behavior

**Session Request**:
One durable user-initiated chat execution within a Session, from accepted user message to one terminal outcome: succeeded, failed, cancelled, or interrupted. Its identity is bound to the original submission: message, target, action, and explicit options. An identical retry replays it; a different submission under that identity is refused.
_Avoid_: The user message itself, a Digest run, a transient delivery channel, automatically retrying an interrupted request, returning an old result for changed input

### Browser conversation

**Digest request (conversation)**:
A browser message asking for fresh signals, in English or Chinese, whether or not it uses the word “digest”. It carries its own topic, source, timeframe, count, language, and audience, and executes one Digest run.
_Avoid_: Requiring a trigger phrase, treating a source name alone as a request for collection, silently reusing saved preferences over an explicit option

**Digest follow-up**:
A browser message about a digest already in the conversation — explanation, inspection, or a change to how it is described. It reads saved evidence and does not collect again unless freshness, source, or timeframe changes.
_Avoid_: Fetching new signals for a rephrasing, answering from general knowledge when saved evidence exists

**General explanation**:
An answer from general knowledge to a standalone question that neither asks for fresh signals nor refers to a saved digest entry. It is labelled as general knowledge. A digest already being present does not by itself make the question a follow-up.
_Avoid_: Presenting it as a digest result, implying freshness, running source collection to answer it, changing the meaning because a digest exists or a language model is unavailable

**Unresolved clarification**:
The single pending question asked when a browser request is genuinely ambiguous. A short reply completes the original request. A self-contained new request, or an explicit targeted follow-up, replaces it and clears it durably.
_Avoid_: Stacking multiple pending questions, losing the original topic across a reload, treating the clarification reply as a new standalone request, restoring a clarification that a later request already replaced

**Resolved request**:
The options a Digest request actually ran with — sources, each source's count and effective time window, language, audience, and topic — shown with the question and restored after reload. Run again repeats these options.
_Avoid_: Echoing the composer's unconfirmed selection, exposing interpreter reasoning or raw evidence, claiming a result that was never collected, re-resolving the message against settings changed later

**No eligible results**:
A completed collection that found nothing matching the request's sources, filters, and timeframe.
_Avoid_: A failed collection presented as an empty digest

**Collection failure**:
A selected source that did not complete collection. It is not evidence that no matching items exist.
_Avoid_: Offering it as a normal empty digest, hiding the failure behind an alternative-source suggestion

**Partial results**:
A digest in which at least one selected source returned eligible entries and at least one selected source failed.
_Avoid_: Treating the whole digest as empty, hiding the failed source

**Run again**:
A new collection that repeats a previous request's resolved options, using fresh data and the provider credentials current at the new run.
_Avoid_: Replaying the saved response, re-resolving the original message against settings changed since that run

### Shared

**NewsItem**:
The normalized candidate collected from any connector before ranking and summarization.
_Avoid_: Treating every NewsItem as an article; shape depends on SourceKind

**SourceKind**:
Which source family produced a NewsItem (`github`, `bilibili`, `juya`, `huggingface`, `zhihu`, `openrouter`, …).
_Avoid_: Overloading `github` for Juya bulletin rows, treating OpenRouter and Hugging Face as the same source family

**Item count**:
The upper bound on eligible display entries one source may contribute. Filters, timeframe, and model-family grouping still apply. A shortfall is shown rather than filled by relaxing those constraints.
_Avoid_: A guaranteed exact count, counting packaging variants as separate Hugging Face families, silently widening the timeframe

**Juya all**:
The Juya item-count choice meaning every eligible story in the issues selected by the request, after topic and timeframe filtering. Summarizing more than 20 stories requires confirmation.
_Avoid_: An unlimited archive crawl, removing only the display cap while collection stays capped, applying all to other sources

**Output language**:
The language of generated digest text and entry labels. The saved preference is global: source default, English, or Simplified Chinese. Source default keeps each source's existing presentation language. A language named in the message overrides it for that run. Original titles, quotations, names, and identifiers stay as collected.
_Avoid_: A Juya-only language setting that changes every other source, translating quoted evidence

**Source profile**:
The saved settings for one source, shared by every conversation and by every supported interface that uses the same digest archive. Explicit request options override it.
_Avoid_: A per-conversation count, a web-only preference

**Owner access token**:
The shared credential that identifies the single owner of a remotely reachable app. It is neither a user account nor a provider credential.
_Avoid_: Per-user login, a provider API key, treating a browser conversation as a security boundary

**Provider credential**:
A credential the app uses to call a source or a language-model service.
_Avoid_: The owner access token, a per-conversation secret

**Unreadable credential override**:
A saved provider-credential override that exists but cannot be read. Operations that depend on it stay blocked until the owner restores the key, replaces the override, or explicitly deletes it.
_Avoid_: Treating it as unset, silently using an environment credential instead

**Source selection**:
Which connectors run for a digest. Bare digest with no platform cue defaults to Juya only. Explicit source lists, clear intent phrases, or platform-specific targets select those connectors and replace the Juya default unless Juya is also named or targeted. Juya targets are website URLs only (`daily.juya.uk`), not the former GitHub repo alias.
_Avoid_: Always running GitHub+Bilibili by default; always adding Juya on top of platform-targeted digests; requiring a source name when a target already implies the platform; routing `jujuyaya/juya-ai-daily` to Juya

**Cross-source ranking**:
When a digest mixes SourceKinds, candidates are scored with kind-aware features (not one naive “newsiness”), then presented in segmented sections by source rather than a single interleaved top-N. Section order is intent-first (primary kind from the ask leads); otherwise fixed fallback Juya → Hugging Face → OpenRouter → GitHub → Zhihu → Bilibili, omitting empty sections.
_Avoid_: One score that treats bulletins, trending models, repos, practitioner insights, and videos as the same kind of “newsiness” without kind-aware rules; interleaving unlike genres into one ranked list as the primary UX; unstable size-based section order
