# Targeted follow-ups use digest identity and do not move latest context

Status: accepted

Free-text follow-ups were answered from a conversation's latest successful digest, so a click on an older entry could be explained from a newer one. The visible chip uses `dN`, while an early draft addressed the entry by run id. Those numbers are different identities. ADR-0006 also allows one live Hugging Face model-card fetch on the latest digest. Reusing that fetch unchanged reloads the global latest digest and would discard the targeted context.

Separately, a session request id currently replays a completed request without comparing the new submission. A targeted retry could then return the answer for entry #3 when the new submission names entry #5.

## Considered options (rejected)

- Keep addressing targets by run id and translate it in the interface — two public identities for one entry, and `dN:rN` would not match the stored target.
- Make the targeted digest the conversation's latest context — later untargeted follow-ups would silently move.
- Live-fetch the Hugging Face README for every targeted digest — older entries would change after the fact, which history show already refuses.
- Always return the full deep-dive card for a typed question — the card can hide the answer the user asked for.
- Treat a connector failure with zero items as an empty digest — a timeout would look like evidence that nothing was published.
- Replay whatever request id is presented — the id would no longer identify one submission.

## Decision

1. A targeted follow-up names `{digest_id, display_rank}` and an action, `deep_dive` or `ask`. The digest must belong to the conversation. Untargeted follow-ups still use the latest successful digest.
2. Deep dive returns the source-specific card. Ask about this answers the typed question from that entry and says when the evidence is insufficient. Neither searches other sources.
3. Hugging Face may fetch the representative README once only when the target is in the conversation's latest successful digest. The fetch reloads that digest. Older targets and history show stay saved-evidence-only.
4. A request id is bound to the original message, target, action, and explicit options. An identical retry replays it. A different submission with that id returns 409 and runs nothing.
5. No eligible results, collection failure, and partial results are different outcomes. Only a completed no-match result offers other sources as another search. That suggestion copies the resolved request and changes the source; it does not rely on the interpreter to reconstruct the options.

## Consequences

- This extends ADR-0006 rather than replacing it. The one-time live README fetch remains latest-digest-only.
- ADR-0008's terminal replay now includes the same-submission check. A changed body is a conflict, not a replay.
- A standalone question such as "Tell me about Qwen" stays a general explanation whether or not a digest exists. An explicit entry reference is a follow-up. A request for recent updates collects. A pending clarification is completed by a short reply and replaced by a self-contained new request or a targeted action.
