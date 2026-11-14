"""Tests for OpenRouterConnector (B1)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from ai_news_agent.connectors.openrouter import OpenRouterConnector
from ai_news_agent.connectors.base import ConnectorRequest
from ai_news_agent.models import SourceKind

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES / name
    with path.open(encoding="utf-8") as f:
        return json.load(f)


FIXED_NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)


def _models_transport(
    payload: dict[str, Any],
    *,
    status: int = 200,
    text: str | None = None,
    error: Exception | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if error is not None:
            raise error
        if request.url.path != "/api/v1/models":
            return httpx.Response(404)
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler)


async def _collect(
    payload: dict[str, Any],
    request: ConnectorRequest,
    *,
    now: datetime | None = None,
    status: int = 200,
    text: str | None = None,
    error: Exception | None = None,
) -> Any:
    transport = _models_transport(payload, status=status, text=text, error=error)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://openrouter.ai",
    ) as client:
        conn = OpenRouterConnector(client=client, now=(lambda: now or FIXED_NOW))
        return await conn.collect(request)


def test_collect_maps_zero_priced_row_to_news_item() -> None:
    fixture = _load_fixture("openrouter_models_sample.json")
    zero = next(
        m
        for m in fixture["data"]
        if m.get("pricing", {}).get("prompt") == "0"
        and m.get("pricing", {}).get("completion") == "0"
    )
    payload = {"data": [zero]}

    async def main() -> None:
        # Explicit wide window so fallback is not involved.
        out = await _collect(
            payload,
            ConnectorRequest(topics=[], timeframe="last_30_days"),
        )
        assert len(out.items) == 1
        item = out.items[0]
        assert item.source is SourceKind.OPENROUTER
        assert item.source_id == zero["id"]
        assert item.title == zero["name"]
        assert item.url == f"https://openrouter.ai/{zero['id']}"
        assert item.published_at is not None
        ev = item.source_evidence
        assert ev["free_token_pricing"] is True
        assert ev["prompt_price_per_million"] == "0"
        assert ev["completion_price_per_million"] == "0"
        assert ev["provider"] == zero["id"].split("/", 1)[0]
        assert ev["context_length"] == zero["context_length"]
        assert ev["input_modalities"] == zero["architecture"]["input_modalities"]
        assert "created" in ev
        assert out.raw_count == 1
        assert not out.warnings

    asyncio.run(main())


def test_free_suffix_without_zero_prices_is_not_free_token_pricing() -> None:
    recent = int(FIXED_NOW.timestamp()) - 3600
    row = {
        "id": "vendor/demo:free",
        "name": "Demo Free Route",
        "created": recent,
        "description": "priced despite suffix",
        "context_length": 8192,
        "architecture": {"input_modalities": ["text"]},
        "pricing": {"prompt": "0.000001", "completion": "0"},
    }

    async def main() -> None:
        out = await _collect(
            {"data": [row]},
            ConnectorRequest(topics=[], timeframe="last_7_days"),
        )
        assert len(out.items) == 1
        ev = out.items[0].source_evidence
        assert ev["free_route_suffix"] == ":free"
        assert ev["free_token_pricing"] is False

    asyncio.run(main())


def test_unknown_prices_stay_null_not_zero() -> None:
    from ai_news_agent.connectors.openrouter import _price_per_million

    assert _price_per_million(None) == (None, None)
    assert _price_per_million("") == (None, None)
    assert _price_per_million("nope") == (None, None)
    assert _price_per_million("-1") == (None, None)


def test_per_token_price_scales_to_per_million() -> None:
    from ai_news_agent.connectors.openrouter import _price_per_million

    assert _price_per_million("0.0000025") == ("2.5", False)
    assert _price_per_million("0") == ("0", True)


def test_collect_scales_priced_fixture_row() -> None:
    fixture = _load_fixture("openrouter_models_sample.json")
    priced = next(m for m in fixture["data"] if m.get("pricing", {}).get("prompt") not in (None, "0"))

    async def main() -> None:
        out = await _collect(
            {"data": [priced]},
            ConnectorRequest(topics=[], timeframe="last_30_days"),
        )
        assert len(out.items) == 1
        ev = out.items[0].source_evidence
        assert ev["free_token_pricing"] is False
        assert ev["prompt_price_per_million"] == "0.12"
        assert ev["completion_price_per_million"] == "0.4"

    asyncio.run(main())


def test_timeframe_filters_created_and_default_is_last_7_days() -> None:
    recent = int(FIXED_NOW.timestamp()) - 3600
    old = int((FIXED_NOW.replace(year=2020)).timestamp())
    rows = [
        {
            "id": "a/in",
            "name": "In",
            "created": recent,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": []},
        },
        {
            "id": "b/out",
            "name": "Out",
            "created": old,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": []},
        },
    ]

    async def main() -> None:
        explicit = await _collect(
            {"data": rows},
            ConnectorRequest(topics=[], timeframe="last_7_days"),
        )
        assert [i.source_id for i in explicit.items] == ["a/in"]

        fallback = await _collect({"data": rows}, ConnectorRequest(topics=[]))
        assert [i.source_id for i in fallback.items] == ["a/in"]

    asyncio.run(main())


def test_topics_filter_only_when_topics_are_filters() -> None:
    recent = int(FIXED_NOW.timestamp()) - 3600
    row = {
        "id": "lab/cn-model",
        "name": "CN",
        "created": recent,
        "description": "该条目讨论大语言模型训练",
        "pricing": {"prompt": "0", "completion": "0"},
        "architecture": {"input_modalities": ["text"]},
    }

    async def main() -> None:
        off = await _collect(
            {"data": [row]},
            ConnectorRequest(topics=["model"], topics_are_filters=False, timeframe="last_7_days"),
        )
        assert len(off.items) == 1
        on = await _collect(
            {"data": [row]},
            ConnectorRequest(topics=["model"], topics_are_filters=True, timeframe="last_7_days"),
        )
        assert len(on.items) == 1
        miss = await _collect(
            {"data": [row]},
            ConnectorRequest(topics=["quantum"], topics_are_filters=True, timeframe="last_7_days"),
        )
        assert miss.items == []

    asyncio.run(main())


def test_collect_caps_items_to_max_items_keeping_newest() -> None:
    newest = int(FIXED_NOW.timestamp()) - 60
    middle = int(FIXED_NOW.timestamp()) - 3600
    oldest = int(FIXED_NOW.timestamp()) - 7200
    rows = [
        {
            "id": "lab/oldest",
            "name": "Oldest",
            "created": oldest,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": []},
        },
        {
            "id": "lab/newest",
            "name": "Newest",
            "created": newest,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": []},
        },
        {
            "id": "lab/middle",
            "name": "Middle",
            "created": middle,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": []},
        },
    ]

    async def main() -> None:
        capped = await _collect(
            {"data": rows},
            ConnectorRequest(topics=[], timeframe="last_7_days", max_items=2),
        )
        assert [i.source_id for i in capped.items] == ["lab/newest", "lab/middle"]
        assert capped.raw_count == 3

        uncapped = await _collect(
            {"data": rows},
            ConnectorRequest(topics=[], timeframe="last_7_days"),
        )
        assert len(uncapped.items) == 3

    asyncio.run(main())


def test_free_only_flag_on_request() -> None:
    recent = int(FIXED_NOW.timestamp()) - 3600
    rows = [
        {
            "id": "z/free",
            "name": "Free",
            "created": recent,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": []},
        },
        {
            "id": "z/paid",
            "name": "Paid",
            "created": recent,
            "pricing": {"prompt": "0.000001", "completion": "0.000001"},
            "architecture": {"input_modalities": []},
        },
    ]
    assert ConnectorRequest(topics=[]).free_only is False

    async def main() -> None:
        all_rows = await _collect(
            {"data": rows},
            ConnectorRequest(topics=[], timeframe="last_7_days", free_only=False),
        )
        assert len(all_rows.items) == 2
        only_free = await _collect(
            {"data": rows},
            ConnectorRequest(topics=[], timeframe="last_7_days", free_only=True),
        )
        assert [i.source_id for i in only_free.items] == ["z/free"]

    asyncio.run(main())


def test_request_failures_emit_single_request_failed_warning() -> None:
    recent = int(FIXED_NOW.timestamp()) - 3600
    one = {
        "data": [
            {
                "id": "ok/x",
                "name": "Ok",
                "created": recent,
                "pricing": {"prompt": "0", "completion": "0"},
                "architecture": {"input_modalities": []},
            }
        ]
    }

    async def main() -> None:
        http = await _collect(one, ConnectorRequest(topics=[]), status=503)
        assert http.items == [] and len(http.warnings) == 1
        assert http.warnings[0].code == "request_failed"
        assert http.warnings[0].connector == "openrouter"

        timeout = await _collect(
            one,
            ConnectorRequest(topics=[]),
            error=httpx.ReadTimeout("t"),
        )
        assert timeout.items == [] and timeout.warnings[0].code == "request_failed"

        bad_json = await _collect(one, ConnectorRequest(topics=[]), text="not-json")
        assert bad_json.items == [] and bad_json.warnings[0].code == "request_failed"

        bad_shape = await _collect({"data": "x"}, ConnectorRequest(topics=[]))
        assert bad_shape.items == [] and bad_shape.warnings[0].code == "request_failed"

    asyncio.run(main())


def test_empty_filter_result_is_not_failure() -> None:
    old = int((FIXED_NOW.replace(year=2020)).timestamp())
    row = {
        "id": "old/x",
        "name": "Old",
        "created": old,
        "pricing": {"prompt": "0", "completion": "0"},
        "architecture": {"input_modalities": []},
    }

    async def main() -> None:
        out = await _collect({"data": [row]}, ConnectorRequest(topics=[]))
        assert out.items == []
        assert out.warnings == []
        assert out.raw_count == 1

    asyncio.run(main())


def _priced_row(model_id: str, created: int | None) -> dict[str, Any]:
    return {
        "id": model_id,
        "name": model_id,
        "created": created,
        "description": f"{model_id} listing",
        "pricing": {"prompt": "0", "completion": "0"},
        "architecture": {"input_modalities": []},
    }


def test_empty_non_strict_short_window_falls_back_to_last_7_days() -> None:
    calls = 0
    yesterday = int(FIXED_NOW.timestamp()) - 86_400
    today = int(FIXED_NOW.timestamp()) - 60
    outside = int((FIXED_NOW.replace(year=2020)).timestamp())
    payload = {
        "data": [
            _priced_row("lab/yesterday", yesterday),
            _priced_row("lab/outside", outside),
            _priced_row("lab/undated", None),
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/api/v1/models"
        return httpx.Response(200, json=payload)

    async def main() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://openrouter.ai",
        ) as client:
            conn = OpenRouterConnector(client=client, now=(lambda: FIXED_NOW))
            request = ConnectorRequest(topics=[], timeframe="today", max_items=5)
            out = await conn.collect(request)

        assert [item.source_id for item in out.items] == ["lab/yesterday"]
        assert out.raw_count == 3
        assert calls == 1
        assert len(out.warnings) == 1
        warning = out.warnings[0]
        assert warning.connector == "openrouter"
        assert warning.code == "window_widened"
        assert warning.message == (
            "No models matched the requested window; showing matching listings "
            "from the last 7 days instead."
        )
        assert json.loads(warning.detail or "") == {
            "requested_timeframe": "today",
            "effective_timeframe": "last_7_days",
        }
        assert request.timeframe == "today"

        today_payload = {"data": [_priced_row("lab/today", today)]}
        explicit_today = await _collect(
            today_payload,
            ConnectorRequest(topics=[], timeframe="today", max_items=5),
        )
        assert [item.source_id for item in explicit_today.items] == ["lab/today"]
        assert explicit_today.warnings == []

    asyncio.run(main())


def test_window_fallback_keeps_filters_bounds_and_failure_behavior() -> None:
    yesterday = int(FIXED_NOW.timestamp()) - 86_400
    older = int(FIXED_NOW.timestamp()) - 2 * 86_400
    today = int(FIXED_NOW.timestamp()) - 60
    window_start = int(datetime(2026, 11, 3, 0, 0, tzinfo=UTC).timestamp())
    before_window = window_start - 1
    rows = [
        _priced_row("lab/older-match", older),
        _priced_row("lab/yesterday-match", yesterday),
        {
            **_priced_row("lab/yesterday-paid", yesterday),
            "pricing": {"prompt": "0.000001", "completion": "0.000001"},
        },
        {
            **_priced_row("lab/yesterday-other", yesterday),
            "description": "unrelated quantum listing",
        },
        _priced_row("lab/before-window", before_window),
    ]

    async def main() -> None:
        fallback = await _collect(
            {"data": rows},
            ConnectorRequest(
                topics=["match"],
                topics_are_filters=True,
                timeframe="today",
                free_only=True,
                max_items=1,
            ),
        )
        assert [item.source_id for item in fallback.items] == ["lab/yesterday-match"]
        assert [warning.code for warning in fallback.warnings] == ["window_widened"]

        strict = ConnectorRequest(
            topics=[],
            timeframe="today",
            strict_timeframe=True,
        )
        strict_out = await _collect({"data": rows}, strict)
        assert strict_out.items == []
        assert strict_out.warnings == []
        assert strict.timeframe == "today"
        assert strict.strict_timeframe is True

        no_match = await _collect(
            {"data": [_priced_row("lab/old", before_window)]},
            ConnectorRequest(topics=[], timeframe="today"),
        )
        assert no_match.items == []
        assert no_match.warnings == []

        previous_week = int(datetime(2026, 11, 8, 12, 0, tzinfo=UTC).timestamp())
        short_week = await _collect(
            {"data": [_priced_row("lab/yesterday-match", previous_week)]},
            ConnectorRequest(topics=[], timeframe="this_week"),
            now=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
        )
        assert [item.source_id for item in short_week.items] == ["lab/yesterday-match"]
        assert [warning.code for warning in short_week.warnings] == ["window_widened"]

        for timeframe in (None, "last_7_days", "last_30_days", "latest"):
            unchanged = await _collect(
                {"data": [_priced_row("lab/old", before_window)]},
                ConnectorRequest(topics=[], timeframe=timeframe),
            )
            assert [warning.code for warning in unchanged.warnings] != ["window_widened"]

        failed = await _collect(
            {"data": rows},
            ConnectorRequest(topics=[], timeframe="today"),
            status=503,
        )
        assert failed.items == []
        assert [warning.code for warning in failed.warnings] == ["request_failed"]

    asyncio.run(main())


def test_skips_blank_id_without_failing_payload() -> None:
    recent = int(FIXED_NOW.timestamp()) - 3600
    rows = [
        {"id": "  ", "name": "Bad", "created": recent, "pricing": {"prompt": "0", "completion": "0"}, "architecture": {"input_modalities": []}},
        {
            "id": "good/x",
            "name": "Good",
            "created": recent,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": []},
        },
    ]

    async def main() -> None:
        out = await _collect({"data": rows}, ConnectorRequest(topics=[], timeframe="last_7_days"))
        assert len(out.items) == 1
        assert out.items[0].source_id == "good/x"
        assert not out.warnings
        assert out.raw_count == 2

    asyncio.run(main())

