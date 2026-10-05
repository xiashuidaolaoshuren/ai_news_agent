"""Hugging Face publisher profile lookup for digest presentation metadata."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ai_news_agent.models import ConnectorWarning, NewsItem, SourceKind

HF_PROFILE_BASE = "https://huggingface.co"
OWNER_PROFILE_TIMEOUT = httpx.Timeout(5.0)
OWNER_PROFILE_MAX_CONCURRENT = 4
OWNER_PROFILE_MAX_RESPONSE_BYTES = 256_000


async def enrich_hf_owner_profiles(
    items: list[NewsItem],
    *,
    client: httpx.AsyncClient,
) -> tuple[list[NewsItem], list[ConnectorWarning]]:
    """Attach owner presentation metadata to HF family representatives."""
    hf_items = [item for item in items if item.source is SourceKind.HUGGINGFACE]
    if not hf_items:
        return items, []

    authors = _unique_authors(hf_items)
    if not authors:
        return items, []

    semaphore = asyncio.Semaphore(OWNER_PROFILE_MAX_CONCURRENT)
    cache: dict[str, tuple[dict[str, Any] | None, ConnectorWarning | None]] = {}
    warnings: list[ConnectorWarning] = []

    async def _lookup(author: str) -> None:
        async with semaphore:
            evidence, warning = await _fetch_owner_profile(client, author)
            cache[author] = (evidence, warning)

    await asyncio.gather(*(_lookup(author) for author in authors))

    enriched: list[NewsItem] = []
    for item in items:
        if item.source is not SourceKind.HUGGINGFACE:
            enriched.append(item)
            continue
        author = _item_author(item)
        if not author or author not in cache:
            enriched.append(item)
            continue
        evidence, warning = cache[author]
        if warning is not None:
            warnings.append(warning)
        if not evidence:
            enriched.append(item)
            continue
        merged = {**(item.source_evidence or {}), **evidence}
        enriched.append(item.model_copy(update={"source_evidence": merged}))

    return enriched, warnings


def _unique_authors(items: list[NewsItem]) -> list[str]:
    seen: set[str] = set()
    authors: list[str] = []
    for item in items:
        author = _item_author(item)
        if not author or author in seen:
            continue
        seen.add(author)
        authors.append(author)
    return authors


def _item_author(item: NewsItem) -> str | None:
    author = (item.author or "").strip()
    if author:
        return author
    source_id = (item.source_id or "").strip()
    if "/" in source_id:
        namespace = source_id.split("/", 1)[0].strip()
        return namespace or None
    return None


async def _fetch_owner_profile(
    client: httpx.AsyncClient,
    author: str,
) -> tuple[dict[str, Any] | None, ConnectorWarning | None]:
    org_path = f"/api/organizations/{author}/overview"
    try:
        org_response = await client.get(org_path)
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        return None, _owner_profile_warning(author, str(exc))

    org_result = _parse_profile_response(org_response, author, owner_type="organisation")
    if org_result is not None:
        return org_result, None

    if org_response.status_code != 404:
        return None, _owner_profile_warning(
            author,
            f"organization overview HTTP {org_response.status_code}",
        )

    user_path = f"/api/users/{author}/overview"
    try:
        user_response = await client.get(user_path)
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        return None, _owner_profile_warning(author, str(exc))

    user_result = _parse_profile_response(user_response, author, owner_type="person")
    if user_result is not None:
        return user_result, None

    if user_response.status_code == 404:
        return None, None

    return None, _owner_profile_warning(
        author,
        f"user overview HTTP {user_response.status_code}",
    )


def _parse_profile_response(
    response: httpx.Response,
    author: str,
    *,
    owner_type: str,
) -> dict[str, Any] | None:
    if response.status_code != 200:
        return None
    if len(response.content) > OWNER_PROFILE_MAX_RESPONSE_BYTES:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    name = str(payload.get("name") or payload.get("user") or author).strip()
    if not name:
        return None

    evidence: dict[str, Any] = {
        "owner_name": name,
        "owner_profile_url": f"{HF_PROFILE_BASE}/{name}",
        "owner_type": owner_type,
    }
    avatar = payload.get("avatarUrl") or payload.get("avatar")
    if avatar:
        avatar_text = str(avatar).strip()
        if avatar_text.startswith(("http://", "https://")):
            evidence["owner_avatar_url"] = avatar_text
    return evidence


def _owner_profile_warning(author: str, detail: str) -> ConnectorWarning:
    return ConnectorWarning(
        connector="huggingface",
        code="owner_profile_unavailable",
        message="Hugging Face owner profile lookup unavailable",
        detail=f"{author}: {detail}"[:300],
    )
