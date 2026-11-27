"""Research observation contract (plan R3)."""

from __future__ import annotations

import pytest

from ai_news_agent.tools.schemas import ToolObservationStatus


def test_hand_built_observation_retains_ordered_passages_and_envelope() -> None:
    from ai_news_agent.research_evidence import ResearchObservation, ResearchPassage

    obs = ResearchObservation(
        status=ToolObservationStatus.OK,
        summary="Fetched the README section.",
        requested_url="https://github.com/acme/widget",
        evidence_id="ev-acme-readme-1",
        retrieval_outcome="retrieved",
        extraction_completeness="complete",
        passages=[
            ResearchPassage(passage_id="p1", text="First paragraph."),
            ResearchPassage(passage_id="p2", text="Second paragraph."),
        ],
        fresh=True,
    )

    assert obs.status == ToolObservationStatus.OK
    assert obs.summary == "Fetched the README section."
    assert obs.evidence_id == "ev-acme-readme-1"
    assert [p.passage_id for p in obs.passages] == ["p1", "p2"]
    assert [p.text for p in obs.passages] == ["First paragraph.", "Second paragraph."]


def test_retrieval_outcome_is_independent_of_execution_and_answerability() -> None:
    from pydantic import ValidationError

    from ai_news_agent.research_evidence import ResearchObservation

    readable_no_answer = ResearchObservation(
        status=ToolObservationStatus.OK,
        summary="Read the install page.",
        requested_url="https://acme.example/docs/install",
        evidence_id="ev-1",
        retrieval_outcome="retrieved",
        extraction_completeness="complete",
        caveats=["No GPU memory figures on this page."],
    )
    assert readable_no_answer.retrieval_outcome == "retrieved"
    assert readable_no_answer.status == ToolObservationStatus.OK

    for outcome in ("inaccessible", "refused", "failed"):
        limited = ResearchObservation(
            status=ToolObservationStatus.ERROR,
            summary="Could not use this source.",
            requested_url="https://acme.example/missing",
            evidence_id=f"ev-{outcome}",
            retrieval_outcome=outcome,
            extraction_completeness="unsuccessful",
        )
        assert limited.retrieval_outcome == outcome

    with pytest.raises(ValidationError):
        ResearchObservation(
            status=ToolObservationStatus.OK,
            summary="Bad outcome label.",
            requested_url="https://acme.example/x",
            evidence_id="ev-bad",
            retrieval_outcome="blocked",  # type: ignore[arg-type]
            extraction_completeness="complete",
        )


def test_extraction_limits_stay_visible_with_caveats() -> None:
    from pydantic import ValidationError

    from ai_news_agent.research_evidence import ResearchObservation, ResearchPassage

    truncated = ResearchObservation(
        status=ToolObservationStatus.OK,
        summary="Partial body returned.",
        requested_url="https://acme.example/huge",
        evidence_id="ev-trunc",
        retrieval_outcome="retrieved",
        extraction_completeness="truncated",
        caveats=["Body exceeded the extraction cap."],
        passages=[ResearchPassage(passage_id="p1", text="Visible head of document.")],
    )
    assert truncated.extraction_completeness == "truncated"
    assert "extraction cap" in truncated.caveats[0]
    assert truncated.passages[0].text == "Visible head of document."

    for completeness in ("unsupported", "unsuccessful"):
        obs = ResearchObservation(
            status=ToolObservationStatus.ERROR,
            summary="Extraction failed.",
            requested_url="https://acme.example/bin",
            evidence_id=f"ev-{completeness}",
            retrieval_outcome="retrieved",
            extraction_completeness=completeness,
        )
        assert obs.extraction_completeness != "complete"

    with pytest.raises(ValidationError):
        ResearchObservation(
            status=ToolObservationStatus.OK,
            summary="Bad completeness label.",
            requested_url="https://acme.example/x",
            evidence_id="ev-bad-c",
            retrieval_outcome="retrieved",
            extraction_completeness="partial",  # type: ignore[arg-type]
        )


def test_provenance_variants_for_project_original_and_refusal() -> None:
    from ai_news_agent.models import SourceKind
    from ai_news_agent.research_evidence import ResearchObservation
    from ai_news_agent.research_scope import ApprovedResearchScope

    scope = ApprovedResearchScope(
        source_kind=SourceKind.HUGGINGFACE,
        source_id="acme/widget-instruct",
        subject_id="acme/widget-instruct",
        publisher="Acme community maintainers",
        relationship="variant_maintainer",
        entry_point="https://acme.example/docs/widget/install",
        project_path="/docs/widget",
    )
    with_grant = ResearchObservation(
        status=ToolObservationStatus.OK,
        summary="Read maintainer docs.",
        requested_url=scope.entry_point,
        final_url=scope.entry_point,
        evidence_id="ev-maint",
        retrieval_outcome="retrieved",
        extraction_completeness="complete",
        publisher=scope.publisher,
        relationship=scope.relationship,
        approved_scope=scope,
    )
    assert with_grant.approved_scope is scope
    assert with_grant.relationship == "variant_maintainer"

    original = ResearchObservation(
        status=ToolObservationStatus.OK,
        summary="Read saved page.",
        requested_url="https://github.com/acme/widget",
        final_url="https://github.com/acme/widget",
        evidence_id="ev-orig",
        retrieval_outcome="retrieved",
        extraction_completeness="complete",
        publisher="github.com",
        relationship="original_source",
        approved_scope=None,
    )
    assert original.approved_scope is None

    refused = ResearchObservation(
        status=ToolObservationStatus.ERROR,
        summary="Destination refused.",
        requested_url="https://169.254.169.254/latest/meta-data",
        evidence_id="ev-refused",
        retrieval_outcome="refused",
        extraction_completeness="unsuccessful",
        final_url=None,
        publisher=None,
        relationship=None,
        approved_scope=None,
        retrieved_at=None,
    )
    assert refused.final_url is None
    assert refused.publisher is None


def test_candidate_links_are_plain_urls_not_grants() -> None:
    from pydantic import ValidationError

    from ai_news_agent.research_evidence import ResearchObservation

    obs = ResearchObservation(
        status=ToolObservationStatus.OK,
        summary="Found outbound links.",
        requested_url="https://acme.example/docs/widget",
        evidence_id="ev-links",
        retrieval_outcome="retrieved",
        extraction_completeness="complete",
        candidate_links=[
            "https://acme.example/docs/widget/gpu",
            "https://other.example/unapproved",
        ],
    )
    assert obs.candidate_links == [
        "https://acme.example/docs/widget/gpu",
        "https://other.example/unapproved",
    ]

    with pytest.raises(ValidationError):
        ResearchObservation(
            status=ToolObservationStatus.OK,
            summary="Wrong candidate shape.",
            requested_url="https://acme.example/x",
            evidence_id="ev-bad-links",
            retrieval_outcome="retrieved",
            extraction_completeness="complete",
            candidate_links=[{"url": "https://acme.example/y", "approved": True}],  # type: ignore[list-item]
        )


def test_freshness_and_json_round_trip_preserve_reuse_metadata() -> None:
    from datetime import UTC, datetime

    from ai_news_agent.models import SourceKind
    from ai_news_agent.research_evidence import ResearchObservation, ResearchPassage
    from ai_news_agent.research_scope import ApprovedResearchScope

    when = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    scope = ApprovedResearchScope(
        source_kind=SourceKind.GITHUB,
        source_id="acme/widget",
        subject_id="acme/widget",
        publisher="Acme developer docs",
        relationship="original_developer",
        entry_point="https://acme.example/docs/widget/install",
        project_path="/docs/widget",
    )
    fresh = ResearchObservation(
        status=ToolObservationStatus.OK,
        summary="Fresh fetch.",
        requested_url=scope.entry_point,
        evidence_id="ev-fresh",
        retrieval_outcome="retrieved",
        extraction_completeness="complete",
        approved_scope=scope,
        retrieved_at=when,
        fresh=True,
        passages=[ResearchPassage(passage_id="p1", text="Requirement: 16 GB VRAM.")],
    )
    payload = fresh.model_dump(mode="json")
    restored = ResearchObservation.model_validate(payload)
    assert restored.fresh is True
    assert restored.retrieved_at == when
    assert restored.passages[0].text == "Requirement: 16 GB VRAM."
    assert restored.approved_scope == scope

    reused = fresh.model_copy(update={"fresh": False, "summary": "From saved evidence."})
    round_trip = ResearchObservation.model_validate(reused.model_dump(mode="json"))
    assert round_trip.fresh is False
    assert round_trip.retrieved_at == when
    assert round_trip.evidence_id == "ev-fresh"
    assert [p.passage_id for p in round_trip.passages] == ["p1"]
