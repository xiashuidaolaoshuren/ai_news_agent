"""OpenRouter connector: callable model listings via GET /api/v1/models (B1)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ai_news_agent.connectors.base import ConnectorRequest, ConnectorResult
from ai_news_agent.connectors.juya import _text_matches_topic
from ai_news_agent.models import ConfidenceLevel, ConnectorWarning, NewsItem, SourceKind
from ai_news_agent.ranking import within_timeframe

SNIPPET_MAX = 650


def _parse_created_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if text.isdigit():
                return datetime.fromtimestamp(float(text), tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _price_per_million(raw: Any) -> tuple[str | None, bool | None]:
    """Return (per-million string, is_known_zero). None bool means unknown price."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None, None
    if d < 0:
        return None, None
    is_zero = d == 0
    scaled = d * Decimal(1_000_000)
    formatted = format(scaled, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0", is_zero


def _free_token_pricing(prompt_zero: bool | None, completion_zero: bool | None) -> bool:
    return prompt_zero is True and completion_zero is True


def _provider_from_id(model_id: str) -> str | None:
    if "/" not in model_id:
        return None
    prefix = model_id.split("/", 1)[0].strip()
    return prefix or None


def _model_to_news_item(model: dict[str, Any], collected_at: datetime) -> NewsItem | None:
    model_id = str(model.get("id") or "").strip()
    if not model_id:
        return None
    name = str(model.get("name") or "").strip() or model_id
    description = str(model.get("description") or "").strip() or None
    if description and len(description) > SNIPPET_MAX:
        description = description[:SNIPPET_MAX]
    published_at = _parse_created_ts(model.get("created"))
    pricing = model.get("pricing") or {}
    prompt_pm, prompt_zero = _price_per_million(pricing.get("prompt"))
    completion_pm, completion_zero = _price_per_million(pricing.get("completion"))
    free_pricing = _free_token_pricing(prompt_zero, completion_zero)
    arch = model.get("architecture") or {}
    modalities = arch.get("input_modalities")
    input_modalities = (
        [str(m) for m in modalities if m is not None]
        if isinstance(modalities, list)
        else []
    )
    ctx = model.get("context_length")
    context_length: int | None
    try:
        context_length = int(ctx) if ctx is not None else None
    except (TypeError, ValueError):
        context_length = None
    evidence: dict[str, Any] = {
        "created": (published_at.date().isoformat() if published_at else None),
        "context_length": context_length,
        "prompt_price_per_million": prompt_pm,
        "completion_price_per_million": completion_pm,
        "free_token_pricing": free_pricing,
        "input_modalities": input_modalities,
    }
    provider = _provider_from_id(model_id)
    if provider:
        evidence["provider"] = provider
    if model_id.endswith(":free"):
        evidence["free_route_suffix"] = ":free"
    return NewsItem(
        source=SourceKind.OPENROUTER,
        source_id=model_id,
        url=f"https://openrouter.ai/{model_id}",
        title=name,
        published_at=published_at,
        collected_at=collected_at,
        raw_snippet=description,
        metadata_completeness=0.5 if description else 0.35,
        content_confidence=ConfidenceLevel.MEDIUM if description else ConfidenceLevel.LOW,
        source_evidence=evidence,
    )


def _request_failed_warning(detail: str) -> ConnectorWarning:
    return ConnectorWarning(
        connector="openrouter",
        code="request_failed",
        message="OpenRouter models request failed",
        detail=detail[:300],
    )


def _matches_topics(model: dict[str, Any], topics: list[str]) -> bool:
    haystack = " ".join(
        [
            str(model.get("id") or ""),
            str(model.get("name") or ""),
            str(model.get("description") or ""),
        ]
    )
    return any(_text_matches_topic(haystack, topic) for topic in topics if topic.strip())


class OpenRouterConnector:
    """Collects callable model listings from OpenRouter."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client
        self._now = now or (lambda: datetime.now(UTC))

    def name(self) -> str:
        return "openrouter"

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def collect(self, request: ConnectorRequest) -> ConnectorResult:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://openrouter.ai",
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": "ai-news-agent/0.1"},
            )
            self._owns_client = True
        client = self._client
        try:
            resp = await client.get("/api/v1/models")
        except httpx.RequestError as exc:
            return ConnectorResult(
                items=[],
                warnings=[_request_failed_warning(f"{type(exc).__name__}: {exc}")],
                raw_count=0,
            )
        if resp.status_code < 200 or resp.status_code >= 300:
            return ConnectorResult(
                items=[],
                warnings=[
                    _request_failed_warning(f"HTTP {resp.status_code}: {resp.text[:200]}")
                ],
                raw_count=0,
            )
        try:
            body = resp.json()
        except ValueError as exc:
            return ConnectorResult(
                items=[],
                warnings=[_request_failed_warning(f"invalid JSON: {exc}")],
                raw_count=0,
            )
        models = body.get("data")
        if not isinstance(models, list):
            return ConnectorResult(
                items=[],
                warnings=[_request_failed_warning("response data is not a list")],
                raw_count=0,
            )
        raw_count = len(models)
        collected_at = self._now()
        effective_timeframe = request.timeframe if request.timeframe else "last_7_days"
        items: list[NewsItem] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            item = _model_to_news_item(model, collected_at)
            if item is None:
                continue
            if item.published_at is None:
                if effective_timeframe:
                    continue
            elif not within_timeframe(item, effective_timeframe, collected_at):
                continue
            if request.topics_are_filters and request.topics:
                if not _matches_topics(model, request.topics):
                    continue
            if request.free_only and not (item.source_evidence or {}).get(
                "free_token_pricing"
            ):
                continue
            items.append(item)
        return ConnectorResult(items=items, warnings=[], raw_count=raw_count)

