# Targeted follow-ups, empty-digest suggestions, and conversation polish

Status: draft for review
Date: 2026-10-20

## Goal

Make "Ask a follow-up" answer about the exact entry the user clicked, and fix the rough edges seen in the running app: a flash of the empty state, dead-end empty digests, and inconsistent routing of identical messages.

## Problems observed

1. `prefillFollowUp` (`stores/composer.ts`) pastes free text that matches none of the rank patterns in `followup_structured.py`, so it skips the built-in deep dives (Juya story, live Hugging Face card, Zhihu card).
2. `get_followup_context_for_session` always loads the session's latest successful digest, so a follow-up about an older digest is answered from the newest one.
3. Opening a conversation with digests first shows "Start a digest", then the messages.
4. A digest with zero items offers nothing. Example: "Recent updates" ran on Juya only and found nothing.
5. "Tell me about Qwen" was answered directly once and met with a clarifying question the next time.

## Follow-up target

- `PostMessageBody` gains optional `followup_target: {run_id: int, display_rank: int}`.
- Validation: the run must belong to this session (a succeeded request with that `run_id`) and the rank must exist, otherwise `400`. The intent is forced to `followup`; the interpreter is skipped.
- Resolution: `ChatService` builds the follow-up context from `run_id` instead of the latest, then answers in two parts: first the existing deterministic deep dive for that entry's source kind, then, when an LLM is configured, a short grounded elaboration using only that entry's stored evidence. Without an LLM only the deterministic part is returned.
- Typed follow-ups with no target keep today's behaviour (latest digest in the session).
- The target is stored on the user message and returned on `MessageOut.followup_target`, so a reload restores the chip.
- Idempotency, cancellation and replay work unchanged because the target is part of the stored request.

## UI

- Per entry: **Deep dive** (sends at once with the target) and **Ask about this** (fills the composer and shows a removable chip "↳ d12 #3 title"; sending includes the target; removing the chip sends a plain message).
- The reply shows a "re: #3" link that scrolls to the entry.
- The user bubble shows the same chip from the stored target.
- Follow-up replies stay Markdown; rich cards are out of scope.
- Run again and suggestions keep their current behaviour.

## Empty-digest suggestions

- When a digest result has zero entries, the assistant message shows buttons for up to three other visible sources not used in that run, in catalog order, labelled "Try Hugging Face".
- A button sends a message naming that source and repeating the original topic. A source named in a message already applies to that run only, so no API change.
- Suggestions come from the visible source catalog, so hidden sources never appear.

## Loading state

- Switching conversations shows a skeleton thread until the first messages request resolves or fails.
- "Start a digest" shows only when loading has finished and the conversation has no messages.
- A failed load shows an error with Retry.

## Consistent routing

- First write the two Qwen cases as failing tests: the same text under the same context must give the same decision, and "Recent updates" after a pending clarification must keep its topic.
- Fix by making the rule order in `interpret_message` independent of incidental context (a model call or session source list must not change a rule-matched decision), and by logging the chosen branch.
- The scope is limited to what the tests expose. A rewrite of the interpreter is out of scope.

## Error handling

| Case | Behaviour |
|---|---|
| Target run not in session or rank missing | 400, composer shows "That entry is no longer available" and clears the chip |
| LLM unavailable | deterministic part only |
| Target digest has no stored evidence | generic entry card from the digest entry |

## Testing (TDD; one failing test per behaviour)

Backend:
1. A target selects its own run even when a newer digest exists.
2. A target from another session is rejected.
3. An unknown rank is rejected.
4. Each source kind returns its deterministic deep dive for a target.
5. LLM elaboration is grounded only in the targeted entry and skipped when no model.
6. `followup_target` persists and round-trips on `MessageOut`; replay keeps it.
7. Routing: the two Qwen cases give stable decisions.

Frontend:
8. Deep dive sends the target in one click; Ask about this shows the chip and sends the target; removing the chip drops it.
9. Chip restored from stored messages; "re: #n" scrolls.
10. Zero-item digest shows suggestions from visible sources only; click sends the right message.
11. Skeleton while loading; empty state only when truly empty; retry on failure.

Verification: regenerate OpenAPI and client; manual check in the running app on the conversation with three digests.

## Open items

None blocking. Decision recorded: targeted follow-ups use a structured field rather than text patterns, so the deterministic path is reached without relying on phrasing.
