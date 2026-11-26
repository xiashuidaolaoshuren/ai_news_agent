"""Tests for /api/v1/settings routes (B6+)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from ai_news_agent.api.app import create_app
from ai_news_agent.credentials import CREDENTIAL_ENV_NAMES
from ai_news_agent.services.composition import build_application


def _client(db_path: Path) -> TestClient:
    application = build_application(fake=True, db_path=db_path)
    return TestClient(create_app(application), client=("127.0.0.1", 50000))


def test_local_live_app_bootstraps_sidecar_and_saves_across_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    monkeypatch.delenv("AI_NEWS_AGENT_SECRET_KEY", raising=False)
    db = tmp_path / "live-bootstrap.db"
    key_file = tmp_path / "live-bootstrap.db.key"

    app = build_application(fake=False, db_path=db)
    client = TestClient(create_app(app), client=("127.0.0.1", 50000))
    listed = client.get("/api/v1/settings/credentials").json()
    assert listed["secret_key_configured"] is True
    assert key_file.exists()

    github = client.put(
        "/api/v1/settings/credentials/GITHUB_TOKEN", json={"value": "ghp_live1234"}
    )
    assert github.status_code == 200
    llm = client.put(
        "/api/v1/settings/credentials/llm",
        json={"api_key": "sk-live-key", "base_url": "https://llm.example/v1", "model": "m"},
    )
    assert llm.status_code == 200

    with sqlite3.connect(db) as conn:
        rows = dict(conn.execute("SELECT name, ciphertext FROM secrets"))
    assert "ghp_live1234" not in rows["GITHUB_TOKEN"]
    assert "sk-live-key" not in rows["OPENAI_API_KEY"]

    restarted = build_application(fake=False, db_path=db)
    client2 = TestClient(create_app(restarted), client=("127.0.0.1", 50000))
    body = client2.get("/api/v1/settings/credentials").json()
    assert body["secret_key_configured"] is True
    by_name = {row["name"]: row for row in body["credentials"]}
    assert by_name["GITHUB_TOKEN"]["status"] == "ui"
    assert by_name["GITHUB_TOKEN"]["last4"] == "1234"
    assert by_name["llm"]["status"] == "ui"
    assert "ghp_live1234" not in str(body)
    assert "sk-live-key" not in str(body)


def test_missing_key_beside_encrypted_rows_warns_without_secret_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cryptography.fernet import Fernet

    from ai_news_agent.credentials import CredentialsProvider, key_file_path_for
    from ai_news_agent.services import composition
    from ai_news_agent.storage import DigestStore

    messages: list[str] = []
    monkeypatch.setattr(
        composition.logger, "warning", lambda fmt, *args: messages.append(fmt % args)
    )
    monkeypatch.delenv("AI_NEWS_AGENT_SECRET_KEY", raising=False)
    db = tmp_path / "recover.db"
    DigestStore(db).init_schema()
    key_file = key_file_path_for(db)
    key_file.write_text(Fernet.generate_key().decode(), encoding="utf-8")
    CredentialsProvider(db, environ={}, key_file=key_file).save(
        "GITHUB_TOKEN", "ghp_recover1234"
    )
    key_file.unlink()

    application = build_application(fake=False, db_path=db)

    assert application.credentials_service.has_secret_key() is False
    assert not key_file.exists()
    assert any(
        "credential key unavailable" in message and "recovery_required" in message
        for message in messages
    )
    assert "ghp_recover1234" not in "".join(messages)


def test_fake_and_remote_apps_never_create_a_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_news_agent.access import AccessConfig

    monkeypatch.delenv("AI_NEWS_AGENT_SECRET_KEY", raising=False)
    fake_db = tmp_path / "fake-no-sidecar.db"
    fake_app = build_application(fake=True, db_path=fake_db)
    fake_client = TestClient(create_app(fake_app), client=("127.0.0.1", 50000))
    assert (
        fake_client.get("/api/v1/settings/credentials").json()["secret_key_configured"]
        is False
    )
    assert not (tmp_path / "fake-no-sidecar.db.key").exists()

    remote_db = tmp_path / "remote-no-sidecar.db"
    remote_app = build_application(
        fake=False,
        db_path=remote_db,
        access=AccessConfig(remote=True, access_token="owner-token"),
    )
    remote_client = TestClient(create_app(remote_app), client=("127.0.0.1", 50000))
    assert (
        remote_client.get(
            "/api/v1/settings/credentials",
            headers={"Authorization": "Bearer owner-token"},
        ).json()["secret_key_configured"]
        is False
    )
    assert not (tmp_path / "remote-no-sidecar.db.key").exists()


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


def test_get_credentials_lists_names_never_values_and_works_keyless(tmp_path: Path) -> None:
    client = _client(tmp_path / "creds-get.db")
    response = client.get("/api/v1/settings/credentials")
    assert response.status_code == 200
    body = response.json()
    assert "secret_key_configured" in body
    assert body["secret_key_configured"] is False
    names = [row["name"] for row in body["credentials"]]
    assert names == list(CREDENTIAL_ENV_NAMES) + ["llm"]
    assert "sk-" not in str(body)
    assert "ghp_" not in str(body)


def test_put_credentials_requires_secret_key_and_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Fernet.generate_key().decode()
    db = tmp_path / "creds-put.db"
    client = _client(db)

    no_key = client.put("/api/v1/settings/credentials/GITHUB_TOKEN", json={"value": "ghp_test1234"})
    assert no_key.status_code == 409

    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", key)
    client2 = _client(db)
    saved = client2.put(
        "/api/v1/settings/credentials/GITHUB_TOKEN",
        json={"value": "ghp_saved5678"},
    )
    assert saved.status_code == 200
    listed = client2.get("/api/v1/settings/credentials").json()
    github = next(c for c in listed["credentials"] if c["name"] == "GITHUB_TOKEN")
    assert github["status"] == "ui"
    assert github["last4"] == "5678"
    assert "ghp_saved5678" not in str(listed)

    deleted = client2.delete("/api/v1/settings/credentials/GITHUB_TOKEN")
    assert deleted.status_code == 204
    after = client2.get("/api/v1/settings/credentials").json()
    github_after = next(c for c in after["credentials"] if c["name"] == "GITHUB_TOKEN")
    assert github_after["status"] in ("env", "unset")


def test_put_credentials_unknown_name_is_404(tmp_path: Path) -> None:
    client = _client(tmp_path / "creds-404.db")
    response = client.put("/api/v1/settings/credentials/NOT_A_NAME", json={"value": "x"})
    assert response.status_code == 404


def test_put_credentials_llm_saves_triple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", key)
    client = _client(tmp_path / "creds-llm.db")
    response = client.put(
        "/api/v1/settings/credentials/llm",
        json={
            "api_key": "sk-ui-llm-key",
            "base_url": "https://llm.example/v1",
            "model": "gpt-test",
        },
    )
    assert response.status_code == 200
    body = client.get("/api/v1/settings/credentials").json()
    llm = next(c for c in body["credentials"] if c["name"] == "llm")
    assert llm["status"] == "ui"
    assert llm["last4"] == "-key"
    assert "sk-ui" not in str(body)
