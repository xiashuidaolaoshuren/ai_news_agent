"""GitHub repository social-preview image lookup from canonical repo pages."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from ai_news_agent.models import ConnectorWarning, NewsItem, SourceKind

GITHUB_WEB_BASE = "https://github.com"
PREVIEW_TIMEOUT = httpx.Timeout(5.0)
PREVIEW_MAX_CONCURRENT = 4
PREVIEW_MAX_RESPONSE_BYTES = 512_000
PREVIEW_MAX_REDIRECTS = 3

_OG_IMAGE_RE = re.compile(
    r'<meta\s+[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_RE_ALT = re.compile(
    r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
    re.IGNORECASE,
)


def parse_og_image_url(html: str) -> str | None:
    """Extract the first HTTPS ``og:image`` content URL from HTML."""
    for pattern in (_OG_IMAGE_RE, _OG_IMAGE_RE_ALT):
        match = pattern.search(html)
        if match is None:
            continue
        url = match.group(1).strip()
        if url.startswith("https://"):
            return url
    return None


async def enrich_github_previews(
    items: list[NewsItem],
    *,
    client: httpx.AsyncClient,
) -> tuple[list[NewsItem], list[ConnectorWarning]]:
    """Attach repository preview image URLs to GitHub digest items."""
    gh_items = [item for item in items if item.source is SourceKind.GITHUB]
    if not gh_items:
        return items, []

    semaphore = asyncio.Semaphore(PREVIEW_MAX_CONCURRENT)
    cache: dict[str, tuple[str | None, ConnectorWarning | None]] = {}
    warnings: list[ConnectorWarning] = []

    async def _lookup(full_name: str) -> None:
        async with semaphore:
            preview_url, warning = await _fetch_repo_preview_url(client, full_name)
            cache[full_name] = (preview_url, warning)

    full_names = [_github_full_name(item) for item in gh_items]
    unique_names = list(dict.fromkeys(name for name in full_names if name))
    await asyncio.gather(*(_lookup(name) for name in unique_names))

    enriched: list[NewsItem] = []
    for item in items:
        if item.source is not SourceKind.GITHUB:
            enriched.append(item)
            continue
        full_name = _github_full_name(item)
        if not full_name or full_name not in cache:
            enriched.append(item)
            continue
        preview_url, warning = cache[full_name]
        if warning is not None:
            warnings.append(warning)
        if not preview_url:
            enriched.append(item)
            continue
        evidence = {**(item.source_evidence or {}), "preview_image_url": preview_url}
        enriched.append(item.model_copy(update={"source_evidence": evidence}))

    return enriched, warnings


def _github_full_name(item: NewsItem) -> str | None:
    title = (item.title or "").strip()
    if "/" in title:
        return title
    url = (item.url or "").strip()
    if "github.com/" in url:
        path = urlparse(url).path.strip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return None


async def _fetch_repo_preview_url(
    client: httpx.AsyncClient,
    full_name: str,
) -> tuple[str | None, ConnectorWarning | None]:
    part = full_name.partition("/")
    if not part[1]:
        return None, None
    owner, _, repo = part
    if not owner or not repo:
        return None, None

    path = f"/{owner}/{repo}"
    current_url = f"{GITHUB_WEB_BASE}{path}"

    try:
        for _ in range(PREVIEW_MAX_REDIRECTS + 1):
            response = await client.get(current_url)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    return None, _preview_warning(full_name, "redirect missing Location")
                next_url = _normalize_redirect(current_url, location)
                if not _is_allowed_github_url(next_url):
                    return None, _preview_warning(full_name, "redirect left github.com")
                current_url = next_url
                continue
            break
        else:
            return None, _preview_warning(full_name, "too many redirects")
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        return None, _preview_warning(full_name, str(exc))

    if response.status_code != 200:
        return None, _preview_warning(full_name, f"HTTP {response.status_code}")

    if len(response.content) > PREVIEW_MAX_RESPONSE_BYTES:
        return None, _preview_warning(full_name, "response too large")

    preview_url = parse_og_image_url(response.text)
    return preview_url, None


def _normalize_redirect(current_url: str, location: str) -> str:
    if location.startswith(("http://", "https://")):
        return location
    if location.startswith("/"):
        parsed = urlparse(current_url)
        return f"{parsed.scheme}://{parsed.netloc}{location}"
    base = current_url.rstrip("/")
    return f"{base}/{location.lstrip('/')}"


def _is_allowed_github_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return host == "github.com" or host.endswith(".github.com")


def _preview_warning(full_name: str, detail: str) -> ConnectorWarning:
    return ConnectorWarning(
        connector="github",
        code="preview_unavailable",
        message="GitHub repository preview image unavailable",
        detail=f"{full_name}: {detail}"[:300],
    )
