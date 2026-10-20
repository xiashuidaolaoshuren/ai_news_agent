# Web client always uses Juya story mode; composer sources are session preferences

Status: accepted; decision 2 superseded by ADR-0013

The approved prototype shows a Juya issue cover followed by numbered stories, and its composer shows source checkboxes and a per-source count as if they applied to each message. The 8A.1 backend stores sources and count as sticky session preferences (`PATCH /sessions/{id}`, count 1-20), and accepts `juya_item_mode` per message (ADR-0009).

## Considered options (rejected)

- **Add a Juya issues/stories toggle** — extra UI the prototype does not have; can be added later without contract change.
- **Always send issue mode** — contradicts the approved Juya section design.
- **Per-message sources on the message body** — a backend contract change with no benefit over session preferences for a single-user local app.
- **Cap the UI at 1-10 as in the prototype** — hides valid backend range for no gain.

## Decision

1. The web client sends `juya_item_mode: "stories"` with every message. CLI, Gradio and OpenClaw stay in issue mode (ADR-0009 unchanged).
2. Superseded by ADR-0013. Source checkboxes remain session preferences. The shared per-source stepper no longer writes an active session count; item counts live in global source profiles.
3. Stories are grouped client-side under one issue cover, keyed by `issue.id`. The UI shows no issue number because the API does not provide a verified one.

## Consequences

- Web Juya digests change display-rank meaning versus issue mode; historical `dN:rN` tokens remain valid.
- Preferences persist across reloads, but per-message source chips on past user messages are not available.
- A future toggle is additive.
