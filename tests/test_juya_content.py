"""Tests for structured Juya issue markdown parsing."""

from __future__ import annotations

from pathlib import Path

from ai_news_agent.juya_content import (
    build_juya_issue_evidence,
    build_juya_story_evidence,
    parse_juya_issue_markdown,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_juya_issue_markdown_extracts_cover_date_and_lead() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_with_cover_sample.md"))
    assert parsed.cover_url == "https://assets.juya.uk/cover/2026-06-19.png"
    assert parsed.date == "2026-06-19"
    assert parsed.lead_title is not None
    assert "SpaceX" in parsed.lead_title
    assert "GLM-5.2" in parsed.lead_title


def test_parse_juya_issue_markdown_uses_cover_path_not_article_image() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_with_cover_sample.md"))
    assert parsed.cover_url is not None
    assert "assets.juya.uk/cover/" in parsed.cover_url
    assert "daily.juya.uk/images" not in parsed.cover_url


def test_parse_juya_issue_markdown_extracts_numbered_stories_without_overview_duplicates() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_with_cover_sample.md"))
    assert len(parsed.stories) == 2
    assert [story.number for story in parsed.stories] == [1, 2]
    assert parsed.stories[0].title.startswith("DeepSeek")
    assert parsed.stories[0].section == "要闻"
    assert parsed.stories[0].original_url == "https://www.deepseek.com"
    assert parsed.stories[1].original_url == "https://openai.com/blog/codex-replay"


def test_parse_linked_story_headings_keeps_plain_title_and_article_url() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_linked_headlines_sample.md"))

    assert len(parsed.stories) == 2
    first = parsed.stories[0]
    assert first.title == "有关部门拟增列AI技术进入出口管制目录"
    assert (
        first.original_url
        == "https://aqygzj.mofcom.gov.cn/flzc/gzjgfxwj/art/2026/art_c99f95ca.html"
    )


def test_parse_plain_story_heading_skips_body_images_for_original_url() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_linked_headlines_sample.md"))

    second = parsed.stories[1]
    assert second.title == "OpenAI 宣布优化 Codex 提升用户有效使用量"
    assert (
        second.original_url == "https://x.com/thsottiaux/status/2111244596131111253"
    )
    assert "assets.juya.uk" not in (second.original_url or "")


def test_parse_issue_with_only_video_banner_has_no_lead() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_linked_headlines_sample.md"))

    assert parsed.lead_title is None


def test_parse_issue_keeps_genuine_lead_paragraph() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_with_cover_sample.md"))

    assert parsed.lead_title is not None
    assert "SpaceX" in parsed.lead_title


def test_build_juya_story_evidence_keeps_clean_summary_and_drops_image_artifacts() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_linked_headlines_sample.md"))
    first = parsed.stories[0]

    evidence = build_juya_story_evidence(
        parsed,
        first,
        issue_id="juya-rss-abc",
        issue_url="https://daily.juya.uk/issues/2026-10-17/",
    )

    assert evidence["story_summary"].startswith("有关部门就修订出口技术目录")
    assert "assets.juya.uk" not in evidence["story_summary"]
    assert "m001_" not in first.evidence_text
    assert "---" not in first.evidence_text


def test_build_juya_story_evidence_omits_missing_summary() -> None:
    parsed = parse_juya_issue_markdown(
        "# AI 早报 2026-10-18\n\n## 要闻\n\n### 无摘要故事 `#1`\n\n正文内容。\n"
    )

    evidence = build_juya_story_evidence(
        parsed,
        parsed.stories[0],
        issue_id="juya-rss-xyz",
        issue_url="https://daily.juya.uk/issues/2026-10-18/",
    )

    assert "story_summary" not in evidence
    assert evidence["story_identity"] == "juya-rss-xyz:1"


def test_build_juya_issue_evidence_maps_parsed_metadata() -> None:
    parsed = parse_juya_issue_markdown(_load("juya_website_with_cover_sample.md"))
    evidence = build_juya_issue_evidence(
        parsed,
        issue_id="juya-rss-abc",
        issue_url="https://daily.juya.uk/2026/06/19/",
    )
    assert evidence["juya_item_type"] == "issue"
    assert evidence["issue_id"] == "juya-rss-abc"
    assert evidence["issue_date"] == "2026-06-19"
    assert evidence["issue_cover_url"].startswith("https://")
    assert "SpaceX" in evidence["issue_lead_title"]
