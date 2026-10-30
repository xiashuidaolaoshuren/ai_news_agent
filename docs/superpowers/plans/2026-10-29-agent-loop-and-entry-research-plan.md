# Implementation plan: Entry-bound research

**Spec:** `docs/superpowers/specs/2026-10-29-agent-loop-and-entry-research-design.md`
**ADRs:** `docs/adr/0016-hybrid-agent-loop-and-separate-research-records.md`, `docs/adr/0015-targeted-followups-and-request-identity.md`
**Depends on:** `docs/superpowers/plans/2026-10-20-followups-settings-backend-plan.md` task **B1** (entry resolver and submission identity) and task **B5** (schema 4). **B2** must stay intact when research ships. The frontend piece does not block R1–R8. **R9** consumes frontend **U1**.
**Created:** 2026-10-30
**Goal scope:** One goal: an explicitly authorized investigation of one saved entry, with application-enforced source scope and budgets, evidence the model evaluates, and a research record stored apart from the digest. Digest generation and exact listings stay on their current paths.

## Summary

Research is a separate session operation. It reuses B1's `{digest_id, display_rank}` resolution and does not add a value to `followup_action`. The model may choose another permitted fetch after it sees an observation. The application decides the target, the scope, the budgets, and when to stop. Findings go in a research record. A later follow-up may reuse that record without fetching. A continuation is a new Session Request.

Scope policy, the observation schema, the fetcher, and the research loop can be built before the follow-ups UI. Chat binding waits on **B1**. The record store waits on **B5**, because settings owns schema 4 and research records are schema 5.

## Discovery notes

- Reuse: B1's session-owned digest resolution and the submission comparison on `begin_request`. Research fields join that comparison. They are not a third `FollowupAction`.
- Reuse: `ToolObservation` in `tools/schemas.py` (`status`, `summary`, `data`, `caveats`). Research observations extend that envelope; they do not replace it for connector tools.
- Reuse: `build_tool_agent_runner` in `tools/agent.py`. An OK observation with nonblank `formatted_text` becomes a terminal conversational result. `tests/test_tool_agent.py` locks that for listings. Research gets its own runner and does not turn that short-circuit off.
- Reuse: `github_previews.py` bounds (`PREVIEW_TIMEOUT` 5s, `PREVIEW_MAX_REDIRECTS` 3, streaming size cap, off-host redirect rejection). Research fetch is a new module with its own cap. Digest connectors, including Zhihu, stay non-crawling.
- Reuse: `DigestStore` schema migrations. Settings **B5** moves schema `"3"` to `"4"`. Research records are schema `"5"` on top of that. `session_requests` remains the lifecycle: succeeded, failed, cancelled, interrupted. Replay and conflict stay B1's rule.
- Reuse: `get_followup_context_for_digest` for the selected entry's saved evidence. Research must not call `get_latest_followup_context()` as a substitute for the targeted digest.
- Constraint: the public research fields below are the contract this plan locks. The spec left them unspecified. A later change to the names is material.
- Constraint: budgets below are the spec's candidates, now the implementation contract. Per-document and aggregate text caps are still unnamed; **R5** settles them in Plan mode before coding.
- Constraint: citation checks prove a passage id was in the evidence supplied to the model. They do not prove the passage supports the claim.
- Patterns to follow: flat modules beside `huggingface_followup.py` and `github_previews.py`; Pydantic models; pytest per module; Vue entry actions from the follow-ups plan rather than a new visual language.
- Anti-goals: no MCP client, no LangGraph replacement, no global change to digest workflow, no web-wide search, no multi-entry comparison, no code execution, no model-weight download, no raw HTML or full-document archive, no research value on `followup_action`, no drive-by refactor that parameterizes the listing short-circuit "while here."

## File map

### Goal: Entry-bound research

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|---|---|---|---|---|
| `src/ai_news_agent/api/schemas/sessions.py` | modify | Research request fields beside the follow-up fields | `ResearchTarget`, `PostMessageBody.research_target`, `PostMessageBody.research_continuation_of` | verified path; names locked here |
| `src/ai_news_agent/research_evidence.py` | create | Observation and passage models | `ResearchObservation`, `ResearchPassage` | provisional |
| `src/ai_news_agent/research_scope.py` | create | Publisher and project-scope decisions | `authorize_research_url(...)` | provisional |
| `src/ai_news_agent/research_fetch.py` | create | Bounded fetch and extraction inside an approved scope | `fetch_research_source(...)` | provisional |
| `src/ai_news_agent/research_loop.py` | create | Research runner, budgets, finalization | `build_research_runner(...)` | provisional |
| `src/ai_news_agent/repositories/digest_store.py` | modify | Research records at schema 5, after settings schema 4 | `save_research_record`, `get_research_record` | verified path; table layout provisional |
| `src/ai_news_agent/services/chat.py` | modify | Dispatch research, saved-evidence follow-up, and continuation | `ChatService.stream_events` | verified |
| `src/ai_news_agent/services/conversation.py` | modify | Explicit research wording and ambiguous subject | `interpret_message` only when no research target field is present | verified |
| `src/ai_news_agent/tools/agent.py` | — | Listing and digest tool loop | unchanged | verified |
| `tests/test_research_evidence.py` | create | Observation contract | pytest | provisional |
| `tests/test_research_scope.py` | create | Allow and deny cases | pytest | provisional |
| `tests/test_research_fetch.py` | create | Extraction, redirects, limits | pytest | provisional |
| `tests/test_research_loop.py` | create | Budgets and non-termination | pytest | provisional |
| `tests/test_research_store.py` | create | Records, replay, continuation link | pytest | provisional |
| `tests/test_chat.py` | modify | Research does not move latest context or rewrite the digest | pytest | verified |
| `tests/test_tool_agent.py` | — | Listing short-circuit | unchanged assertions | verified |
| `frontend/src/components/thread/EntryRow.vue` | modify | Research action beside Deep dive and Ask about this | entry foot | verified |
| `frontend/src/components/thread/HfTable.vue` | modify | Same action on a comparison-table row | actions cell | verified |
| `frontend/src/stores/composer.ts` | modify | Send `research_target` | composer store | verified |
| `frontend/src/stores/thread.ts` | modify | Partial result and continuation offer | thread store | verified |

### Blast radius

| Path | Why sensitive | Behavior that must stay intact | Plan mode |
|---|---|---|---|
| `services/chat.py` `stream_events` | Every session send | Digest, Deep dive, Ask about this, history show, general explanation | high |
| `services/session_service.py` `begin_request` | Submission identity from B1 | Identical replay and `request_conflict` 409; research fields are additional compared keys | high |
| `repositories/digest_store.py` | Schema 3 databases | Existing tables and `interpretation_json`; research rows do not update `digests` | high |
| `tools/agent.py` | Exact listing rendering | `formatted_text` short-circuit and the five-turn cap for the existing runner | skip (do not edit) |
| `followup_enrich.py` | ADR-0006 | Latest-digest README exception unchanged | skip |

## Workflow (for implementers)

1. **writing-plans** produced this file (type-1 decomposition only).
2. **R2**, **R3**, **R4**, and **R5** do not wait for the follow-ups plans. **R1** waits for backend **B1**. **R6** waits for backend **B5** so schema 5 follows settings schema 4. **R7** also waits for **B2** so older-entry deep dive and history show stay persist-only.
3. Per subtask: **Plan mode** + **planning-subtasks** when **Plan mode** is `high` (or `medium` with a real remaining unknown).
4. **Agent mode**: **test-driven-development** when `TDD suitable: yes` (or the testable slice of `partial`).
5. Do not edit `tools/agent.py` to "support research." A new runner in `research_loop.py` is the boundary.
6. Update this document if reality diverges; add a **Plan changelog** row.

## Subtasks

Dependency notation: `Blocked by: R3` means start after R3 is done. `Blocked by: B1` means the follow-ups backend plan task.

### R1 — Research request identity

- [ ] **Do:** Accept an explicit research request for one conversation entry without using `followup_action`.
- **Consumes:** Backend **B1** resolver: the digest belongs to the session, the rank exists, and the latest successful digest does not move. B1 submission comparison.
- **Produces:** `ResearchTarget { digest_id: int, display_rank: int }`. `PostMessageBody.research_target`. `PostMessageBody.research_continuation_of: str | None` (a prior session request id). Sending `research_target` together with `followup_target` returns 400. A present `research_target` skips `interpret_message`, binds that entry, and is part of the submission comparison. Text that explicitly asks to research an entry in the conversation is the same operation when the target is unambiguous. An evidence-only Ask about this may say that research is available and must not fetch. Ambiguous subject uses the existing single pending clarification and does not retrieve.
- **Acceptance:** "Research whether item 3 can run on my 8 GB GPU," or acceptance of a specific offer, starts research and does not ask for a second confirmation. Ask about this with insufficient evidence does not fetch. The target stays the selected entry after a newer digest. Latest-digest context is unchanged. A subject that the entry does not identify is clarified before any fetch, and a model family does not switch size or variant. A body that sets both research and follow-up targets returns 400. An identical request id replays. A changed research target or continuation id under that id returns 409 `request_conflict`.
- **Compatibility:** `followup_action` remains `deep_dive | ask` only. Deep dive and Ask about this are unchanged except the offer sentence, which does not retrieve.
- **Blocked by:** B1
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_api_sessions.py tests/test_chat.py tests/test_conversation.py -q`

### R2 — Source scope

- [ ] **Do:** Decide whether a candidate URL may be read for the selected entry, before any fetch.
- **Consumes:** The selected entry's saved source URL and ownership fields. No network.
- **Produces:** `authorize_research_url(entry, url, approved_scopes) -> ResearchAuthorization` with allow, deny, or unverified, plus publisher attribution and the approved project scope when allow. Deny reasons cover: another repository on a shared host, a link or redirect outside the approved project path, a private or local network destination, and a publisher the application has not accepted.
- **Acceptance:** The original source URL is allowed as the entry's own page and is not treated as proof of its claims. Verified original-developer documentation and verified exact-variant maintainer documentation are allowed and attributed separately. A bare link, a page title, an "official" label, or a model assertion does not authorize a publisher. After a documentation entry point is verified, further URLs on that host and project path can be allowed. Another owner or repository on that host is denied. An allowed page's outbound link does not add a publisher. Redirect targets are decided again, not trusted from the first URL. Page text is not an input to the decision.
- **Compatibility:** None of this runs on digest collect or ordinary follow-ups.
- **Blocked by:** —
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_research_scope.py -q`

### R3 — Research observation

- [ ] **Do:** Define the evidence object the fetcher, the loop, the citation check, and the record all share.
- **Consumes:** `ToolObservation` field meanings (`status` is execution, not answerability).
- **Produces:** `ResearchPassage { passage_id: str, text: str }`. `ResearchObservation` with requested URL, final URL, evidence id, publisher, relationship to the target, approved scope, retrieval time, `fresh: bool`, passages, extraction completeness (`complete | truncated | unsupported | unsuccessful`), retrieval outcome (`retrieved | inaccessible | refused | failed`), and candidate links that are not yet approved. A readable document with no answer uses retrieval outcome `retrieved` and does not use `inaccessible`.
- **Acceptance:** The model can be given a hand-built observation with no fetch. Inaccessible content and readable content that lacks the answer are different. Truncation is visible. A candidate link in the observation is not an authorization. Execution status stays separate from whether the question is answered.
- **Blocked by:** —
- **Plan mode:** skip
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_research_evidence.py -q`

### R4 — Bounded fetch

- [ ] **Do:** Fetch and extract one authorized URL into an R3 observation.
- **Consumes:** R2 `authorize_research_url`. R3 `ResearchObservation`. The timeout, redirect limit, and streaming size-cap pattern in `github_previews.py`.
- **Produces:** `fetch_research_source(...) -> ResearchObservation`. Unsupported or unreachable sources come back as limitations. Extracted text is bounded. Candidate links are listed with their URLs and are not fetched by this call.
- **Acceptance:** An allowed URL returns passages with stable ids, the final URL, and `fresh=True`. A redirect outside the approved scope is refused and not saved as success. A private or local destination is refused. An oversize body is truncated or unsuccessful according to the cap, and the observation says which. An unsupported format is `unsupported`, not an empty success. A failed fetch is not stored as evidence that the fact is absent. Zhihu digest collect and ordinary follow-ups still do not crawl.
- **Compatibility:** `github_previews.py` behavior is unchanged.
- **Blocked by:** R2, R3
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_research_fetch.py tests/test_connectors_zhihu.py -q`

### R5 — Research loop

- [ ] **Do:** Let the model evaluate research observations and apply the budgets in application code.
- **Consumes:** R3 observations. A fake tool that returns them. Not `build_tool_agent_runner`.
- **Produces:** `build_research_runner`. Limits, enforced before another tool starts, including when one model turn requests several tools: at most 6 retrieval attempts; at most 8 model calls, one of them reserved for the final answer; a deadline of about 90 seconds that leaves time for that final call. Identical successful fetches are reused and do not count as new retrievals. Retries count. Repeated calls that add no evidence stop early. Rejected authentication and disallowed destinations are not retried. Cited passage ids must exist in the evidence supplied to the model. If the final model call fails, the runner returns an application summary of the sources and the failure, with no invented conclusion.
- **Acceptance:** A research observation that contains formatted text is returned to the model for another decision. The listing runner's formatted-text short-circuit still terminates, and `tests/test_tool_agent.py` is unchanged. Two tools in one turn both count. A duplicate successful URL is reused. No-progress repetition stops before the retrieval cap. Hitting a limit returns supported findings, the gap, and the stop reason, and does not extend the budget. The final-answer call still has a reserved model slot when retrieval stops at the cap. Passage ids that were not supplied fail the citation check. A passage that exists is not treated as proof of the model's reading. Estimates in the prompt contract are labelled as estimates with assumptions, not as documented requirements.
- **Compatibility:** Digest workflow and `tools/agent.py` are unchanged.
- **Blocked by:** R3
- **Plan mode:** high (named unknown: per-document text cap, aggregate evidence cap, and per-call timeout, chosen so the 90-second deadline still leaves a final answer)
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_research_loop.py tests/test_tool_agent.py -q`

### R6 — Research records

- [ ] **Do:** Persist the investigation apart from the digest, and reuse the Session Request lifecycle.
- **Consumes:** R3 observations, including the bounded text actually supplied to the model. `session_requests` statuses. Schema migration style in `digest_store.py`. Settings **B5** leaves the database at version `"4"`.
- **Produces:** Schema version `"5"`, applied after settings schema `"4"`, and a research-record table. `save_research_record` / `get_research_record` store question, target, clarified subject, session id, request id, evidence, answer, qualifications, limitations, and stop information. Continuation stores the prior request id. Saved rows are not written into `digests` or `news_items`.
- **Acceptance:** The record keeps the bounded text supplied to the model, not only the cited passages, plus provenance, passage ids, retrieval times, and truncation. An identical retry does not insert another investigation. A changed submission under the same request id does not overwrite the record. Cancellation, interruption, disconnect, and a failed save follow the existing request statuses and do not claim the evidence was saved when it was not. Deleting a session removes its research records with the session.
- **Compatibility:** Digest rows and latest-digest context are unchanged by a save.
- **Blocked by:** R3, B5
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_research_store.py tests/test_digest_bundle.py -q`

### R7 — Session chat wiring

- [ ] **Do:** Run an authorized research request through R5, save R6, and leave the other chat paths alone.
- **Consumes:** R1 binding, R4 fetch, R5 runner, R6 records. Backend **B2** cards and the ADR-0006 fetch.
- **Produces:** A research turn that can call the research tool only inside R2's decision. A follow-up that names the research record answers from the saved evidence, keeps the original retrieval time, and does not fetch. A continuation is a new request linked with `research_continuation_of`, reuses saved evidence, and fetches only when the user explicitly asks to refresh. Stopped runs offer continuation and do not extend the budget.
- **Acceptance:** The acceptance scenario's steps hold for one community-maintained variant: clarify if needed, read the original source, verify maintainer docs before leaving that source, navigate only inside the approved scope, cite documented facts, label estimates, and keep conflicts visible. A limit or fetch failure returns partial findings and a continuation offer. Final-model failure returns the application summary. The digest and latest-digest context are unchanged. An older entry's deep dive and history show stay persist-only. A research observation does not take the listing short-circuit. Source text cannot change the target, the tool list, or a budget. A saved-evidence follow-up does not present the record as freshly checked.
- **Compatibility:** B2, B3, and B4 behaviors stay. `tools/agent.py` stays.
- **Blocked by:** R1, R4, R5, R6, B2
- **Plan mode:** high
- **TDD suitable:** yes
- **Verification:** `uv run pytest tests/test_chat.py tests/test_huggingface_followup.py tests/test_tool_agent.py -q`

### R8 — Contract check

- [ ] **Do:** Prove the schema, the untouched listing loop, and the offline suite.
- **Consumes:** R1–R7.
- **Produces:** OpenAPI lists `research_target` and `research_continuation_of`. `followup_action` is still only `deep_dive` and `ask`.
- **Acceptance:** `GET /openapi.json` contains the research fields and does not add a research enum value. `uv run pytest -q` passes with no network.
- **Blocked by:** R1, R2, R3, R4, R5, R6, R7
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** the schema-presence test is test-first; the rest is the existing suite.
- **Verification:** `uv run pytest -q`

### R9 — Research controls in the thread

- [ ] **Do:** Add a research action beside Deep dive and Ask about this, using the entry-foot pattern from frontend **U1**.
- **Consumes:** R1 `research_target` and `research_continuation_of`. U1 anchors `deepdive-*` and `followup-*`. The current prototype has no research control; do not invent a second chrome. Use the same `link-btn` row.
- **Produces:** A research control on each block entry and each Hugging Face row. It sends `research_target` and does not send `followup_action`. A partial answer offers continuation, which sends a new request with `research_continuation_of`. A follow-up on a saved research answer does not send a fetch.
- **Acceptance:** The control is present on a block entry and a comparison-table row, and absent from history-show persist-only actions. Ask about this still sends `ask`. Continuation creates a new request id. The thread shows the stop reason and does not label saved evidence as freshly checked.
- **Compatibility:** U1 chip, Deep dive, and Ask about this stay.
- **Blocked by:** R8, U1
- **Plan mode:** high
- **TDD suitable:** partial
- **TDD suitable reason:** the request payload is testable; the control's placement is checked in the app next to the prototype's entry actions.
- **Verification:** `npm test -- --run src/components/thread/entry-row.test.ts src/stores/thread.test.ts` from `frontend/`, then a browser pass of research, continuation, and Ask about this on one entry.

## TDD note (Agent mode)

Per subtask, obey **`TDD suitable`**. **`yes`** means strict test-first. The listing short-circuit is already covered; do not add a RED cycle whose only purpose is to keep `tools/agent.py` unchanged. Run `tests/test_tool_agent.py` as the regression when a task claims that file was not edited.

## Plan changelog

| Date | Change | Kind |
|---|---|---|
| 2026-10-30 | Initial plan | — |
| 2026-10-30 | Follow-ups F1/F2/F5 became backend B1/B2 and frontend U1. Research records moved from schema 4 to schema 5 because settings owns schema 4. | material |
