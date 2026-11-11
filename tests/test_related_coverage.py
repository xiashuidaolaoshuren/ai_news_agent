"""Tests for related_display_ranks identity linking (B5)."""

from __future__ import annotations

from ai_news_agent.models import DigestEntry, FollowUpAction, NewsItem, SourceKind


def _entry(title: str, *, kind: SourceKind = SourceKind.GITHUB, source_id: str = "a") -> DigestEntry:
    return DigestEntry(
        source_kind=kind,
        source_id=source_id,
        title=title,
        source_name="Test",
        source_url="https://example.com",
        summary="s",
        why_it_matters="w",
        background_knowledge="b",
        follow_up_action=FollowUpAction.READ,
    )


def _pair(entry: DigestEntry) -> tuple[DigestEntry, NewsItem | None]:
    return (entry, None)


def test_confident_pair_lists_each_other_and_unrelated_lists_none() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    a = _entry("Qwen3.8-27B", source_id="1")
    b = _entry("Qwen3.8-27B", source_id="2")
    c = _entry("Llama 3.1 8B", source_id="3")
    result = related_display_ranks([_pair(a), _pair(b), _pair(c)])
    assert result[1] == [2]
    assert result[2] == [1]
    assert result[3] == []


def test_flash_and_pro_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    flash = _entry("M3.1 Flash")
    pro = _entry("M3.1 Pro")
    result = related_display_ranks([_pair(flash), _pair(pro)])
    assert result[1] == []
    assert result[2] == []


def test_different_sizes_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    small = _entry("M3.1 7B")
    large = _entry("M3.1 70B")
    result = related_display_ranks([_pair(small), _pair(large)])
    assert result[1] == []
    assert result[2] == []


def test_different_versions_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    m3 = _entry("M3")
    m31 = _entry("M3.1")
    result = related_display_ranks([_pair(m3), _pair(m31)])
    assert result[1] == []
    assert result[2] == []


def test_generic_topic_words_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    a = _entry("both are reasoning models")
    b = _entry("both are reasoning models")
    result = related_display_ranks([_pair(a), _pair(b)])
    assert result[1] == []
    assert result[2] == []


def test_one_sided_version_does_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    with_ver = _entry("M3.1 8B")
    without = _entry("8B")
    result = related_display_ranks([_pair(with_ver), _pair(without)])
    assert result[1] == []
    assert result[2] == []

