"""Tests for the dedicated Juya bulletin connector (Milestone 5 T1)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from ai_news_agent.connectors.base import ConnectorRequest
from ai_news_agent.connectors.juya import JuyaConnector, parse_juya_rss_entries
from ai_news_agent.models import SourceKind

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _rss_fixture_text() -> str:
    return (FIXTURES / "juya_rss_sample.xml").read_text(encoding="utf-8")


def _juya_website_transport(
    rss_text: str,
    *,
    rss_status: int = 200,
    markdown_by_path: dict[str, str] | None = None,
) -> httpx.MockTransport:
    markdown_by_path = markdown_by_path or {}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        path = request.url.path
        if host == "daily.juya.uk":
            if path == "/rss.xml":
                return httpx.Response(rss_status, text=rss_text)
            if path in markdown_by_path:
                return httpx.Response(200, text=markdown_by_path[path])
            return httpx.Response(404, text="not found")
        return httpx.Response(404, json={"message": "not found"})

    return httpx.MockTransport(handler)


def test_juya_connector_name() -> None:
    assert JuyaConnector().name() == "juya"


def test_parse_juya_rss_entries_maps_juya_identity() -> None:
    xml_text = _rss_fixture_text()
    items = parse_juya_rss_entries(xml_text, max_items=5)
    assert len(items) == 2
    assert items[0].title == "2026-06-16"
    assert items[0].url == "https://daily.juya.uk/2026/06/16/"
    assert "GLM-5.2" in (items[0].raw_snippet or "")
    assert items[0].source is SourceKind.JUYA
    assert items[0].tags == ["juya", "juya-daily", "rss"]
    assert items[0].source_id.startswith("juya-rss-")


def test_juya_collect_fetches_website_rss_and_markdown() -> None:
    markdown = {
        "/markdown/2026-06-16.md": "# 2026-06-16\n\nGLM-5.2 release notes.",
        "/markdown/2026-06-15.md": "# 2026-06-15\n\nPrior day roundup.",
    }
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        path = request.url.path
        requested_paths.append(path)
        if host == "daily.juya.uk":
            if path == "/rss.xml":
                return httpx.Response(200, text=_rss_fixture_text())
            if path in markdown:
                return httpx.Response(200, text=markdown[path])
            return httpx.Response(404, text="not found")
        return httpx.Response(404, json={"message": "not found"})

    async def main() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            conn = JuyaConnector(client=client)
            out = await conn.collect(
                ConnectorRequest(
                    topics=["rag"],
                    max_items=5,
                ),
            )
        assert "/rss.xml" in requested_paths
        assert len(out.items) == 2
        assert out.items[0].title == "2026-06-16"
        assert "daily.juya.uk" in out.items[0].url
        assert "GLM-5.2" in (out.items[0].raw_snippet or "")
        assert out.items[0].source is SourceKind.JUYA
        assert "juya-markdown" in out.items[0].tags
        assert all(w.connector == "juya" for w in out.warnings)
        assert not any(w.code == "juya_rss_unavailable" for w in out.warnings)

    asyncio.run(main())


def test_juya_collect_issue_mode_enriches_issue_metadata_from_markdown() -> None:
    markdown = _load_fixture_markdown("juya_website_with_cover_sample.md")

    async def main() -> None:
        transport = _juya_website_transport(
            _rss_fixture_text(),
            markdown_by_path={"/markdown/2026-06-16.md": markdown},
        )
        async with httpx.AsyncClient(transport=transport) as client:
            out = await JuyaConnector(client=client).collect(
                ConnectorRequest(topics=["rag"], max_items=1),
            )
        assert len(out.items) == 1
        evidence = out.items[0].source_evidence
        assert evidence.get("juya_item_type") == "issue"
        assert evidence.get("issue_cover_url", "").startswith("https://assets.juya.uk/cover/")
        assert evidence.get("issue_date") == "2026-06-19"
        assert "SpaceX" in (evidence.get("issue_lead_title") or "")
        assert "GLM-5.2" in (out.items[0].raw_snippet or "")

    asyncio.run(main())


def _load_fixture_markdown(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_juya_collect_stories_mode_emits_one_item_per_numbered_story() -> None:
    markdown = _load_fixture_markdown("juya_website_with_cover_sample.md")

    async def main() -> None:
        transport = _juya_website_transport(
            _rss_fixture_text(),
            markdown_by_path={"/markdown/2026-06-16.md": markdown},
        )
        async with httpx.AsyncClient(transport=transport) as client:
            out = await JuyaConnector(client=client).collect(
                ConnectorRequest(
                    topics=["rag"],
                    max_items=5,
                    juya_item_mode="stories",
                ),
            )
        assert len(out.items) == 2
        assert out.items[0].source_id.startswith("juya-story-")
        assert out.items[0].source_evidence["juya_item_type"] == "story"
        assert out.items[0].source_evidence["story_number"] == 1
        assert out.items[1].source_evidence["story_number"] == 2
        assert "#story-" in out.items[0].url
        assert out.items[0].title.startswith("DeepSeek")
        assert "juya-story" in out.items[0].tags

    asyncio.run(main())


def test_juya_collect_stories_mode_stops_after_story_cap_without_issue_rows() -> None:
    markdown = _load_fixture_markdown("juya_website_with_cover_sample.md")
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        path = request.url.path
        requested_paths.append(path)
        if host == "daily.juya.uk":
            if path == "/rss.xml":
                return httpx.Response(200, text=_rss_fixture_text())
            if path in {
                "/markdown/2026-06-16.md",
                "/markdown/2026-06-15.md",
            }:
                return httpx.Response(200, text=markdown)
            return httpx.Response(404, text="not found")
        return httpx.Response(404, json={"message": "not found"})

    async def main() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            out = await JuyaConnector(client=client).collect(
                ConnectorRequest(
                    topics=["rag"],
                    max_items=2,
                    juya_item_mode="stories",
                ),
            )
        assert len(out.items) == 2
        assert all(
            item.source_evidence.get("juya_item_type") == "story" for item in out.items
        )
        assert "/markdown/2026-06-16.md" in requested_paths
        assert "/markdown/2026-06-15.md" not in requested_paths

    asyncio.run(main())


def test_juya_collect_stories_mode_warns_when_markdown_unparseable() -> None:
    async def main() -> None:
        transport = _juya_website_transport(
            _rss_fixture_text(),
            markdown_by_path={"/markdown/2026-06-16.md": "plain text without stories"},
        )
        async with httpx.AsyncClient(transport=transport) as client:
            out = await JuyaConnector(client=client).collect(
                ConnectorRequest(
                    topics=["rag"],
                    max_items=5,
                    juya_item_mode="stories",
                ),
            )
        assert out.items == []
        assert any(w.code == "juya_stories_unavailable" for w in out.warnings)

    asyncio.run(main())


def test_juya_collect_rss_failure_warns_without_github_fallback() -> None:
    async def main() -> None:
        transport = _juya_website_transport(_rss_fixture_text(), rss_status=404)
        async with httpx.AsyncClient(transport=transport) as client:
            out = await JuyaConnector(client=client).collect(
                ConnectorRequest(
                    topics=[],
                    max_items=5,
                ),
            )
        assert out.items == []
        assert any(
            w.code == "juya_rss_unavailable" and w.connector == "juya"
            for w in out.warnings
        )

    asyncio.run(main())
