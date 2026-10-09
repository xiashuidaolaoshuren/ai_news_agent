"""GitHub daily-trending star counts parsed from the public trending page."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from ai_news_agent.github_previews import _github_full_name, _is_allowed_github_url
from ai_news_agent.models import ConnectorWarning, NewsItem, SourceKind

TRENDING_PATH = "/trending"
TRENDING_SINCE = "daily"
TRENDING_MAX_RESPONSE_BYTES = 2_000_000
TRENDING_MAX_REDIRECTS = 3

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

_DAILY_COUNT_RE = re.compile(r"^([\d,]+)\s+stars?\s+today$", re.IGNORECASE)
_REPO_HREF_RE = re.compile(r"^/([^/?#]+)/([^/?#]+)/?$")


def _class_tokens(attrs: list[tuple[str, str | None]]) -> set[str]:
    for name, value in attrs:
        if name == "class" and value:
            return {token for token in value.split() if token}
    return set()


def _attr(attrs: list[tuple[str, str | None]], wanted: str) -> str | None:
    for name, value in attrs:
        if name == wanted:
            return value
    return None


class _TrendingRowParser(HTMLParser):
    """Collect ``owner/repo`` and its daily star count from trending rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stars_today: dict[str, int] = {}
        self._row_depth = 0
        self._in_heading = False
        self._heading_depth = 0
        self._full_name: str | None = None
        self._in_daily_span = False
        self._daily_depth = 0
        self._daily_text: list[str] = []
        self._daily_value: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _class_tokens(attrs)
        if tag == "article" and "Box-row" in classes and self._row_depth == 0:
            self._begin_row()
            return
        if self._row_depth == 0:
            return
        if tag == "article":
            self._row_depth += 1
            return
        if tag == "h2":
            self._in_heading = True
            self._heading_depth = 0
            return
        if self._in_heading:
            if tag == "h2":
                self._heading_depth += 1
            elif tag == "a" and self._full_name is None:
                self._full_name = _repo_full_name(_attr(attrs, "href"))
            return
        if self._in_daily_span:
            if tag == "span":
                self._daily_depth += 1
            return
        if tag == "span" and "float-sm-right" in classes:
            self._in_daily_span = True
            self._daily_depth = 0
            self._daily_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self._row_depth == 0:
            return
        if tag == "article":
            self._row_depth -= 1
            if self._row_depth == 0:
                self._end_row()
            return
        if self._in_heading and tag == "h2":
            if self._heading_depth == 0:
                self._in_heading = False
            else:
                self._heading_depth -= 1
            return
        if self._in_daily_span and tag == "span":
            if self._daily_depth == 0:
                self._in_daily_span = False
                self._daily_value = _parse_daily_count(" ".join(self._daily_text))
            else:
                self._daily_depth -= 1
            return

    def handle_data(self, data: str) -> None:
        if self._in_daily_span:
            self._daily_text.append(data)

    def _begin_row(self) -> None:
        self._row_depth = 1
        self._in_heading = False
        self._heading_depth = 0
        self._full_name = None
        self._in_daily_span = False
        self._daily_depth = 0
        self._daily_text = []
        self._daily_value = None

    def _end_row(self) -> None:
        full_name = self._full_name
        value = self._daily_value
        self._full_name = None
        self._daily_value = None
        if full_name is None or value is None:
            return
        self.stars_today.setdefault(full_name.casefold(), value)


def _repo_full_name(href: str | None) -> str | None:
    if not href:
        return None
    match = _REPO_HREF_RE.match(href)
    if match is None:
        return None
    owner, repo = match.group(1), match.group(2)
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def _parse_daily_count(text: str) -> int | None:
    normalized = " ".join(text.split())
    match = _DAILY_COUNT_RE.match(normalized)
    if match is None:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_trending_stars_today(html: str) -> dict[str, int]:
    """Map casefolded ``owner/repo`` to the stars gained on the daily list."""
    parser = _TrendingRowParser()
    parser.feed(html)
    parser.close()
    return parser.stars_today


async def enrich_github_stars_today(
    items: list[NewsItem],
    *,
    client: httpx.AsyncClient,
) -> tuple[list[NewsItem], list[ConnectorWarning]]:
    """Attach ``stars_today`` to GitHub items listed on the daily trending page."""
    if not any(item.source is SourceKind.GITHUB for item in items):
        return items, []

    html, warning = await _fetch_trending_html(client)
    if warning is not None:
        return items, [warning]

    stars_today = parse_trending_stars_today(html or "")
    return _join_stars_today(items, stars_today), []


async def _fetch_trending_html(
    client: httpx.AsyncClient,
) -> tuple[str | None, ConnectorWarning | None]:
    """Fetch the daily page once, following bounded same-host redirects."""
    url: str | None = TRENDING_PATH
    params: dict[str, str] | None = {"since": TRENDING_SINCE}
    for _ in range(TRENDING_MAX_REDIRECTS + 1):
        assert url is not None
        try:
            async with client.stream("GET", url, params=params) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("Location")
                    if not location:
                        return None, _trending_warning("redirect missing Location")
                    next_url = urljoin(str(response.url), location)
                    if not _is_allowed_github_url(next_url):
                        return None, _trending_warning("redirect left github.com")
                    url = next_url
                    params = None
                    continue
                if response.status_code != 200:
                    return None, _trending_warning(f"HTTP {response.status_code}")
                body, warning = await _read_capped_body(response)
                if warning is not None:
                    return None, warning
                return body, None
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return None, _trending_warning(str(exc))
    return None, _trending_warning("too many redirects")


async def _read_capped_body(
    response: httpx.Response,
) -> tuple[str | None, ConnectorWarning | None]:
    """Read a response body, rejecting anything past the trending byte cap."""
    encoding = response.encoding or "utf-8"
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > TRENDING_MAX_RESPONSE_BYTES:
            return None, _trending_warning("response too large")
        body.extend(chunk)
    return body.decode(encoding, errors="replace"), None


def _trending_warning(detail: str) -> ConnectorWarning:
    return ConnectorWarning(
        connector="github",
        code="trending_unavailable",
        message="GitHub daily trending stars unavailable",
        detail=detail[:300],
    )


def _join_stars_today(
    items: list[NewsItem],
    stars_today: dict[str, int],
) -> list[NewsItem]:
    if not stars_today:
        return list(items)
    enriched = list(items)
    for index, item in enumerate(items):
        if item.source is not SourceKind.GITHUB:
            continue
        full_name = _github_full_name(item)
        if not full_name:
            continue
        value = stars_today.get(full_name.casefold())
        if value is None:
            continue
        evidence = {**(item.source_evidence or {}), "stars_today": value}
        enriched[index] = item.model_copy(update={"source_evidence": evidence})
    return enriched


__all__ = [
    "TRENDING_MAX_REDIRECTS",
    "TRENDING_MAX_RESPONSE_BYTES",
    "TRENDING_PATH",
    "TRENDING_SINCE",
    "enrich_github_stars_today",
    "parse_trending_stars_today",
]
