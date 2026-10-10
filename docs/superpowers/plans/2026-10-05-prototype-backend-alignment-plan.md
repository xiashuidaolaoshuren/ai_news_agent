# Implementation Plan: Prototype Backend Alignment

**Spec:** `docs/superpowers/specs/2026-10-05-prototype-backend-alignment-design.md`  
**ADR:** `docs/adr/0009-juya-story-mode-and-digest-presentation-metadata.md`  
**Created:** 2026-10-05  
**Follow-on to:** Milestone 8A.1 (T11/T14/T16 complete)

## Summary

Extend connector evidence collection and `DigestView` projection for prototype presentation metadata. Add opt-in Juya story items with per-message web control. No SQLite migration.

**TDD suitable:** yes

## Subtasks (execution order)

| ID | Behavior | Primary files |
|----|----------|---------------|
| B1 | GitHub owner mapping | `connectors/github.py`, `tests/test_connectors_github.py` |
| B2 | HF owner enrichment | `connectors/huggingface.py`, `tests/test_connectors_huggingface.py` |
| B3 | GitHub preview og:image | `connectors/github.py`, `tests/test_connectors_github.py` |
| B4 | Juya issue metadata | `juya_content.py`, `connectors/juya.py`, `tests/test_juya_content.py` |
| B5 | Juya story collection | `connectors/juya.py`, `tests/test_connectors_juya.py` |
| B6 | Story dedupe/ranking | `ranking.py`, `tests/test_ranking.py` |
| B7 | Story follow-up | `juya_followup.py`, `followup_structured.py`, `tests/test_juya_followup.py` |
| B8 | DigestView projection | `api/schemas/digests.py`, `services/digest_views.py`, `tests/test_digest_views.py` |
| B9 | Web opt-in plumbing | `request.py`, `api/schemas/sessions.py`, session/chat services, `tests/test_api_sessions.py` |
| B10 | History show entry | `api/schemas/history.py`, `history_search.py`, `tests/test_api_history.py` |

## Verification

```bash
uv run pytest tests/test_connectors_github.py tests/test_connectors_huggingface.py tests/test_connectors_juya.py tests/test_juya_content.py tests/test_ranking.py tests/test_juya_followup.py tests/test_digest_views.py tests/test_api_sessions.py tests/test_api_history.py -q
uv run pytest -q
```

## Plan changelog

| Date | Change |
|------|--------|
| 2026-10-05 | Initial follow-on plan after OpenDesign prototype review |
