"""Tests for /api/v1 session and meta routes (Milestone 8A.1 T13–T15)."""

from __future__ import annotations

from pathlib import Path

import pytest


def _build_test_client(*, fake: bool, db_path: Path):
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import build_application

    application = build_application(fake=fake, db_path=db_path)
    return TestClient(create_app(application))


def test_fastapi_shell_surface_importable() -> None:
    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import Application, build_application

    assert Application is not None
    assert callable(build_application)
    assert callable(create_app)


def test_api_v1_health_reports_status_and_fake_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "digest.db"
    client = _build_test_client(fake=True, db_path=db_path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "fake": True}


def test_api_v1_sources_lists_defaults_and_opt_in_metadata(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "digest.db")

    response = client.get("/api/v1/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["defaults"] == ["juya"]
    assert [item["name"] for item in payload["sources"]] == [
        "juya",
        "huggingface",
        "github",
        "zhihu",
        "bilibili",
    ]
    by_name = {item["name"]: item for item in payload["sources"]}
    assert by_name["juya"] == {"name": "juya", "default": True, "opt_in": False}
    assert by_name["github"] == {"name": "github", "default": False, "opt_in": True}


def test_api_v1_allows_loopback_cors_origins_only(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "digest.db")

    for origin in ("http://127.0.0.1:5173", "http://localhost:5173"):
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == origin

    blocked = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert blocked.headers.get("access-control-allow-origin") is None

    wildcard = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert wildcard.headers.get("access-control-allow-origin") != "*"


def test_build_application_fake_skips_live_model_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_news_agent.services.composition import build_application

    calls: list[str] = []

    def _track_build_chat_model() -> object:
        calls.append("build_chat_model")
        return object()

    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_chat_model",
        _track_build_chat_model,
    )

    application = build_application(fake=True, db_path=tmp_path / "digest.db")

    assert application.fake is True
    assert calls == []
    assert application.chat_service is not None
    assert application.session_service is not None


def test_build_application_live_uses_model_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_news_agent.services.composition import build_application

    calls: list[str] = []

    def _track_build_chat_model() -> object:
        calls.append("build_chat_model")
        return object()

    def _track_build_tool_chat_model() -> object:
        calls.append("build_tool_chat_model")
        return object()

    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_chat_model",
        _track_build_chat_model,
    )
    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_tool_chat_model",
        _track_build_tool_chat_model,
    )
    monkeypatch.setattr("ai_news_agent.services.composition.load_local_env", lambda **_: None)
    monkeypatch.setattr(
        "ai_news_agent.services.composition.configure_bilibili_network_from_env",
        lambda _: None,
    )

    application = build_application(fake=False, db_path=tmp_path / "digest.db")

    assert application.fake is False
    assert "build_chat_model" in calls
    assert "build_tool_chat_model" in calls
    assert application.chat_service is not None
