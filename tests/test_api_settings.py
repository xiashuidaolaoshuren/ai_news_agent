"""Tests for /api/v1/settings routes (B6)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ai_news_agent.api.app import create_app
from ai_news_agent.services.composition import build_application


def _client(db_path: Path) -> TestClient:
    application = build_application(fake=True, db_path=db_path)
    return TestClient(create_app(application))


def test_get_settings_sources_lists_hidden_bilibili_and_openrouter_defaults(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path / "settings-get.db")
    response = client.get("/api/v1/settings/sources")
    assert response.status_code == 200
    body = response.json()
    profiles = body["sources"]
    names = [p["name"] for p in profiles]
    assert "bilibili" in names
    assert "openrouter" in names
    bilibili = next(p for p in profiles if p["name"] == "bilibili")
    assert bilibili["hidden"] is True
    openrouter = next(p for p in profiles if p["name"] == "openrouter")
    assert openrouter["free_only"] is False


def test_put_settings_sources_round_trips_github_and_juya_all(tmp_path: Path) -> None:
    client = _client(tmp_path / "settings-put.db")
    gh = client.put(
        "/api/v1/settings/sources/github",
        json={"item_count": 7, "keywords": ["agents"], "min_stars": 10, "language": "Python"},
    )
    assert gh.status_code == 200
    juya = client.put("/api/v1/settings/sources/juya", json={"item_count": "all"})
    assert juya.status_code == 200

    listed = client.get("/api/v1/settings/sources").json()["sources"]
    github = next(p for p in listed if p["name"] == "github")
    assert github["item_count"] == 7
    assert github["keywords"] == ["agents"]
    assert github["min_stars"] == 10
    assert github["language"] == "Python"
    juya_row = next(p for p in listed if p["name"] == "juya")
    assert juya_row["item_count"] == "all"


def test_put_settings_sources_unknown_is_404(tmp_path: Path) -> None:
    client = _client(tmp_path / "settings-404.db")
    response = client.put("/api/v1/settings/sources/nope", json={"item_count": 5})
    assert response.status_code == 404


def test_put_settings_sources_invalid_item_count_is_400(tmp_path: Path) -> None:
    client = _client(tmp_path / "settings-400.db")
    response = client.put("/api/v1/settings/sources/juya", json={"item_count": 0})
    assert response.status_code == 400


def test_get_settings_language_defaults_to_source_default(tmp_path: Path) -> None:
    client = _client(tmp_path / "language-get.db")
    response = client.get("/api/v1/settings/language")
    assert response.status_code == 200
    assert response.json() == {"language": "source_default"}


def test_put_settings_language_round_trips_and_rejects_invalid(tmp_path: Path) -> None:
    client = _client(tmp_path / "language-put.db")
    assert client.put("/api/v1/settings/language", json={"language": "zh-CN"}).status_code == 200
    assert client.get("/api/v1/settings/language").json() == {"language": "zh-CN"}
    assert client.put("/api/v1/settings/language", json={"language": "en"}).status_code == 200
    assert client.get("/api/v1/settings/language").json() == {"language": "en"}
    bad = client.put("/api/v1/settings/language", json={"language": "fr"})
    assert bad.status_code == 400
