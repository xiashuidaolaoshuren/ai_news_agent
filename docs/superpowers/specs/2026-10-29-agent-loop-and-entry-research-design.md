# Agent loop and explicitly authorized entry-bound research

Status: agreed; not implemented
Date: 2026-10-29
Review: agreed through the agent-loop and research grilling session on 2026-10-29.
Vocabulary: [CONTEXT.md](../../../CONTEXT.md).
Decision: [ADR-0016](../../adr/0016-hybrid-agent-loop-and-separate-research-records.md).
Related: [Targeted follow-ups](2026-10-20-targeted-followups-design.md), [ADR-0006](../../adr/0006-huggingface-live-model-card-on-rank-followup.md), and [ADR-0015](../../adr/0015-targeted-followups-and-request-identity.md).

## Goal and status

Improve the agent's ability to evaluate tool results against the user's actual question and choose the next useful, permitted action. Preserve predictable digest generation and exact source-specific presentation rather than making every operation model-controlled.

This document records agreed future behavior, not a claim that research tools, permissions, budgets, or research-record persistence already exist. It is a design specification, not an implementation plan. Numerical budget candidates and engineering details identified below still require implementation planning and validation.

## Foundations

An agent loop consists of distinct responsibilities:

1. The model proposes an answer, a clarification, or a structured tool request.
2. The application validates and authorizes the request, executes the tool, and returns its observation.
3. The model evaluates the observation against the question and decides whether another permitted action is useful.
4. The application enforces completion, resource limits, cancellation, and durable outcomes independently of the model's preferences.

Function calling structures a model's request; application code performs the operation. Model Context Protocol (MCP) standardizes integration with external tools and context. Neither MCP nor additional tools substitutes for evidence evaluation, authorization, or stopping rules. Introducing MCP or replacing LangGraph is not a prerequisite for this design.

## Findings from the current implementation

The following were inspected on 2026-10-29:

- [`graph/workflow.py`](../../../src/ai_news_agent/graph/workflow.py) defines the fixed digest workflow: parse, collect, rank, summarize, persist, render, and finalize.
- [`tools/agent.py`](../../../src/ai_news_agent/tools/agent.py) already implements a bounded model/tool loop. Its default cap is five model turns; a single turn may request multiple tools, so this cap alone does not bound retrieval attempts, tokens, or elapsed time.
- The runner treats digest and structured tool results as terminal. It also turns an OK observation containing nonblank `formatted_text` into a terminal conversational result, without another model evaluation of that observation.
- [`tests/test_tool_agent.py`](../../../tests/test_tool_agent.py) deliberately covers formatted search output bypassing model paraphrasing. Preserve this behavior for listing requests; do not globally remove exact rendering to introduce research.
- [`tools/interface_router.py`](../../../src/ai_news_agent/tools/interface_router.py) uses the runner for live open-ended session follow-ups and exposes registry tools backed by connectors. The new research source boundary is therefore an application/tool restriction, not a prompt-only instruction or an assertion that today's registry is research-restricted.
- [`tools/schemas.py`](../../../src/ai_news_agent/tools/schemas.py) already supplies observations with status, summary, data, and caveats. Research needs additional evidence identity, provenance, extraction limitations, and citation support.
- The current runner's iteration-exhaustion fallback does not provide the research-specific partial findings and saved evidence required here.

The key distinction is **tool completion versus task completion**. A formatted listing may complete a listing request; a formatted tool response must not automatically complete a research question.

## Scope and request boundaries

### Hybrid execution

- Digest collection, ranking, persistence, and exact structured views retain their predictable workflows.
- Authorized research uses an adaptive model/tool loop. Open-ended analysis may use the same loop discipline while remaining within its existing evidence permissions; openness of a question is not permission to retrieve new information.
- Application code controls allowed tools, arguments, target identity, source scopes, execution budgets, and cancellation. A model may choose actions only within those constraints.
- The first research capability investigates one explicitly selected saved entry in the current conversation. Multi-entry comparison, standalone candidate discovery, broad web research, code execution, and model-weight downloads are outside this version.
- If one entry contains multiple possible subjects, such as a Juya daily issue, and the question does not identify its subject, clarify before retrieving. Selecting a model family does not authorize silently switching model size, version, or variant.

### Authorization and existing follow-ups

- An evidence-only follow-up answers from its permitted saved evidence and identifies missing information. It may offer research but cannot silently start it.
- A direct instruction such as "Research whether item 3 can run on my 8 GB GPU" is already authorization. Acceptance of a specific offer to investigate also authorizes a research request. Avoid redundant confirmation when the request is already explicit and its target is unambiguous.
- Bind the research request to the selected entry in application code. Retain digest identity and display rank semantics; digest id and run id are different identities.
- Research does not change the conversation's latest successful digest, regenerate a digest, rerank entries, or broaden the selected target.
- **Deep dive**, **Ask about this**, **history show**, and historical search retain their existing contracts. In particular, Ask about this does not become an automatic research action. ADR-0006/ADR-0015's once-only latest-digest Hugging Face README enrichment remains a separate existing exception; this design neither removes it nor extends it to older targets.
- An explicitly authorized research request is a separate operation, including when it concerns an older entry in the conversation. Its new evidence belongs to a research record, not an update to that historical digest. Opening an old entry is still persist-only.
- The public research action, endpoint fields, and UI affordance remain implementation-planning details; this document does not add a new value to the existing `followup_action` contract.

## Source authorization and navigation

### Original source and maintainer authority

- The original source is the page or repository represented by the selected entry. It may be community-maintained or third-party coverage; permission to read it does not imply its statements are authoritative.
- Beyond that source, permit directly linked documentation whose publisher has an established responsibility for the exact project, model, or variant being investigated.
- Verified maintainer documentation may come from the original developer or a community maintainer of the selected variant. Attribute each source accordingly. Base-model documentation must not be presented as variant-specific validation.
- Establish the publisher relationship using application-accepted ownership information or explicit configuration. A model assertion, familiar-looking domain, page title, "official" label, or mere hyperlink is insufficient.
- When the relationship cannot be established, explain the limitation and use the evidence already permitted. Do not silently substitute general web search or unrelated documentation.

### Bounded documentation scopes

- After a documentation entry point is verified, allow additional navigation within its approved host and relevant project path or repository. This intentionally permits more than one link hop, while remaining bounded by retrieval and content limits.
- Authorization is project-specific. A verified repository on a shared host does not authorize the whole host, other owners, or unrelated repositories.
- Links and redirects must remain within an approved scope. An allowed page cannot authorize a new external publisher or project by linking to it. Revalidate destinations rather than trusting the initial URL alone.
- Source content is untrusted evidence, not an instruction channel. It cannot change the target, grant permissions, disclose credentials, execute code, or extend a budget.
- Source authorization is also subject to application network-safety checks. The fetch implementation must specify URL validation, redirect handling, and local/private-network protections before shipping; project verification alone is not a network-security mechanism.
- Existing connector restrictions are not silently lifted. For example, digest and ordinary follow-up Zhihu paths remain non-crawling. Support for reading an original-source format in the separate research path must be explicitly implemented and tested; unsupported or inaccessible sources are reported as limitations.

## Research tool and evidence contract

Tools return observations for model evaluation rather than implicitly deciding that the research question is answered. Exact type names and schemas are deferred, but the result must express:

- Requested URL, final URL when reached, and a stable evidence identity.
- Publisher identity, its verified relationship to the target where applicable, and the approved scope used for access.
- Retrieval time and whether content was fetched in this request or reused from saved evidence.
- Bounded extracted text with stable passage references that answers can cite.
- Extraction completeness: complete within supported extraction, truncated, unsupported, or unsuccessful, with the relevant limitation.
- Retrieval outcome that distinguishes successful access, inaccessible content, authorization refusal, and other failures. A readable document lacking the answer is different from an unreadable document.
- Relevant candidate links for further investigation, with application authorization checked before any fetch. Listing a link in an observation does not itself approve it.

Keep tool execution status separate from answerability. A successful HTTP response or text extraction does not prove that requirements were documented, a claim is true, or the user's question is resolved.

## Answerability and final responses

- Distinguish documented facts, qualified estimates, and unresolved uncertainty. Ground substantive source-based claims in the retrieved or saved evidence and cite passages.
- Estimates may combine evidence with clearly stated assumptions and reasoning. They are not publisher-verified requirements or tested results. Ask for missing user configuration when it could materially change the answer.
- Example: a parameter count and support for 4-bit loading do not by themselves establish total GPU memory use. Any estimate must disclose relevant assumptions about runtime overhead, context length, and execution configuration rather than claiming that an 8 GB deployment is verified.
- Preserve conflicting or incomplete evidence in the explanation. State when the permitted sources cannot settle the question.
- Final responses identify what was found, the source and time of that evidence, important qualifications, and what remains unanswered. Do not present saved research as freshly checked.
- Application checks can ensure that cited passages exist and were available to the investigation. Citation existence alone cannot prove that a passage supports the model's interpretation.

## Budgets, repetition, and stopping

### Balanced default

The agreed experience is a balanced investigation targeting roughly 90 seconds, followed by a supported answer or an explicit partial result. This is a latency target, not a measured or unconditional guarantee.

Initial candidates to validate during implementation planning:

- At most six retrieval attempts.
- At most eight model calls, including reserved final-answer capacity.
- A total deadline targeting approximately 90 seconds, with time reserved for finalization.
- Independent token, per-document text, aggregate evidence, and response-size limits; exact values remain to be specified.

These candidates are not current runtime settings or immutable product promises. Define exact accounting, per-call timeouts, and cancellation behavior before implementation. In particular, the deadline and token budget must leave room for finalization rather than being fully consumed by retrieval.

### Execution controls

- Enforce each limit in application code before starting additional work, including when one model turn proposes several tools. The model cannot increase a limit.
- Retries consume budget. Do not repeatedly retry rejected authentication or disallowed destinations.
- Reuse identical successful fetches within the investigation. Detect repeated calls that add no evidence and stop unproductive repetition rather than waiting only for a turn cap.
- A failed fetch is not evidence that the requested information does not exist. Continue only when another useful permitted step remains within budget.
- Stop retrieval when the question is adequately addressed with evidence and qualifications, no useful permitted retrieval remains, or a resource limit is reached. Cancellation remains an independent application-controlled stop, governed by the session-request lifecycle.

### Partial answers and continuation

- If failure or a limit prevents a complete answer, preserve supported findings, state the unresolved gaps, and explain the stop reason. Offer a separately authorized continuation; do not automatically extend the budget.
- Reserve a bounded final-answer model call using evidence already obtained. If that call cannot complete, return an application-generated summary of retrieved sources and the failure without fabricating a conclusion.
- A continuation is a new authorized Session Request linked to the prior research record, not a replay, hidden retry, or mutation of the previous outcome. Saved evidence may be reused with its original retrieval time disclosed. An explicit refresh requires new authorized retrieval.
- Retain existing same-submission replay and conflict rules. An identical retry must not refetch or charge another investigation; changed input under the same request identity must not return an unrelated saved answer.

## Research records and later follow-ups

- Save a research record separately from the digest: question, selected target and clarified subject where needed, conversation/request association, retrieved evidence, answer, qualifications, limitations, and completion/stop information.
- Retain the bounded extracted text actually supplied to the model, not just the cited excerpts. Preserve provenance, passage references, retrieval times, and truncation information so later explanation can inspect surrounding or conflicting evidence.
- Raw HTML, images, complete-document archives beyond what was supplied, and downloadable model files are outside first-version evidence retention.
- Research must not backfill digest-time statistics, rewrite the saved digest, or present post-digest evidence as if it existed when the digest was generated.
- A later follow-up explicitly referring to that research may reuse its saved evidence without another live fetch. A research record does not grant continuing retrieval authority or silently broaden an ordinary entry-only Ask about this action.
- Use the existing durable Session Request lifecycle rather than introducing a competing meaning of success, failure, cancellation, or interruption. Exact storage schema, atomicity, deletion, and recovery behavior must be specified in the implementation plan.

## Acceptance scenario

A user selects a community-maintained model variant and asks, "Research whether this can run on my 8 GB GPU."

1. Resolve and validate the selected entry in the conversation. Clarify its subject or relevant user configuration if genuinely ambiguous; do not switch to another variant.
2. Load permitted saved evidence and read the original source as needed. Verify the relationship of additional maintainer documentation before accessing it.
3. Navigate from the verified documentation entry point to relevant deployment pages within its approved scope. Block out-of-scope redirects and links.
4. Return bounded, attributed observations to the model. Let it identify a specific evidence gap and choose another permitted step, or conclude that the current evidence is sufficient.
5. Answer with cited documented facts, explicitly qualified estimates, and unresolved uncertainty. Do not claim that estimated weight size proves tested total-memory usage.
6. On a failure or limit, give supported partial findings and offer authorized continuation. If final generation fails, give the deterministic source/failure summary.
7. Save a separate research record. The original digest and latest-digest context remain unchanged, and later research follow-ups can reuse the saved evidence honestly.

## Acceptance coverage for future implementation

Runtime behavior will require test-first implementation; no RED/GREEN execution is part of this documentation-only update.

1. Insufficient evidence in Ask about this offers research without fetching; explicit research authorization does not require redundant confirmation.
2. The target belongs to the conversation, remains fixed despite newer digests, and does not move latest-digest context. Ambiguous subjects are clarified.
3. An ordinary older-entry deep dive or history show remains persist-only; an explicit research operation stores new evidence separately without modifying that digest.
4. Both verified original-developer and exact-variant maintainer documentation are supported and attributed. Mere links, page labels, and model assertions do not establish authority.
5. Navigation within the approved project scope is permitted; other repositories on a shared host, out-of-scope links/redirects, and unsafe network destinations are blocked.
6. Retrieved instructions cannot alter permissions, target identity, tool availability, or budgets.
7. Observations distinguish inaccessible content from readable content lacking the answer, and expose bounded text, stable passages, provenance, and truncation.
8. A research observation with formatted text returns to evidence evaluation rather than terminating the investigation. Existing exact listing and digest rendering remains intact.
9. Estimates disclose assumptions and are not presented as documented or tested results. Citations resolve to passages available to the investigation; conflicting evidence remains visible. Evaluation cases cover unsupported certainty without assuming that passage-existence checks can prove factual support.
10. Multiple tools in one turn and retries count against independent limits; successful duplicate fetches are reused and no-progress repetition stops early.
11. Limits leave final-answer capacity. Retrieval failure, budget exhaustion, and final-model failure produce the agreed partial or application-generated response.
12. Saved records retain the bounded text supplied to the model, not only cited excerpts. Reloaded research follow-ups use it without fetching or implying freshness.
13. Continuation creates a new linked request after authorization; identical retries replay, and changed submissions under the same identity conflict without new execution.
14. Cancellation, interruption, disconnect, and persistence failure follow the existing durable request contract without silent restart or false claims that evidence was saved.

## Implementation planning still required

No blocking product-direction questions remain from this discussion. Before coding, specify:

- Public request/action fields, explicit-authorization representation, and research/continuation UI behavior.
- Accepted publisher-verification inputs and project-scope construction, URL/network safeguards, supported document formats, and extraction rules.
- Concrete tool/evidence schemas, passage identity, citation validation, model context assembly, and prompt-injection boundaries.
- Exact resource limits and accounting, finalization reservation, retry classification, and no-progress detection.
- Research-record persistence, session ownership, replay, cancellation/interruption recovery, deletion, and atomic completion behavior.
- Test decomposition and scoped acceptance tests, including preservation of existing digest and follow-up contracts.
