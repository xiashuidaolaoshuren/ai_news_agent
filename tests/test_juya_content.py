"""Tests for structured Juya issue markdown parsing."""

from __future__ import annotations

from pathlib import Path

from ai_news_agent.juya_content import (
    build_juya_issue_evidence,
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
