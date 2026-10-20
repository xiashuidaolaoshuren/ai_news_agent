"""Tests for natural-language digest intent parsing."""

from __future__ import annotations

import pytest

from ai_news_agent.intent import parse_connector_names_from_message, parse_digest_intent


def test_parse_bilibili_video_url_skips_default_topics() -> None:
    req = parse_digest_intent(
        "Digest https://www.bilibili.com/video/BV1demo0001",
    )
    assert req.topics == []
    assert "https://www.bilibili.com/video/BV1demo0001" in req.bilibili_manual_urls


def test_parse_github_repo_url() -> None:
    req = parse_digest_intent(
        "Please digest https://github.com/acme/widget for me",
    )
    assert req.topics == []
    assert any("github.com/acme/widget" in u for u in req.github_manual_urls)
    assert req.github_target_channels == []


def test_parse_juya_website_url_routes_to_github_connector() -> None:
    req = parse_digest_intent("Digest https://daily.juya.uk/")
    assert req.topics == []
    assert any("daily.juya.uk" in u for u in req.juya_manual_urls)
    assert not req.github_manual_urls


def test_parse_digest_intent_rejects_legacy_juya_github_url() -> None:
    with pytest.raises(ValueError, match="daily.juya.uk"):
        parse_digest_intent("Digest https://github.com/jujuyaya/juya-ai-daily")


def test_parse_explicit_english_instruction() -> None:
    req = parse_digest_intent(
        "Summarize the latest Juya AI 早报 for a beginner in English",
    )
    assert req.output_language == "en"


def test_parse_explicit_chinese_instruction() -> None:
    req = parse_digest_intent("Give me today's digest in Chinese")
    assert req.output_language == "zh-CN"


def test_parse_cjk_language_instruction() -> None:
    req = parse_digest_intent("用中文总结今天的 AI 早报")
    assert req.output_language == "zh-CN"


def test_parse_ignores_bare_language_word() -> None:
    req = parse_digest_intent("Show me Chinese AI model news")
    assert req.output_language is None


def test_resolve_digest_request_keeps_language_without_other_selectors() -> None:
    from ai_news_agent.digest_request_builder import resolve_digest_request

    req = resolve_digest_request(
        "Summarize the latest Juya AI 早报 for a beginner in English"
    )
    assert req.output_language == "en"
    assert req.connector_names == ["juya"]


def test_resolve_digest_request_bare_defaults_to_juya() -> None:
    from ai_news_agent.digest_request_builder import resolve_digest_request

    req = resolve_digest_request("Give me today's AI digest")
    assert req.connector_names == ["juya"]
    assert req.primary_source == "juya"


def test_resolve_digest_request_github_repo_url_does_not_stack_juya() -> None:
    from ai_news_agent.digest_request_builder import resolve_digest_request

    req = resolve_digest_request("Digest https://github.com/acme/widget")
    assert req.connector_names == ["github"]
    assert req.primary_source == "github"
    assert "juya" not in (req.connector_names or [])


def test_resolve_digest_request_juya_website_url_routes_to_juya() -> None:
    from ai_news_agent.digest_request_builder import resolve_digest_request

    req = resolve_digest_request("Digest https://daily.juya.uk/")
    assert req.connector_names == ["juya"]
