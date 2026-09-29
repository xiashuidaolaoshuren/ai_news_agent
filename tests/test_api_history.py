"""Tests for /api/v1 history routes (Milestone 8A.1 T16)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai_news_agent.connectors.base import ConnectorResult
from ai_news_agent.models import (
    ConfidenceLevel,
    Digest,
    DigestEntry,
    FollowUpAction,
    NewsItem,
    SourceKind,
)


def _build_test_client(*, fake: bool, db_path: Path):
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import build_application

    application = build_application(fake=fake, db_path=db_path)
    return TestClient(create_app(application))


def _make_news_item(
    *,
    source: SourceKind,
    source_id: str,
    title: str,
    url: str,
) -> NewsItem:
    collected = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    return NewsItem(
        source=source,
        source_id=source_id,
        url=url,
        title=title,
        published_at=collected,
        collected_at=collected,
        metadata_completeness=0.8,
        tags=[],
        topic_matches=[],
        content_confidence=ConfidenceLevel.MEDIUM,
    )


def _make_digest_entry(
    *,
    source_kind: SourceKind,
    source_id: str,
    title: str,
    url: str,
    summary: str = "Summary",
) -> DigestEntry:
    return DigestEntry(
        source_kind=source_kind,
        source_id=source_id,
        title=title,
        source_name=source_kind.value,
        source_url=url,
        summary=summary,
        why_it_matters="Why",
        background_knowledge="Background",
        follow_up_action=FollowUpAction.READ,
    )


def _seed_run_with_digest(
    store,
    *,
    generated_at: datetime,
    topics: list[str],
    entries: list[DigestEntry],
    news_items: list[NewsItem] | None = None,
) -> tuple[int, int]:
    collected = datetime(2026, 8, 1, 10, 0, 0, tzinfo=UTC)
    run_id = store.save_run(
        requested_at=collected,
        timeframe="today",
        topics=topics,
        connector_names=[item.source.value for item in (news_items or [])] or ["github"],
    )
    if news_items:
        store.save_connector_result(
            run_id,
            ConnectorResult(items=news_items, warnings=[], raw_count=len(news_items)),
        )
    digest_id = store.save_digest(
        run_id,
        Digest(
            generated_at=generated_at,
            entries=entries,
            topics=topics,
            timeframe="today",
        ),
    )
    return run_id, digest_id


def test_history_search_returns_matches_envelope(tmp_path: Path) -> None:
    from ai_news_agent.storage import DigestStore

    db_path = tmp_path / "history-api.db"
    client = _build_test_client(fake=True, db_path=db_path)
    store = DigestStore(db_path)
    _, digest_id = _seed_run_with_digest(
        store,
        generated_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        topics=["agents"],
        entries=[
            _make_digest_entry(
                source_kind=SourceKind.GITHUB,
                source_id="repo-1",
                title="Transformer agents repo",
                url="https://example.com/repo-1",
                summary="Agents framework",
            )
        ],
    )

    response = client.get("/api/v1/history/search", params={"text": "agents"})

    assert response.status_code == 200
    payload = response.json()
    assert "matches" in payload
    assert "scanned_count" in payload
    assert "archive_truncated" in payload
    assert "caveats" in payload
    assert len(payload["matches"]) == 1
    match = payload["matches"][0]
    assert match["ref"]["token"] == f"d{digest_id}:r1"
    assert match["ref"]["digest_id"] == digest_id
    assert match["title"] == "Transformer agents repo"
    assert match["url"] == "https://example.com/repo-1"
    assert match["source_kind"] == "github"
    assert match["score"] > 0


def test_history_search_validation_maps_value_errors_to_400(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "history-validate.db")

    cases = [
        {"sources": "not-a-source"},
        {"text": "agents", "since": "2026-08-02", "until": "2026-08-01"},
        {"text": "agents", "limit": 51},
        {},
    ]
    for params in cases:
        response = client.get("/api/v1/history/search", params=params)
        assert response.status_code == 400, (params, response.status_code)


def test_history_search_empty_archive_returns_200_empty(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "history-empty.db")

    response = client.get("/api/v1/history/search", params={"text": "agents"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["matches"] == []
    assert payload["caveats"]


def test_history_show_persist_only_markdown_and_errors(tmp_path: Path) -> None:
    from ai_news_agent.history_search import show_historical_item
    from ai_news_agent.storage import DigestStore

    db_path = tmp_path / "history-show.db"
    client = _build_test_client(fake=True, db_path=db_path)
    store = DigestStore(db_path)
    _, digest_id = _seed_run_with_digest(
        store,
        generated_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        topics=["agents"],
        entries=[
            _make_digest_entry(
                source_kind=SourceKind.GITHUB,
                source_id="repo-1",
                title="Transformer agents repo",
                url="https://example.com/repo-1",
                summary="Agents framework",
            )
        ],
    )
    token = f"d{digest_id}:r1"

    response = client.get(f"/api/v1/history/{token}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["token"] == token
    assert payload["markdown"] == show_historical_item(store, token)
    assert "Transformer agents repo" in payload["markdown"]

    malformed = client.get("/api/v1/history/not-a-token")
    assert malformed.status_code == 400

    unknown = client.get("/api/v1/history/d9999:r1")
    assert unknown.status_code == 404

    out_of_range_rank = client.get(f"/api/v1/history/d{digest_id}:r2")
    assert out_of_range_rank.status_code == 404