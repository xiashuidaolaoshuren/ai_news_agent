# Hybrid execution and separate records for authorized entry research

Status: accepted (design; research is not implemented)
Date: 2026-10-29

The application already has a predictable digest workflow and a bounded tool-calling loop for open-ended follow-ups. Some tool responses deliberately terminate with exact formatted output. That preserves source-specific listings, but a research question may need the model to inspect a result, identify missing evidence, and choose another permitted step. Separately, silently enriching a saved entry would blur the distinction between historical digest evidence and a later investigation.

## Decision

Keep digest generation and exact structured views as predictable workflows. Use an adaptive model/tool loop for explicitly authorized research about one selected saved entry. The model proposes useful evidence-gathering actions; the application enforces the target, allowed tools, source scopes, budgets, and cancellation. A successful research tool result is evidence to evaluate, not automatic proof of task completion.

Research may read the selected entry's original source and directly linked, verified documentation from the developer or maintainer responsible for the exact project or variant. Once a documentation scope is verified, bounded navigation within that project scope is permitted. Links, redirects, source instructions, and model assertions cannot expand authorization.

Persist the research question, target, bounded evidence supplied to the model, provenance, answer, and limitations in a separate research record linked to the entry and conversation. Preserve the original digest and latest-digest context. Later research follow-ups may reuse that saved evidence, but new retrieval requires authorization. Qualified estimates are allowed when distinguished from documented facts and supported by explicit assumptions.

Stop with supported partial findings and unresolved gaps when evidence, permissions, or execution limits prevent completion. Offer continuation as a new authorized request rather than automatically extending the budget. Reserve final-answer capacity and provide an application-generated source/failure summary if final generation fails.

## Considered options (rejected)

- One model-controlled loop for everything: adds discretionary model steps to operations whose sequence and presentation are already known.
- Fixed retrieve-once-then-answer research: cannot adapt to a useful document revealing another specific evidence gap.
- Silent research during ordinary follow-ups: changes the evidence and retrieval permissions of Ask about this without user authorization.
- Broad web research in the first version: expands discovery, source verification, and evidence-quality requirements beyond the selected entry.
- Store only the answer and cited excerpts: loses surrounding text and potentially contradictory evidence actually available to the model.
- Add research evidence to the original digest: makes historical results mutable and confuses digest-time evidence with post-digest findings.
- Only original-developer documentation: can exclude the relevant maintainer instructions for a community variant.
- Only direct-link fetching: can admit a documentation homepage but prevent reaching its deployment instructions. Trusting an entire shared domain is too broad; use a verified project scope instead.

## Consequences

- This adds a separate research operation; it does not silently change Deep dive, Ask about this, or history show. ADR-0006 and ADR-0015's existing latest-digest-only Hugging Face README exception remains unchanged.
- Research requires evidence-returning tools and an application-enforced allowlist of capabilities/scopes rather than simply exposing the existing connector registry with a stricter prompt.
- Exact formatted listings and terminal digest results retain their existing purpose. Research must not inherit a generic formatted-text short circuit.
- Separate storage and target identity are deliberate boundaries. Continuation is a new linked Session Request; retries and historical digest access retain their existing semantics.
- Citation validation verifies passage availability, not the truth of the model's interpretation. Estimates and unresolved conflicts must remain visible to the user.
- MCP adoption and framework replacement are not required. Concrete interfaces, security checks, storage, and resource accounting remain implementation work.

Details and future acceptance coverage: [Agent loop and entry-bound research design](../superpowers/specs/2026-10-29-agent-loop-and-entry-research-design.md).
