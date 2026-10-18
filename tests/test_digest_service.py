"""Tests for the persistent local HTTP service entry point."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_news_agent.app import digest_service


def test_materialize_fake_db_leaves_source_bytes_unchanged(tmp_path: Path) -> None:
    from ai_news_agent.app.fake_runtime_db import materialize_fake_db, remove_fake_runtime_db
    from ai_news_agent.dev.prototype_demo import seed_prototype_demo
    from ai_news_agent.repositories.session_store import SessionStore

    source = tmp_path / "prototype.sqlite"
    seed_prototype_demo(source)
    before = source.read_bytes()

    runtime_db = materialize_fake_db(source)
    try:
        SessionStore(runtime_db).create_session("runtime-only")
        assert runtime_db.exists()
        assert source.read_bytes() == before
    finally:
        remove_fake_runtime_db(runtime_db)


def test_materialize_fake_db_does_not_create_missing_source(tmp_path: Path) -> None:
    from ai_news_agent.app.fake_runtime_db import materialize_fake_db, remove_fake_runtime_db

    source = tmp_path / "missing.sqlite"
    runtime_db = materialize_fake_db(source)
    try:
        assert not source.exists()
        assert runtime_db.exists()
    finally:
        remove_fake_runtime_db(runtime_db)


def test_main_runs_uvicorn_with_composition_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

    from ai_news_agent.dev.prototype_demo import seed_prototype_demo

    source = tmp_path / "main.db"
    seed_prototype_demo(source)
    source_bytes = source.read_bytes()

    captured: dict[str, object] = {}

    def fake_run(app: object, **kwargs: object) -> None:
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(digest_service, "load_local_env", lambda **kw: None)
    monkeypatch.setattr(
        digest_service,
        "configure_bilibili_network_from_env",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(digest_service, "configure_logging", lambda *args, **kwargs: None)

    code = digest_service.main(
        [
            "--fake",
            "--host",
            "127.0.0.1",
            "--port",
            "9999",
            "--db-path",
            str(source),
        ]
    )

    assert code == 0
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["port"] == 9999
    paths = {route.path for route in captured["app"].routes}
    assert {"/api/v1/health", "/api/v1/sessions"} <= paths
    assert any(path.startswith("/api/v1/history") for path in paths)
    assert "/digest" not in paths
    assert "/followup" not in paths
    application = captured["app"].state.application
    assert application.db_path.resolve() != source.resolve()
    assert source.read_bytes() == source_bytes
