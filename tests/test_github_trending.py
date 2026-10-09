"""Tests for GitHub daily-trending stars enrichment (Milestone 8B B6)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ai_news_agent.models import NewsItem, SourceKind

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_fixture_text(name: str) -> str:
    path = FIXTURES / name
    assert path.is_file(), f"missing fixture {path}"
    return path.read_text(encoding="utf-8")


def _github_item(
    full_name: str,
    *,
    stars: int,
    collected_at: datetime,
) -> NewsItem:
    return NewsItem(
        source=SourceKind.GITHUB,
        source_id=full_name,
        url=f"https://github.com/{full_name}",
        title=full_name,
        collected_at=collected_at,
        stars_or_views=stars,
        source_evidence={"owner_name": full_name.split("/")[0]},
    )


def test_parse_trending_stars_today_reads_daily_rows() -> None:
    from ai_news_agent.github_trending import parse_trending_stars_today

    html = _load_fixture_text("github_trending_daily_sample.html")

    stars = parse_trending_stars_today(html)

    # Thousands separators and stray whitespace around the count are handled.
    assert stars["demo-org/awesome-agents"] == 1234
    # Repository names are keyed case-insensitively.
    assert stars["demo-org/rag-cookbook"] == 5925
    # Non-daily rows never enter the map.
    assert "demo-org/weekly-repo" not in stars
    assert "demo-org/monthly-repo" not in stars
    # Rows without a daily figure are skipped.
    assert "demo-org/no-count" not in stars


def test_parse_trending_stars_today_tolerates_missing_markup() -> None:
    from ai_news_agent.github_trending import parse_trending_stars_today

    assert parse_trending_stars_today("") == {}
    assert parse_trending_stars_today("<html><body></body></html>") == {}


def test_enrich_github_stars_today_joins_one_page_onto_the_batch() -> None:
    from ai_news_agent.github_trending import enrich_github_stars_today
    from ai_news_agent.models import SourceKind
    from ai_news_agent.ranking import rank_items

    html = _load_fixture_text("github_trending_daily_sample.html")
    collected_at = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    matched = _github_item("demo-org/awesome-agents", stars=128_000, collected_at=collected_at)
    case_different = _github_item("DEMO-ORG/RAG-COOKBOOK", stars=420, collected_at=collected_at)
    absent = _github_item("demo-org/absent-repo", stars=17, collected_at=collected_at)
    other_source = NewsItem(
        source=SourceKind.JUYA,
        source_id="juya-1",
        url="https://daily.juya.uk/2026/10/09",
        title="Juya bulletin",
        collected_at=collected_at,
    )
    items = [matched, case_different, absent, other_source]
    before = rank_items(items, top_n=4, now=collected_at)

    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        if request.url.path == "/trending":
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    async def main() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert warnings == []
        assert [item.source_id for item in out_items] == [i.source_id for i in items]
        assert len(requests) == 1
        method, url = requests[0]
        assert method == "GET"
        assert "/trending" in url
        assert "since=daily" in url

        enriched_matched = out_items[0]
        assert enriched_matched.source_evidence["stars_today"] == 1234
        assert enriched_matched.source_evidence["owner_name"] == "demo-org"
        assert isinstance(enriched_matched.source_evidence["stars_today"], int)
        assert enriched_matched.stars_or_views == 128_000

        assert out_items[1].source_evidence["stars_today"] == 5925
        assert "stars_today" not in out_items[2].source_evidence
        assert out_items[3].source_evidence == other_source.source_evidence

        # Inputs and ranking are untouched.
        assert "stars_today" not in matched.source_evidence
        after = rank_items(out_items, top_n=4, now=collected_at)
        assert [(ri.item.source_id, ri.score_total) for ri in after] == [
            (ri.item.source_id, ri.score_total) for ri in before
        ]

    asyncio.run(main())


def test_enrich_github_stars_today_warns_and_returns_items_on_http_error() -> None:
    from ai_news_agent.github_trending import enrich_github_stars_today

    collected_at = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    items = [_github_item("demo-org/awesome-agents", stars=128_000, collected_at=collected_at)]

    async def main() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(503, text="nope"))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert out_items == items
        assert "stars_today" not in out_items[0].source_evidence
        assert len(warnings) == 1
        warning = warnings[0]
        assert warning.connector == "github"
        assert warning.code == "trending_unavailable"

    asyncio.run(main())


def test_enrich_github_stars_today_warns_on_transport_error() -> None:
    from ai_news_agent.github_trending import enrich_github_stars_today

    collected_at = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    items = [_github_item("demo-org/awesome-agents", stars=128_000, collected_at=collected_at)]

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    async def main() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert out_items == items
        assert len(warnings) == 1
        assert warnings[0].code == "trending_unavailable"

    asyncio.run(main())


class _ChunkStream(httpx.AsyncByteStream):
    """Chunked body that records how many chunks were delivered and when closed."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.delivered = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self._chunks:
            self.delivered += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class _ChunkedTransport(httpx.AsyncBaseTransport):
    """Serve a response as explicit chunks so early termination is observable."""

    def __init__(self, chunks: list[bytes], *, status_code: int = 200) -> None:
        self.stream = _ChunkStream(chunks)
        self._status_code = status_code

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status_code, stream=self.stream)


def test_enrich_github_stars_today_stops_early_on_oversized_page() -> None:
    from ai_news_agent.github_trending import (
        TRENDING_MAX_RESPONSE_BYTES,
        enrich_github_stars_today,
    )

    collected_at = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    items = [_github_item("demo-org/awesome-agents", stars=128_000, collected_at=collected_at)]

    chunk_size = 500_000
    chunk_count = (TRENDING_MAX_RESPONSE_BYTES // chunk_size) + 2
    chunks = [b"x" * chunk_size] * chunk_count

    async def main() -> None:
        transport = _ChunkedTransport(chunks)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert out_items == items
        assert len(warnings) == 1
        assert warnings[0].code == "trending_unavailable"
        assert transport.stream.closed is True
        assert transport.stream.delivered < chunk_count

    asyncio.run(main())


def test_enrich_github_stars_today_accepts_page_at_the_size_cap() -> None:
    from ai_news_agent.github_trending import (
        TRENDING_MAX_RESPONSE_BYTES,
        enrich_github_stars_today,
    )

    html = _load_fixture_text("github_trending_daily_sample.html")
    padding = TRENDING_MAX_RESPONSE_BYTES - len(html) - len("<!---->")
    assert padding > 0
    padded = f"<!--{'x' * padding}-->" + html
    assert len(padded) == TRENDING_MAX_RESPONSE_BYTES
    assert len(padded) > 512_000

    collected_at = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    items = [_github_item("demo-org/awesome-agents", stars=128_000, collected_at=collected_at)]
    chunks = [padded.encode("utf-8")[i : i + 200_000] for i in range(0, len(padded), 200_000)]

    async def main() -> None:
        transport = _ChunkedTransport(chunks)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert warnings == []
        assert out_items[0].source_evidence["stars_today"] == 1234
        assert transport.stream.closed is True

    asyncio.run(main())


def _redirect_transport(
    pages: dict[str, tuple[int, str]],
    *,
    locations: dict[str, str] | None = None,
    requested: list[str] | None = None,
) -> httpx.MockTransport:
    """Serve paths as pages or redirects, recording every requested path."""
    locations = locations or {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if requested is not None:
            requested.append(path)
        if path in locations:
            return httpx.Response(302, headers={"Location": locations[path]})
        status, body = pages.get(path, (404, ""))
        return httpx.Response(status, text=body)

    return httpx.MockTransport(handler)


def _trending_items() -> list[NewsItem]:
    collected_at = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    return [_github_item("demo-org/awesome-agents", stars=128_000, collected_at=collected_at)]


def test_enrich_github_stars_today_follows_allowed_relative_redirect() -> None:
    from ai_news_agent.github_trending import enrich_github_stars_today

    html = _load_fixture_text("github_trending_daily_sample.html")
    requested: list[str] = []
    transport = _redirect_transport(
        {"/trending-daily": (200, html)},
        locations={"/trending": "/trending-daily"},
        requested=requested,
    )
    items = _trending_items()

    async def main() -> None:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert warnings == []
        assert out_items[0].source_evidence["stars_today"] == 1234
        assert requested == ["/trending", "/trending-daily"]

    asyncio.run(main())


def test_enrich_github_stars_today_follows_up_to_three_redirects() -> None:
    from ai_news_agent.github_trending import enrich_github_stars_today

    html = _load_fixture_text("github_trending_daily_sample.html")
    transport = _redirect_transport(
        {"/hop3": (200, html)},
        locations={
            "/trending": "/hop1",
            "/hop1": "/hop2",
            "/hop2": "/hop3",
        },
    )
    items = _trending_items()

    async def main() -> None:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert warnings == []
        assert out_items[0].source_evidence["stars_today"] == 1234

    asyncio.run(main())


def test_enrich_github_stars_today_warns_when_redirects_exhausted() -> None:
    from ai_news_agent.github_trending import enrich_github_stars_today

    requested: list[str] = []
    transport = _redirect_transport(
        {},
        locations={
            "/trending": "/hop1",
            "/hop1": "/hop2",
            "/hop2": "/hop3",
            "/hop3": "/hop4",
            "/hop4": "/hop5",
        },
        requested=requested,
    )
    items = _trending_items()

    async def main() -> None:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert out_items == items
        assert len(warnings) == 1
        assert warnings[0].code == "trending_unavailable"
        assert "redirect" in (warnings[0].detail or "").lower()
        # Only the allowed hops were requested; the fourth hop target never was.
        assert requested == ["/trending", "/hop1", "/hop2", "/hop3"]

    asyncio.run(main())


def test_enrich_github_stars_today_rejects_off_host_redirect() -> None:
    from ai_news_agent.github_trending import enrich_github_stars_today

    requested: list[str] = []
    transport = _redirect_transport(
        {},
        locations={"/trending": "https://evil.example/phish"},
        requested=requested,
    )
    items = _trending_items()

    async def main() -> None:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://github.com",
            follow_redirects=False,
        ) as client:
            out_items, warnings = await enrich_github_stars_today(items, client=client)

        assert out_items == items
        assert len(warnings) == 1
        assert warnings[0].code == "trending_unavailable"
        assert "redirect" in (warnings[0].detail or "").lower()
        assert requested == ["/trending"]

    asyncio.run(main())
