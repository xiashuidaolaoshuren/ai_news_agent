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
    from ai_news_agent.api.schemas.digests import GitHubDigestEntryView, DigestView

    entry = _github_entry()
    view = DigestView(
        generated_at=_fixture_dt(),
        timeframe="last_7_days",
        topics=["AI agents"],
        entries=[
            GitHubDigestEntryView(
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


def test_extract_huggingface_evidence_projects_base_model() -> None:
    from ai_news_agent.services.digest_views import extract_huggingface_evidence

    assert (
        extract_huggingface_evidence({"base_model": "Qwen/Qwen3.8-27B"})["base_model"]
        == "Qwen/Qwen3.8-27B"
    )
    assert extract_huggingface_evidence({})["base_model"] is None
    assert extract_huggingface_evidence({"base_model": ""})["base_model"] is None
    assert extract_huggingface_evidence({"base_model": "   "})["base_model"] is None

    assert (
        extract_huggingface_evidence(
            {
                "base_model": "Qwen/Qwen3.8-27B",
                "family_variants": [
                    {
                        "source_id": "Someone/Qwen3.8-27B-GGUF",
                        "title": "Qwen3.8-27B-GGUF",
                        "base_model": "Other/Model",
                    }
                ],
            }
        )["base_model"]
        == "Qwen/Qwen3.8-27B"
    )
    assert (
        extract_huggingface_evidence(
            {
                "family_variants": [
                    {
                        "source_id": "Someone/Qwen3.8-27B-GGUF",
                        "title": "Qwen3.8-27B-GGUF",
                        "base_model": "Other/Model",
                    }
                ]
            }
        )["base_model"]
        is None
    )


def test_build_digest_view_maps_common_fields_and_display_rank() -> None:
    from ai_news_agent.api.schemas.digests import (
        GitHubDigestEntryView,
        JuyaDigestEntryView,
        build_digest_view,
    )

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
    assert isinstance(view.entries[0], GitHubDigestEntryView)
    assert view.entries[0].display_rank == 1
    assert view.entries[0].source_kind == SourceKind.GITHUB
    assert view.entries[0].title == github.title
    assert view.entries[0].summary == github.summary
    assert isinstance(view.entries[1], JuyaDigestEntryView)
    assert view.entries[1].display_rank == 2
    assert view.entries[1].source_kind == SourceKind.JUYA
    assert view.entries[1].title == juya.title
    # A GitHub entry without matching evidence keeps a null daily figure.
    assert view.entries[0].stars_today is None


def test_build_digest_view_wires_huggingface_evidence_via_news_item_lookup() -> None:
    from ai_news_agent.api.schemas.digests import (
        GitHubDigestEntryView,
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

    assert isinstance(view.entries[0], GitHubDigestEntryView)
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


def test_build_digest_view_projects_huggingface_base_model() -> None:
    from ai_news_agent.api.schemas.digests import (
        HuggingFaceDigestEntryView,
        build_digest_view,
    )

    hf = _huggingface_entry()
    digest = Digest(generated_at=_fixture_dt(), entries=[hf])
    news_items = [
        NewsItem(
            source=SourceKind.HUGGINGFACE,
            source_id=hf.source_id,
            url=hf.source_url,
            title=hf.title,
            source_evidence={
                "base_model": "Qwen/Qwen3.8-27B",
                "family_variants": [
                    {
                        "source_id": "Someone/Qwen3.8-27B-GGUF",
                        "title": "Qwen3.8-27B-GGUF",
                        "base_model": "Other/Model",
                    }
                ],
            },
        )
    ]

    view = build_digest_view(digest, news_items=news_items)
    entry = view.entries[0]
    assert isinstance(entry, HuggingFaceDigestEntryView)
    assert entry.base_model == "Qwen/Qwen3.8-27B"

    blank = NewsItem(
        source=SourceKind.HUGGINGFACE,
        source_id=hf.source_id,
        url=hf.source_url,
        title=hf.title,
        source_evidence={"base_model": "   "},
    )
    blank_view = build_digest_view(digest, news_items=[blank])
    assert blank_view.entries[0].base_model is None


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
        "model_card_live_fetched",
        "source_label",
        "query_lens",
        "source_evidence",
    ):
        assert forbidden not in dumped


def test_build_digest_view_github_entry_projects_owner_and_preview() -> None:
    from ai_news_agent.api.schemas.digests import GitHubDigestEntryView, build_digest_view

    github = _github_entry()
    digest = Digest(generated_at=_fixture_dt(), entries=[github])
    news_items = [
        NewsItem(
            source=SourceKind.GITHUB,
            source_id=github.source_id,
            url=github.source_url,
            title=github.title,
            stars_or_views=1280,
            language="Python",
            source_evidence={
                "owner_name": "NVIDIA",
                "owner_profile_url": "https://github.com/NVIDIA",
                "owner_avatar_url": "https://avatars.githubusercontent.com/u/1",
                "owner_type": "organisation",
                "preview_image_url": "https://opengraph.githubassets.com/1/repo.png",
            },
        )
    ]

    view = build_digest_view(digest, news_items=news_items)
    entry = view.entries[0]
    assert isinstance(entry, GitHubDigestEntryView)
    assert entry.owner is not None
    assert entry.owner.name == "NVIDIA"
    assert entry.owner.type == "organisation"
    assert entry.preview_image_url.startswith("https://")
    assert entry.stars == 1280
    assert entry.language == "Python"


def test_extract_github_evidence_projects_stars_today() -> None:
    from ai_news_agent.services.digest_views import extract_github_evidence

    assert extract_github_evidence({"stars_today": 1234}, None)["stars_today"] == 1234
    assert extract_github_evidence({"stars_today": 0}, None)["stars_today"] == 0
    assert extract_github_evidence({}, None)["stars_today"] is None
    assert extract_github_evidence({"stars_today": True}, None)["stars_today"] is None
    assert extract_github_evidence({"stars_today": "1,234"}, None)["stars_today"] is None


def test_build_digest_view_projects_github_stars_today() -> None:
    from ai_news_agent.api.schemas.digests import GitHubDigestEntryView, build_digest_view

    github = _github_entry()
    digest = Digest(generated_at=_fixture_dt(), entries=[github])
    news_items = [
        NewsItem(
            source=SourceKind.GITHUB,
            source_id=github.source_id,
            url=github.source_url,
            title=github.title,
            stars_or_views=1280,
            language="Python",
            source_evidence={"owner_name": "demo-org", "stars_today": 1234},
        )
    ]

    view = build_digest_view(digest, news_items=news_items)
    entry = view.entries[0]
    assert isinstance(entry, GitHubDigestEntryView)
    assert entry.stars_today == 1234
    assert entry.stars == 1280
    assert entry.language == "Python"


def test_build_digest_view_juya_issue_metadata_and_legacy_nulls() -> None:
    from ai_news_agent.api.schemas.digests import JuyaDigestEntryView, build_digest_view

    juya = _juya_entry()
    digest = Digest(generated_at=_fixture_dt(), entries=[juya])
    enriched = NewsItem(
        source=SourceKind.JUYA,
        source_id=juya.source_id,
        url=juya.source_url,
        title=juya.title,
        source_evidence={
            "juya_item_type": "issue",
            "issue_id": juya.source_id,
            "issue_date": "2026-05-13",
            "issue_url": juya.source_url,
            "issue_cover_url": "https://assets.juya.uk/cover/2026-05-13.png",
            "issue_lead_title": "Lead headline",
        },
    )
    legacy = Digest(
        generated_at=_fixture_dt(),
        entries=[_github_entry()],
    )

    view = build_digest_view(digest, news_items=[enriched])
    entry = view.entries[0]
    assert isinstance(entry, JuyaDigestEntryView)
    assert entry.item_type == "issue"
    assert entry.issue is not None
    assert entry.issue.cover_url.startswith("https://assets.juya.uk/cover/")
    assert entry.issue.lead_title == "Lead headline"
    assert entry.story is None

    legacy_view = build_digest_view(legacy, news_items=[])
    assert legacy_view.entries[0].source_kind == SourceKind.GITHUB


def test_build_digest_view_juya_story_entry() -> None:
    from ai_news_agent.api.schemas.digests import JuyaDigestEntryView, build_digest_view

    entry = DigestEntry(
        source_kind=SourceKind.JUYA,
        source_id="juya-story-issue-1",
        title="DeepSeek vision",
        source_name="Juya",
        source_url="https://daily.juya.uk/2026/05/13/#story-1",
        summary="Story summary",
        why_it_matters="Why",
        background_knowledge="",
        follow_up_action=FollowUpAction.READ,
    )
    digest = Digest(generated_at=_fixture_dt(), entries=[entry])
    news_items = [
        NewsItem(
            source=SourceKind.JUYA,
            source_id=entry.source_id,
            url=entry.source_url,
            title=entry.title,
            source_evidence={
                "juya_item_type": "story",
                "issue_id": "issue-2026-05-13",
                "issue_date": "2026-05-13",
                "issue_url": "https://daily.juya.uk/2026/05/13",
                "story_number": 1,
                "story_section": "要闻",
                "story_original_url": "https://www.deepseek.com",
            },
        )
    ]
    view = build_digest_view(digest, news_items=news_items)
    juya_view = view.entries[0]
    assert isinstance(juya_view, JuyaDigestEntryView)
    assert juya_view.item_type == "story"
    assert juya_view.story is not None
    assert juya_view.story.number == 1
    assert juya_view.story.original_url == "https://www.deepseek.com"


def test_build_digest_view_recovers_saved_juya_story_text_and_metadata() -> None:
    from ai_news_agent.api.schemas.digests import JuyaDigestEntryView, build_digest_view

    entry = DigestEntry(
        source_kind=SourceKind.JUYA,
        source_id="juya-story-issue-2",
        title="[有关部门拟增列AI技术](https://example.com/export-control)",
        source_name="Juya",
        source_url="https://daily.juya.uk/issues/2026-10-17/#story-1",
        summary=(
            "Wait — I must output only the JSON object. "
            '<｜end▁of▁thinking｜>{"summary": "有关部门公开征求意见，拟增列 23 项 AI 技术。",'
            ' "why_it_matters": "出口规则直接影响模型出海。", "background_knowledge": "目录定期修订。"}'
        ),
        why_it_matters="",
        background_knowledge="",
        follow_up_action=FollowUpAction.READ,
    )
    digest = Digest(generated_at=_fixture_dt(), entries=[entry])
    news_items = [
        NewsItem(
            source=SourceKind.JUYA,
            source_id=entry.source_id,
            url=entry.source_url,
            title=entry.title,
            source_evidence={
                "juya_item_type": "story",
                "issue_id": "issue-2026-10-17",
                "issue_date": "2026-10-17",
                "issue_url": "https://daily.juya.uk/issues/2026-10-17",
                "issue_lead_title": (
                    "**视频版**：[哔哩哔哩](https://www.bilibili.com/video/BV15pJY6KE32)"
                    " ｜ [YouTube](https://www.youtube.com/watch?v=6VXBmYc0Dc8)"
                ),
                "story_number": 1,
                "story_section": "要闻",
                "story_original_url": "https://assets.juya.uk/imagehub/m001.png",
            },
        )
    ]

    view = build_digest_view(digest, news_items=news_items)
    juya_view = view.entries[0]

    assert isinstance(juya_view, JuyaDigestEntryView)
    assert juya_view.title == "有关部门拟增列AI技术"
    assert juya_view.summary == "有关部门公开征求意见，拟增列 23 项 AI 技术。"
    assert juya_view.why_it_matters == "出口规则直接影响模型出海。"
    assert juya_view.background_knowledge == "目录定期修订。"
    assert juya_view.issue is not None
    assert juya_view.issue.lead_title is None
    assert juya_view.story is not None
    assert juya_view.story.original_url == "https://example.com/export-control"


def test_build_digest_view_falls_back_to_headline_when_saved_summary_unusable() -> None:
    from ai_news_agent.api.schemas.digests import build_digest_view

    entry = DigestEntry(
        source_kind=SourceKind.JUYA,
        source_id="juya-story-issue-3",
        title="DeepSeek 新增搜索 API",
        source_name="Juya",
        source_url="https://daily.juya.uk/issues/2026-10-17/#story-2",
        summary='{"summary": "截断的摘要',
        why_it_matters="",
        background_knowledge="",
        follow_up_action=FollowUpAction.READ,
    )
    digest = Digest(generated_at=_fixture_dt(), entries=[entry])

    view = build_digest_view(digest, news_items=[])
    juya_view = view.entries[0]

    assert juya_view.summary == ""
    assert juya_view.confidence_caveat == "原摘要无法恢复，仅显示标题。"


def test_build_digest_view_rejects_image_original_url() -> None:
    from ai_news_agent.api.schemas.digests import build_digest_view

    entry = DigestEntry(
        source_kind=SourceKind.JUYA,
        source_id="juya-story-issue-4",
        title="Plain headline",
        source_name="Juya",
        source_url="https://daily.juya.uk/issues/2026-10-17/#story-3",
        summary="Plain summary.",
        why_it_matters="Why.",
        background_knowledge="",
        follow_up_action=FollowUpAction.READ,
    )
    digest = Digest(generated_at=_fixture_dt(), entries=[entry])
    news_items = [
        NewsItem(
            source=SourceKind.JUYA,
            source_id=entry.source_id,
            url=entry.source_url,
            title=entry.title,
            source_evidence={
                "juya_item_type": "story",
                "issue_id": "issue-2026-10-17",
                "story_number": 3,
                "story_original_url": "https://assets.juya.uk/imagehub/m001.png",
            },
        )
    ]

    juya_view = build_digest_view(digest, news_items=news_items).entries[0]

    assert juya_view.story is not None
    assert juya_view.story.original_url is None


def test_build_digest_view_huggingface_entry_without_matching_news_item() -> None:
    from ai_news_agent.api.schemas.digests import HuggingFaceDigestEntryView, build_digest_view

    hf = _huggingface_entry()
    digest = Digest(generated_at=_fixture_dt(), entries=[hf])

    view = build_digest_view(digest, news_items=[])

    entry = view.entries[0]
    assert isinstance(entry, HuggingFaceDigestEntryView)
    assert entry.base_model is None
    assert entry.trending_score is None
    assert entry.downloads_30d is None
    assert entry.likes is None
    assert entry.pipeline_tag is None
    assert entry.family_variants == []

def test_build_digest_view_related_display_ranks_same_hf_family() -> None:
    from ai_news_agent.api.schemas.digests import (
        GitHubDigestEntryView,
        HuggingFaceDigestEntryView,
        build_digest_view,
    )
    from ai_news_agent.models import ConfidenceLevel, NewsItem
    from ai_news_agent.services.digest_views import build_digest_view_payload

    base = "Qwen/Qwen3.8-27B"
    hf_a = _huggingface_entry(source_id=f"{base}-A").model_copy(update={"title": "Qwen A"})
    hf_b = _huggingface_entry(source_id=f"{base}-B").model_copy(update={"title": "Qwen B"})
    hf_other = _huggingface_entry(source_id="Other/Model").model_copy(
        update={"title": "Other model"}
    )
    gh = _github_entry()
    digest = Digest(
        generated_at=_fixture_dt(),
        entries=[hf_a, hf_b, hf_other, gh],
    )
    news_items = [
        NewsItem(
            source=SourceKind.HUGGINGFACE,
            source_id=hf_a.source_id,
            url=hf_a.source_url,
            title=hf_a.title,
            collected_at=_fixture_dt(),
            content_confidence=ConfidenceLevel.HIGH,
            source_evidence={"base_model": base},
        ),
        NewsItem(
            source=SourceKind.HUGGINGFACE,
            source_id=hf_b.source_id,
            url=hf_b.source_url,
            title=hf_b.title,
            collected_at=_fixture_dt(),
            content_confidence=ConfidenceLevel.HIGH,
            source_evidence={"base_model": base},
        ),
        NewsItem(
            source=SourceKind.HUGGINGFACE,
            source_id=hf_other.source_id,
            url=hf_other.source_url,
            title=hf_other.title,
            collected_at=_fixture_dt(),
            content_confidence=ConfidenceLevel.HIGH,
            source_evidence={"base_model": "Other/Model"},
        ),
        NewsItem(
            source=SourceKind.GITHUB,
            source_id=gh.source_id,
            url=gh.source_url,
            title=gh.title,
            collected_at=_fixture_dt(),
        ),
    ]

    payload = build_digest_view_payload(digest, news_items=news_items)
    assert payload["entries"][0]["related_display_ranks"] == [2]
    assert payload["entries"][1]["related_display_ranks"] == [1]

    view = build_digest_view(digest, news_items=news_items)
    assert isinstance(view.entries[0], HuggingFaceDigestEntryView)
    assert view.entries[0].related_display_ranks == [2]
    assert view.entries[1].related_display_ranks == [1]
    assert isinstance(view.entries[2], HuggingFaceDigestEntryView)
    assert view.entries[2].related_display_ranks == []
    assert isinstance(view.entries[3], GitHubDigestEntryView)
    assert "related_display_ranks" not in view.entries[3].model_dump()


def test_build_digest_view_payload_exposes_entry_output_language() -> None:
    from ai_news_agent.services.digest_views import build_digest_view_payload

    entry = _github_entry().model_copy(update={"language": "zh-CN"})
    digest = Digest(
        generated_at=_fixture_dt(),
        entries=[entry],
    )
    payload = build_digest_view_payload(digest)
    assert payload["entries"][0]["output_language"] == "zh-CN"

    legacy = _github_entry()
    legacy_digest = Digest(generated_at=_fixture_dt(), entries=[legacy])
    legacy_payload = build_digest_view_payload(legacy_digest)
    assert legacy_payload["entries"][0]["output_language"] is None


def _openrouter_entry() -> DigestEntry:
    return DigestEntry(
        source_kind=SourceKind.OPENROUTER,
        source_id="openai/gpt-4o",
        title="GPT-4o",
        source_name="OpenRouter",
        source_url="https://openrouter.ai/openai/gpt-4o",
        summary="OpenRouter summary.",
        why_it_matters="Why OpenRouter.",
        background_knowledge="BG.",
        follow_up_action=FollowUpAction.TRY,
    )


def test_build_digest_view_wires_openrouter_evidence_via_news_item_lookup() -> None:
    from ai_news_agent.api.schemas.digests import OpenRouterDigestEntryView, build_digest_view

    or_entry = _openrouter_entry()
    digest = Digest(generated_at=_fixture_dt(), entries=[or_entry])
    news_items = [
        NewsItem(
            source=SourceKind.OPENROUTER,
            source_id=or_entry.source_id,
            url=or_entry.source_url,
            title=or_entry.title,
            source_evidence={
                "context_length": 128000,
                "prompt_price_per_million": "2.5",
                "completion_price_per_million": "10",
                "free_token_pricing": False,
                "input_modalities": ["text", "image"],
                "provider": "openai",
            },
        )
    ]

    view = build_digest_view(digest, news_items=news_items)
    entry = view.entries[0]
    assert isinstance(entry, OpenRouterDigestEntryView)
    assert entry.display_rank == 1
    assert entry.context_length == 128000
    assert entry.prompt_price_per_million == "2.5"
    assert entry.completion_price_per_million == "10"
    assert entry.free_token_pricing is False
    assert entry.input_modalities == ["text", "image"]
    assert entry.provider == "openai"


def test_extract_openrouter_evidence_known_zero_prices_set_free_token_pricing() -> None:
    from ai_news_agent.services.digest_views import extract_openrouter_evidence

    assert extract_openrouter_evidence(
        {
            "prompt_price_per_million": "0",
            "completion_price_per_million": "0",
        }
    )["free_token_pricing"] is True


def test_extract_openrouter_evidence_missing_prices_not_free() -> None:
    from ai_news_agent.services.digest_views import extract_openrouter_evidence

    out = extract_openrouter_evidence({})
    assert out["prompt_price_per_million"] is None
    assert out["completion_price_per_million"] is None
    assert out["free_token_pricing"] is False

    partial = extract_openrouter_evidence(
        {"prompt_price_per_million": "0", "free_route_suffix": ":free"}
    )
    assert partial["completion_price_per_million"] is None
    assert partial["free_token_pricing"] is False


def test_build_digest_view_openrouter_free_suffix_without_zero_prices() -> None:
    from ai_news_agent.api.schemas.digests import OpenRouterDigestEntryView, build_digest_view

    or_entry = _openrouter_entry().model_copy(
        update={"source_id": "meta-llama/llama-3.2-3b-instruct:free"}
    )
    digest = Digest(generated_at=_fixture_dt(), entries=[or_entry])
    news_items = [
        NewsItem(
            source=SourceKind.OPENROUTER,
            source_id=or_entry.source_id,
            url=or_entry.source_url,
            title=or_entry.title,
            source_evidence={
                "free_route_suffix": ":free",
                "free_token_pricing": False,
            },
        )
    ]
    entry = build_digest_view(digest, news_items=news_items).entries[0]
    assert isinstance(entry, OpenRouterDigestEntryView)
    assert entry.prompt_price_per_million is None
    assert entry.completion_price_per_million is None
    assert entry.free_token_pricing is False


def test_build_digest_view_union_validates_all_kinds_plus_openrouter() -> None:
    from ai_news_agent.api.schemas.digests import (
        DigestEntryView,
        GitHubDigestEntryView,
        HuggingFaceDigestEntryView,
        JuyaDigestEntryView,
        OpenRouterDigestEntryView,
        build_digest_view,
    )

    zhihu = DigestEntry(
        source_kind=SourceKind.ZHIHU,
        source_id="zh-answer-1",
        title="RAG patterns",
        source_name="Zhihu",
        source_url="https://www.zhihu.com/question/1",
        summary="Zhihu summary.",
        why_it_matters="Why.",
        background_knowledge="",
        follow_up_action=FollowUpAction.READ,
    )
    bilibili = DigestEntry(
        source_kind=SourceKind.BILIBILI,
        source_id="BV123",
        title="AI video",
        source_name="Bilibili",
        source_url="https://www.bilibili.com/video/BV123",
        summary="Bili summary.",
        why_it_matters="Why.",
        background_knowledge="",
        follow_up_action=FollowUpAction.WATCH,
    )
    digest = Digest(
        generated_at=_fixture_dt(),
        entries=[
            _github_entry(),
            _huggingface_entry(),
            _juya_entry(),
            zhihu,
            bilibili,
            _openrouter_entry(),
        ],
    )
    hf = _huggingface_entry()
    or_ent = _openrouter_entry()
    news_items = [
        NewsItem(
            source=SourceKind.HUGGINGFACE,
            source_id=hf.source_id,
            url=hf.source_url,
            title=hf.title,
            source_evidence={"base_model": "Qwen/Qwen3.8-27B"},
        ),
        NewsItem(
            source=SourceKind.OPENROUTER,
            source_id=or_ent.source_id,
            url=or_ent.source_url,
            title=or_ent.title,
            source_evidence={"provider": "openai"},
        ),
    ]

    view = build_digest_view(digest, news_items=news_items)
    assert len(view.entries) == 6
    assert isinstance(view.entries[0], GitHubDigestEntryView)
    assert isinstance(view.entries[1], HuggingFaceDigestEntryView)
    assert view.entries[1].base_model == "Qwen/Qwen3.8-27B"
    assert isinstance(view.entries[2], JuyaDigestEntryView)
    assert isinstance(view.entries[3], DigestEntryView)
    assert view.entries[3].source_kind == SourceKind.ZHIHU
    assert isinstance(view.entries[4], DigestEntryView)
    assert view.entries[4].source_kind == SourceKind.BILIBILI
    assert isinstance(view.entries[5], OpenRouterDigestEntryView)
