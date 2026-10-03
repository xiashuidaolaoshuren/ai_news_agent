"""Tests for DigestView API DTOs and build_digest_view (Milestone 8A.1 T11)."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_news_agent.models import Digest, DigestEntry, FollowUpAction, NewsItem, SourceKind


def _fixture_dt() -> datetime:
    return datetime(2026, 5, 13, 8, 30, 0, tzinfo=UTC)


def _huggingface_entry(*, source_id: str = "Qwen/Qwen3.8-27B") -> DigestEntry:
    return DigestEntry(
        source_kind=SourceKind.HUGGINGFACE,
        source_id=source_id,
        title="Qwen3.8-27B",
        source_name="Hugging Face",
        source_url=f"https://huggingface.co/{source_id}",
        summary="HF summary.",
        why_it_matters="Why HF.",
        background_knowledge="BG HF.",
        follow_up_action=FollowUpAction.TRY,
    )


def _juya_entry() -> DigestEntry:
    return DigestEntry(
        source_kind=SourceKind.JUYA,
        source_id="issue-2026-05-13",
        title="Juya bulletin",
        source_name="Juya",
        source_url="https://daily.juya.uk/2026/05/13",
        summary="Juya summary.",
        why_it_matters="Why Juya.",
        background_knowledge="BG Juya.",
        follow_up_action=FollowUpAction.READ,
    )


def _github_entry() -> DigestEntry:
    return DigestEntry(
        source_kind=SourceKind.GITHUB,
        source_id="repo/ai-tool",
        title="Neural nets primer",
        source_name="GitHub",
        source_url="https://github.com/repo/ai-tool",
        summary="A short summary.",
        why_it_matters="It matters to us.",
        background_knowledge="Foundational RL.",
        follow_up_action=FollowUpAction.READ,
        confidence_caveat="Limited metadata.",
    )


def test_digest_view_dto_surface_importable_and_round_trips_generic_entry() -> None:
    from ai_news_agent.api.schemas.digests import DigestEntryView, DigestView

    entry = _github_entry()
    view = DigestView(
        generated_at=_fixture_dt(),
        timeframe="last_7_days",
        topics=["AI agents"],
        entries=[
            DigestEntryView(
                source_kind=entry.source_kind,
                source_id=entry.source_id,
                title=entry.title,
                source_name=entry.source_name,
                source_url=entry.source_url,
                summary=entry.summary,
                why_it_matters=entry.why_it_matters,
                background_knowledge=entry.background_knowledge,
                follow_up_action=entry.follow_up_action,
                confidence_caveat=entry.confidence_caveat,
                display_rank=1,
            )
        ],
    )
    payload = view.model_dump()
    assert payload["generated_at"] == _fixture_dt()
    assert payload["timeframe"] == "last_7_days"
    assert payload["topics"] == ["AI agents"]
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["source_kind"] == "github"
    assert payload["entries"][0]["display_rank"] == 1
    assert payload["entries"][0]["title"] == "Neural nets primer"


def test_huggingface_entry_view_exposes_family_metrics_and_variants() -> None:
    from ai_news_agent.api.schemas.digests import FamilyVariant, HuggingFaceDigestEntryView
    from ai_news_agent.services.digest_views import extract_huggingface_evidence

    evidence = {
        "trending_score": 42.5,
        "downloads_30d": 1000,
        "likes": 50,
        "pipeline_tag": "text-generation",
        "family_variants": [
            {
                "source_id": "Someone/Qwen3.8-27B-GGUF",
                "title": "Qwen3.8-27B-GGUF",
                "url": "https://huggingface.co/Someone/Qwen3.8-27B-GGUF",
                "downloads_30d": 200,
                "likes": 10,
                "model_card_live_fetched": True,
            }
        ],
        "base_model": "Qwen/Qwen3.8-27B",
    }
    hf_fields = extract_huggingface_evidence(evidence)
    view = HuggingFaceDigestEntryView(
        source_id="Qwen/Qwen3.8-27B",
        title="Qwen3.8-27B",
        source_name="Hugging Face",
        source_url="https://huggingface.co/Qwen/Qwen3.8-27B",
        summary="HF summary.",
        why_it_matters="Why HF.",
        background_knowledge="BG HF.",
        follow_up_action=FollowUpAction.TRY,
        display_rank=1,
        **hf_fields,
    )
    assert view.trending_score == 42.5
    assert view.downloads_30d == 1000
    assert view.likes == 50
    assert view.pipeline_tag == "text-generation"
    assert view.family_variants == [
        FamilyVariant(
            source_id="Someone/Qwen3.8-27B-GGUF",
            title="Qwen3.8-27B-GGUF",
            url="https://huggingface.co/Someone/Qwen3.8-27B-GGUF",
            downloads_30d=200,
            likes=10,
        )
    ]


def test_build_digest_view_maps_common_fields_and_display_rank() -> None:
    from ai_news_agent.api.schemas.digests import DigestEntryView, build_digest_view

    github = _github_entry()
    juya = _juya_entry()
    digest = Digest(
        generated_at=_fixture_dt(),
        timeframe="last_7_days",
        topics=["AI agents"],
        entries=[github, juya],
    )

    view = build_digest_view(digest)

    assert view.generated_at == _fixture_dt()
    assert view.timeframe == "last_7_days"
    assert view.topics == ["AI agents"]
    assert len(view.entries) == 2
    assert isinstance(view.entries[0], DigestEntryView)
    assert view.entries[0].display_rank == 1
    assert view.entries[0].source_kind == SourceKind.GITHUB
    assert view.entries[0].title == github.title
    assert view.entries[0].summary == github.summary
    assert view.entries[1].display_rank == 2
    assert view.entries[1].source_kind == SourceKind.JUYA
    assert view.entries[1].title == juya.title


def test_build_digest_view_wires_huggingface_evidence_via_news_item_lookup() -> None:
    from ai_news_agent.api.schemas.digests import (
        DigestEntryView,
        HuggingFaceDigestEntryView,
        build_digest_view,
    )

    github = _github_entry()
    hf = _huggingface_entry()
    digest = Digest(
        generated_at=_fixture_dt(),
        entries=[github, hf],
    )
    news_items = [
        NewsItem(
            source=SourceKind.GITHUB,
            source_id=github.source_id,
            url=github.source_url,
            title=github.title,
            source_evidence={"query_lens": "should-not-leak"},
        ),
        NewsItem(
            source=SourceKind.HUGGINGFACE,
            source_id=hf.source_id,
            url=hf.source_url,
            title=hf.title,
            source_evidence={
                "trending_score": 99.0,
                "downloads_30d": 5000,
                "likes": 120,
                "pipeline_tag": "text-generation",
                "family_variants": [
                    {
                        "source_id": "Someone/Qwen3.8-27B-GGUF",
                        "title": "Qwen3.8-27B-GGUF",
                    }
                ],
                "base_model": "Qwen/Qwen3.8-27B",
            },
        ),
    ]

    view = build_digest_view(digest, news_items=news_items)

    assert isinstance(view.entries[0], DigestEntryView)
    assert not isinstance(view.entries[0], HuggingFaceDigestEntryView)
    hf_view = view.entries[1]
    assert isinstance(hf_view, HuggingFaceDigestEntryView)
    assert hf_view.display_rank == 2
    assert hf_view.trending_score == 99.0
    assert hf_view.downloads_30d == 5000
    assert hf_view.likes == 120
    assert hf_view.pipeline_tag == "text-generation"
    assert len(hf_view.family_variants) == 1
    assert hf_view.family_variants[0].source_id == "Someone/Qwen3.8-27B-GGUF"


def test_build_digest_view_does_not_leak_raw_source_evidence_keys() -> None:
    from ai_news_agent.api.schemas.digests import build_digest_view

    hf = _huggingface_entry()
    digest = Digest(generated_at=_fixture_dt(), entries=[hf])
    news_items = [
        NewsItem(
            source=SourceKind.HUGGINGFACE,
            source_id=hf.source_id,
            url=hf.source_url,
            title=hf.title,
            source_evidence={
                "trending_score": 10.0,
                "downloads_30d": 100,
                "likes": 5,
                "pipeline_tag": "text-generation",
                "family_variants": [
                    {
                        "source_id": "Someone/Qwen3.8-27B-GGUF",
                        "title": "Qwen3.8-27B-GGUF",
                        "model_card_live_fetched": True,
                    }
                ],
                "base_model": "Qwen/Qwen3.8-27B",
                "model_card_live_fetched": True,
                "source_label": "hub-trending",
                "query_lens": "ignored",
            },
        )
    ]

    payload = build_digest_view(digest, news_items=news_items).model_dump(mode="json")
    dumped = str(payload)
    for forbidden in (
        "base_model",
        "model_card_live_fetched",
        "source_label",
        "query_lens",
        "source_evidence",
    ):
        assert forbidden not in dumped


def test_build_digest_view_huggingface_entry_without_matching_news_item() -> None:
    from ai_news_agent.api.schemas.digests import HuggingFaceDigestEntryView, build_digest_view

    hf = _huggingface_entry()
    digest = Digest(generated_at=_fixture_dt(), entries=[hf])

    view = build_digest_view(digest, news_items=[])

    entry = view.entries[0]
    assert isinstance(entry, HuggingFaceDigestEntryView)
    assert entry.trending_score is None
    assert entry.downloads_30d is None
    assert entry.likes is None
    assert entry.pipeline_tag is None
    assert entry.family_variants == []
