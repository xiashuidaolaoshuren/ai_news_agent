# Juya story mode and digest presentation metadata

Status: accepted

The OpenDesign research-chat prototype needs publisher avatars, owner account types, Juya issue covers, GitHub social-preview images, and individual Juya bulletin stories as separate digest rows. Milestone 8A.1 already exposes a source-kind-discriminated `DigestView` built from persisted `NewsItem.source_evidence` on session SSE and transcript reload. Extending that projection is sufficient; separate avatar or image endpoints are unnecessary for the prototype.

## Considered options (rejected)

- **New `/api/v1/assets` or profile routes** — duplicates upstream URLs and adds proxy/cache scope the prototype does not need.
- **Make Juya stories the default everywhere** — breaks CLI, Gradio, OpenClaw, and historical rank semantics; issue deep-dive remains the correct shape for whole-bulletin follow-up.
- **Nested stories inside issue rows only** — avoids new ranks but prevents independent history references and per-story summarization.
- **SQLite columns for media URLs** — evidence already round-trips in `news_items.raw_payload_json`; a migration adds no capability.
- **Infer Juya issue numbers from story count** — upstream does not expose a verified issue number in markdown/RSS.

## Decision

1. Persist presentation metadata in whitelisted `source_evidence` keys during collection.
2. Project nullable fields through extended `DigestView` entry types (GitHub, Hugging Face, Juya).
3. Default Juya collection and all non-web interfaces remain **issue mode** (one row per daily issue).
4. Web `POST .../messages` accepts optional `juya_item_mode: stories` for that message only; replay semantics unchanged.
5. Juya stories use stable issue-plus-story-number identity; ranking deduplication treats marked story rows as distinct despite shared parent URLs.
6. History search unchanged; history show adds optional structured `entry` from saved evidence (no live fetch).

## Consequences

- Additive OpenAPI fields; old clients ignore them; old digests return null metadata.
- GitHub previews require an extra unauthenticated HTML fetch bounded by timeout and size.
- Hugging Face owner lookup is best-effort with non-fatal warnings on failure.
- Story digests change display-rank meaning for Juya-only runs; historical issue references remain valid.
