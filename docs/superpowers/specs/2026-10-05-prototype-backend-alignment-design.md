# Prototype Backend Alignment — Design

**Created:** 2026-10-05  
**Follow-on to:** Milestone 8A.1 Web API and Sessions (`docs/superpowers/specs/2026-09-11-milestone-8a1-web-api-and-sessions-design.md`)

## Goal

Extend the existing `/api/v1` digest contract so the OpenDesign research-chat prototype can render publisher avatars, organisation/person account types, Juya issue covers, GitHub hover previews, and opt-in individual Juya story rows — without new profile/image endpoints or breaking CLI, Gradio, or OpenClaw.

## Non-goals

- Vue/OpenDesign implementation
- Zhihu/Bilibili author avatars
- GitHub daily star deltas
- Database schema migration or archive backfill
- Media proxying or authentication

## DigestView extensions

Additive source-specific fields on the existing `source_kind` discriminated union:

| Source | New fields |
|--------|------------|
| GitHub | `owner` (name, profile_url, avatar_url, type), `preview_image_url`, `stars`, `language` |
| Hugging Face | `owner` (same shape) |
| Juya | `item_type` (`issue` \| `story`), `issue` (id, date, url, cover_url, lead_title), `story` (number, section, original_url) |

`owner.type` is `organisation` or `person` (platform account kind, not verified identity). Missing upstream data → JSON `null`. Old saved digests keep nulls.

## Collection

- **GitHub:** map REST `owner` fields into `source_evidence`; fetch canonical repo page `og:image` via a separate unauthenticated client.
- **Hugging Face:** after family grouping, enrich representatives via public `/api/organizations/{name}/overview` with `/api/users/{name}/overview` fallback only on definitive 404.
- **Juya issue mode (default):** parse raw markdown before flattening; persist cover/date/lead in evidence; unchanged issue snippets.
- **Juya story mode (opt-in):** one `NewsItem` per numbered bulletin story; stable `issue_id + story_number` identity; cap applies to stories.

## Web opt-in

`POST /api/v1/sessions/{id}/messages` accepts optional `juya_item_mode: issue | stories` (default `issue`). Per-message only; not sticky on session. Request replay returns saved outcome regardless of new options.

## History

- Search unchanged.
- Show adds optional structured `entry` (same projection as session digest) alongside existing markdown.

## Compatibility

Issue mode remains the default for web, CLI, Gradio, and OpenClaw. Story mode is explicit per web message. Historical `dN:rN` tokens remain valid; story digests give each story its own rank.
