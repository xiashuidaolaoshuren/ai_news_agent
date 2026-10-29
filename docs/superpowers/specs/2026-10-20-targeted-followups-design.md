# Targeted follow-ups, empty-digest suggestions, and conversation polish

Status: agreed
Date: 2026-10-20
Review: agreed 2026-10-20. Vocabulary: [CONTEXT.md](../../../CONTEXT.md). Decisions: [ADR-0015](../../adr/0015-targeted-followups-and-request-identity.md).

## Goal

Make **Deep dive** and **Ask about this** answer about the exact entry the user selected, and fix the rough edges seen in the running app: a flash of the empty state, dead-end empty digests, and inconsistent routing of identical messages.

## Problems observed

1. `prefillFollowUp` (`stores/composer.ts`) pastes free text that matches none of the rank patterns in `followup_structured.py`, so it skips the built-in deep dives (Juya story, live Hugging Face card, Zhihu card).
2. `get_followup_context_for_session` always loads the session's latest successful digest, so a follow-up about an older digest is answered from the newest one.
3. Opening a conversation with digests first shows "Start a digest", then the messages.
4. A digest with zero items offers nothing. Example: "Recent updates" ran on Juya only and found nothing.
5. "Tell me about Qwen" was answered directly once and met with a clarifying question the next time.

## Follow-up target

The public target is `{digest_id: int, display_rank: int}`, the same identity as a historical item reference (`dN:rN`). Digest id and run id are different database identities and need not match. The server resolves the run from the digest.

- `PostMessageBody` gains optional `followup_target` and `followup_action: "deep_dive" | "ask"`.
- Validation: the digest must belong to this session, the rank must exist on it, and the action must be present when a target is present. Otherwise `400`. The intent is forced to `followup`; the interpreter is skipped.
- The target does not change the session's latest successful digest. Untargeted follow-ups still use that latest digest.
- Typed follow-ups with no target keep today's behaviour.

### Deep dive and Ask about this

- **Deep dive** returns the existing deterministic rank deep-dive for that entry's source kind. When an LLM is configured, it may append a short elaboration grounded only in that entry. Without an LLM, only the deterministic card is returned.
- **Ask about this** answers the typed question from that entry's evidence. If the evidence is insufficient, the reply says so and does not search other sources. Without an LLM, it shows the deterministic card and says that question-specific answering is unavailable.
- On the session's latest successful digest, a Hugging Face target may live-fetch the representative model-card README once, label that snippet as fetched after the digest, and save it. The fetch must reload the targeted digest, not the global latest digest. Older targets, history show, and Zhihu stay saved-evidence-only.
- An older target labels its model-card snippet as saved with that digest. Only a target in the conversation's latest successful digest may be labelled as fetched after it, so a card never implies a fetch that did not happen.
- A card renders the fields its saved evidence provides. A field the digest never recorded shows `Not saved`. It is never inferred, backfilled from a later run, or dropped without trace.
- When the entry has `related_display_ranks`, the card shows the same Related link its digest row shows; otherwise it shows none.
- The target and action are stored with the user message and returned on `MessageOut`, so a reload restores the chip.
- Idempotency binds the session request id to the original message, target, action, and explicit options. An identical retry replays the stored request and its saved settings. The same id with different input returns `409` and executes nothing. A change to global settings alone does not invalidate an identical retry.

## UI

- Per entry — a block entry or one Hugging Face comparison-table row — **Deep dive** (sends at once with the target and `deep_dive`) and **Ask about this** (fills the composer and shows a removable chip `↳ d12 #3 title`; sending includes the target and `ask`; removing the chip sends a plain message).
- The reply shows a `re: #3` link that scrolls to that entry in its digest.
- The user bubble shows the same chip from the stored target.
- Follow-up replies stay Markdown; rich cards are out of scope.
- **Run again** repeats the original resolved request, including counts, filters, timeframe rules, and output language. It collects fresh data and uses the provider credentials current at the new run. It is not replay: replay returns the stored request and never re-resolves settings or collects again.

## Empty and failed collection

Distinguish three outcomes:

| Outcome | Meaning | UI |
|---|---|---|
| No eligible results | Collection completed and nothing matched | Up to three buttons for other visible sources, in catalog order, such as "Try Hugging Face" |
| Collection failure | A selected source did not complete | Explain the failure. Prefer Retry or credential repair. Alternatives may be offered as alternatives, not as proof the source had no news |
| Partial results | At least one source returned entries and at least one failed | Show the entries and name the failed source |

- A no-results suggestion creates a new digest request from the original resolved options, changing only the source. It keeps an explicit topic, timeframe, language, and audience. For count and source filters the original message did not set, it uses the destination source's saved profile. The button states what will run; the interpreter does not reconstruct those options from text.
- Suggestions come from the visible source catalog, so hidden sources never appear.
- A suggestion is a new request. It replaces a pending clarification.

## Loading state

- Switching conversations shows a skeleton thread until the first messages request resolves or fails.
- "Start a digest" shows only when loading has finished and the conversation has no messages.
- A failed load shows an error with Retry.

## Consistent routing

Rule-matched decisions do not change because a digest exists, a model is available, or the session source list differs.

- A standalone "Tell me about Qwen" is a **general explanation**, with or without an existing digest. It is labelled as general knowledge.
- "Explain the Qwen entry above", or another explicit digest reference, is a follow-up over saved evidence.
- "Recent Qwen updates", or another request for fresh signals, is a digest request.
- If a general explanation needs an LLM and none is configured, say so. Do not change the intent to a digest or a clarification.
- While a clarification is pending, a short direct reply completes the original request and keeps its topic. A self-contained new request replaces it. An explicit targeted action also replaces it. The replacement is persisted, so a reload cannot restore the old clarification.
- Log the chosen branch. The scope is these rules, not a rewrite of the interpreter.

## Error handling

| Case | Behaviour |
|---|---|
| Target digest not in session, or rank missing | 400; composer shows "That entry is no longer available" and clears the chip |
| Same request id, different message, target, action, or explicit options | 409; nothing runs |
| LLM unavailable for Deep dive | deterministic card only |
| LLM unavailable for Ask about this | deterministic card, plus a statement that question-specific answering is unavailable |
| Targeted entry has no stored evidence | generic entry card from the digest entry |
| Card field the digest never recorded | shows `Not saved`; no inference or backfill |
| Older Hugging Face target | saved evidence only; no live README fetch; snippet labelled as saved with that digest |

## Testing (TDD; one failing test per behaviour)

Backend:

1. A target selects its own digest even when a newer digest exists, and leaves the latest-digest context unchanged.
2. A target from another session is rejected.
3. An unknown rank is rejected.
4. Deep dive returns the deterministic card; Ask about this answers the question from that entry only.
5. A latest-digest Hugging Face target may fetch the README once; an older target does not, and the fetch does not replace the targeted context with the global latest.
6. A card shows `Not saved` for a stat the digest never recorded and never infers it. An older target labels its snippet as saved with that digest; a latest-digest fetch is labelled as fetched after it.
7. LLM elaboration or answers use only the targeted entry and are skipped, with the agreed fallback, when no model is configured.
8. `followup_target` and action persist and round-trip on `MessageOut`.
9. An identical request id replays; a changed body with that id returns 409.
10. Routing: standalone "Tell me about Qwen" is general explanation with and without a digest; an explicit entry reference is follow-up; "Recent updates" after a pending Qwen clarification keeps Qwen.
11. A no-results suggestion preserves explicit options and changes only the source. A connector failure is not presented as no eligible results.
12. Each Hugging Face comparison-table row resolves to the same entry target as a block entry, and its Deep dive renders the family card.

Frontend:

13. Deep dive sends the target and action in one click, including from a comparison-table row. Ask about this shows the chip and sends both. Removing the chip drops them.
14. Chip restored from stored messages; `re: #n` scrolls to the entry in that digest.
15. No-results, failure, and partial-results states show the actions defined above.
16. Skeleton while loading; empty state only when truly empty; retry on failure.
17. A Related link on a card scrolls to the other entry, and is absent when the entry has no related ranks.

Verification: regenerate OpenAPI and client; manual check in the running app on the conversation with three digests.

## Open items

None blocking.
