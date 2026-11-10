"""Tests for CredentialsProvider (B9) and credential health (B10)."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

from ai_news_agent.credential_health import (
    CredentialHealthStore,
    health_version_for_source,
    record_connector_health_from_digest,
    summary_for_catalog_source,
)
from ai_news_agent.credential_tests import classify_probe_outcome, probe_github
from ai_news_agent.credentials import (
    CREDENTIAL_ENV_NAMES,
    LLM_ENV_NAMES,
    CredentialsProvider,
    MissingSecretKeyError,
)
from ai_news_agent.models import ConnectorWarning
from ai_news_agent.storage import DigestStore


def _provider(
    db_path: Path,
    *,
    environ: dict[str, str] | None = None,
    secret_key: str | None = None,
) -> CredentialsProvider:
    DigestStore(db_path).init_schema()
    env = dict(environ or {})
    if secret_key is not None:
        env["AI_NEWS_AGENT_SECRET_KEY"] = secret_key
    return CredentialsProvider(db_path, environ=env)


def test_save_override_wins_over_env_and_exposes_last4_and_version(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode()
    db = tmp_path / "creds.db"
    env = {"GITHUB_TOKEN": "env-token-aaaa", "AI_NEWS_AGENT_SECRET_KEY": key}
    provider = _provider(db, environ=env, secret_key=key)
    provider.save("GITHUB_TOKEN", "ui-token-bbbb")

    resolved = provider.resolve("GITHUB_TOKEN")
    assert resolved.status == "ui"
    assert resolved.value == "ui-token-bbbb"
    assert resolved.last4 == "bbbb"
    assert resolved.version is not None
    assert len(resolved.version) == 16

    provider.delete("GITHUB_TOKEN")
    after = provider.resolve("GITHUB_TOKEN")
    assert after.status == "env"
    assert after.value == "env-token-aaaa"


def test_unreadable_override_does_not_fall_back_to_env(tmp_path: Path) -> None:
    key1 = Fernet.generate_key().decode()
    db = tmp_path / "unreadable.db"
    provider1 = _provider(
        db,
        environ={"GITHUB_TOKEN": "env-fallback", "AI_NEWS_AGENT_SECRET_KEY": key1},
        secret_key=key1,
    )
    provider1.save("GITHUB_TOKEN", "stored-secret-xyz1")

    provider2 = _provider(db, environ={"GITHUB_TOKEN": "env-fallback"})
    resolved = provider2.resolve("GITHUB_TOKEN")
    assert resolved.status == "unreadable"
    assert resolved.value is None

    provider2.delete("GITHUB_TOKEN")
    restored = provider2.resolve("GITHUB_TOKEN")
    assert restored.status == "env"
    assert restored.value == "env-fallback"


def test_save_llm_atomic_blank_api_key_rejected_and_delete_llm_restores_env(
    tmp_path: Path,
) -> None:
    key = Fernet.generate_key().decode()
    db = tmp_path / "llm.db"
    env = {
        "OPENAI_API_KEY": "sk-env-key",
        "OPENAI_BASE_URL": "https://env.example/v1",
        "OPENAI_MODEL": "env-model",
        "AI_NEWS_AGENT_SECRET_KEY": key,
    }
    provider = _provider(db, environ=env, secret_key=key)

    with pytest.raises(ValueError):
        provider.save_llm(api_key="   ")

    for name in LLM_ENV_NAMES:
        assert provider.resolve(name).status == "env"

    provider.save_llm(
        api_key="sk-ui-key",
        base_url="https://ui.example/v1",
        model="ui-model",
    )
    llm = provider.resolve_llm()
    assert llm.status == "ui"
    assert llm.api_key == "sk-ui-key"
    assert llm.base_url == "https://ui.example/v1"
    assert llm.model == "ui-model"

    provider.delete_llm()
    llm_after = provider.resolve_llm()
    assert llm_after.status == "env"
    assert llm_after.api_key == "sk-env-key"


def test_save_without_secret_key_raises(tmp_path: Path) -> None:
    provider = _provider(tmp_path / "nokey.db", environ={})
    with pytest.raises(MissingSecretKeyError):
        provider.save("GITHUB_TOKEN", "x")


def test_statuses_lists_six_env_names_then_llm(tmp_path: Path) -> None:
    provider = _provider(tmp_path / "status.db", environ={})
    names = [row.name for row in provider.statuses()]
    assert names == list(CREDENTIAL_ENV_NAMES) + ["llm"]


def test_build_connectors_passes_provider_github_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_news_agent.connectors.github import GitHubConnector
    from ai_news_agent.sources import build_connectors

    key = Fernet.generate_key().decode()
    provider = _provider(
        tmp_path / "conn.db",
        environ={"GITHUB_TOKEN": "env-should-not-win", "AI_NEWS_AGENT_SECRET_KEY": key},
        secret_key=key,
    )
    provider.save("GITHUB_TOKEN", "ui-github-token")

    captured: list[str | None] = []
    original_init = GitHubConnector.__init__

    def _capture_init(self, *args, **kwargs):  # noqa: ANN001, ANN002
        captured.append(kwargs.get("token"))
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(GitHubConnector, "__init__", _capture_init)

    build_connectors(fake=False, names=["github"], credentials=provider)
    assert captured == ["ui-github-token"]


def test_build_connectors_unreadable_github_is_blocked(tmp_path: Path) -> None:
    from ai_news_agent.connectors.base import ConnectorRequest
    from ai_news_agent.sources import build_connectors

    key1 = Fernet.generate_key().decode()
    db = tmp_path / "blocked.db"
    provider1 = _provider(
        db,
        environ={"AI_NEWS_AGENT_SECRET_KEY": key1},
        secret_key=key1,
    )
    provider1.save("GITHUB_TOKEN", "secret")
    provider2 = _provider(db, environ={})

    connector = build_connectors(fake=False, names=["github"], credentials=provider2)[0]
    import asyncio

    result = asyncio.run(
        connector.collect(
            ConnectorRequest(topics=["agents"], max_items=5),
        )
    )
    assert result.items == []
    assert any(w.code == "credential_unreadable" for w in result.warnings)


def test_build_application_live_without_openai_env_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_news_agent.services.composition import _LazyToolProxy, build_application

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    application = build_application(fake=False, db_path=tmp_path / "live-no-llm.db")
    assert application.chat_service is not None
    router = application.chat_service._interface_router
    assert isinstance(router._tool_model, _LazyToolProxy)


def test_lazy_tool_proxy_resolves_the_current_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cryptography.fernet import Fernet

    from ai_news_agent.services import composition
    from ai_news_agent.services.composition import _LLM_UNCONFIGURED_MESSAGE, build_application

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", key)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    db = tmp_path / "lazy-tool.db"
    models: list[object] = []

    class _Model:
        def __init__(self, name: str) -> None:
            self.name = name

        def bind_tools(self, tools: object) -> "_Model":
            del tools
            return self

    def _build_tool_chat_model(**_kwargs: object) -> _Model:
        model = _Model("A" if len(models) == 0 else "B")
        models.append(model)
        return model

    monkeypatch.setattr(composition, "build_chat_model", lambda **_kwargs: object())
    monkeypatch.setattr(composition, "build_tool_chat_model", _build_tool_chat_model)

    application = build_application(fake=False, db_path=db)
    proxy = application.chat_service._interface_router._tool_model
    with pytest.raises(ValueError, match=re.escape(_LLM_UNCONFIGURED_MESSAGE)):
        proxy.bind_tools([])

    application.credentials_service.save_llm(api_key="sk-first")
    assert proxy.bind_tools([]).name == "A"
    application.credentials_service.save_llm(api_key="sk-second")
    assert proxy.bind_tools([]).name == "B"


def test_build_application_uses_saved_llm_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_news_agent.services import composition
    from ai_news_agent.services.composition import build_application

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", key)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    db = tmp_path / "llm-app.db"
    provider = _provider(db, environ={"AI_NEWS_AGENT_SECRET_KEY": key}, secret_key=key)
    provider.save_llm(api_key="sk-saved", base_url="https://saved/v1", model="saved-model")

    build_calls: list[dict[str, str | None]] = []

    def _capture_build_chat_model(**kwargs):  # noqa: ANN003
        build_calls.append(kwargs)
        return object()

    monkeypatch.setattr(composition, "build_chat_model", _capture_build_chat_model)
    monkeypatch.setattr(composition, "build_tool_chat_model", lambda **_: object())

    application = build_application(fake=False, db_path=db)
    assert application.chat_service is not None
    chat_model, _tool = application.chat_service._chat_model._holder.get()
    assert chat_model is not None
    assert build_calls
    assert build_calls[0]["api_key"] == "sk-saved"


def test_cli_digest_exits_when_llm_unconfigured(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    from argparse import Namespace

    from ai_news_agent.cli import _run_digest_command

    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    db = tmp_path / "cli-no-llm.db"
    ns = Namespace(
        db_path=db,
        fake=False,
        sources="juya",
        topics=None,
        top_n=None,
        max_items=None,
        output_style=None,
        output_language=None,
    )
    code = _run_digest_command(ns, stdout=open(os.devnull, "w", encoding="utf-8"))
    assert code == 2
    assert "Configure an LLM in Settings" in capsys.readouterr().err


def test_cli_digest_exits_when_override_unreadable(tmp_path: Path, capsys) -> None:
    from argparse import Namespace

    from ai_news_agent.cli import _run_digest_command

    key1 = Fernet.generate_key().decode()
    db = tmp_path / "cli-unread.db"
    provider1 = _provider(
        db,
        environ={"OPENAI_API_KEY": "sk-x", "AI_NEWS_AGENT_SECRET_KEY": key1},
        secret_key=key1,
    )
    provider1.save_llm(api_key="sk-stored")

    ns = Namespace(
        db_path=db,
        fake=False,
        sources="juya",
        topics=None,
        top_n=None,
        max_items=None,
        output_style=None,
        output_language=None,
    )
    code = _run_digest_command(ns, stdout=open(os.devnull, "w", encoding="utf-8"))
    assert code == 2
    assert "AI_NEWS_AGENT_SECRET_KEY" in capsys.readouterr().err


def test_cli_digest_uses_saved_llm_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from argparse import Namespace
    from io import StringIO

    from ai_news_agent.cli import _run_digest_command

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", key)
    db = tmp_path / "cli-ok.db"
    provider = _provider(
        db,
        environ={"AI_NEWS_AGENT_SECRET_KEY": key},
        secret_key=key,
    )
    provider.save_llm(api_key="sk-cli-override")

    build_calls: list[dict[str, str | None]] = []

    def _fake_build(**kwargs):  # noqa: ANN003
        build_calls.append(kwargs)
        return object()

    class _FakeResult:
        text = "done\n"
        run_id = 1
        warnings: list = []
        errors: list = []

    async def _fake_run(_req, **kwargs):  # noqa: ANN003, ARG001, ANN002
        return _FakeResult()

    monkeypatch.setattr("ai_news_agent.cli.build_chat_model", _fake_build)
    monkeypatch.setattr("ai_news_agent.cli._run_digest_async", _fake_run)

    ns = Namespace(
        db_path=db,
        fake=False,
        sources="juya",
        topics=None,
        top_n=None,
        max_items=None,
        output_style=None,
        output_language=None,
    )
    out = StringIO()
    code = _run_digest_command(ns, stdout=out)
    assert code == 0
    assert build_calls[0]["api_key"] == "sk-cli-override"


def _health_db(path: Path) -> CredentialHealthStore:
    DigestStore(path).init_schema()
    return CredentialHealthStore(path)


def test_health_store_newest_wins_and_ok_supersedes_auth_error(tmp_path: Path) -> None:
    store = _health_db(tmp_path / "health.db")
    version = "abc123"
    store.record(source="github", credential_version=version, kind="test", result="auth_error")
    store.record(
        source="github",
        credential_version=version,
        kind="test",
        result="ok",
        observed_at="2026-11-03T00:00:01+00:00",
    )
    summary = store.summary_for_source("github", version)
    assert summary.current == "ok"
    assert summary.stale is False


def test_health_store_stale_when_version_changes(tmp_path: Path) -> None:
    store = _health_db(tmp_path / "stale.db")
    store.record(source="github", credential_version="oldver", kind="test", result="ok")
    summary = store.summary_for_source("github", "newver")
    assert summary.current is None
    assert summary.stale is True


def test_classify_probe_outcome_distinct_results() -> None:
    assert classify_probe_outcome(status_code=200).result == "ok"
    assert classify_probe_outcome(status_code=401).result == "auth_error"
    assert classify_probe_outcome(status_code=429).result == "rate_limited"
    assert classify_probe_outcome(status_code=None, timed_out=True).result == "timeout"
    assert classify_probe_outcome(status_code=503).result == "unavailable"


def test_probe_github_uses_rate_limit_url() -> None:
    import asyncio

    seen: list[str] = []

    async def _run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            outcome = await probe_github("secret-token", client=client)
        assert outcome.result == "ok"
        assert "secret-token" not in outcome.reason

    asyncio.run(_run())
    assert seen == ["https://api.github.com/rate_limit"]


def test_record_connector_health_from_digest(tmp_path: Path) -> None:
    db = tmp_path / "conn-health.db"
    store = _health_db(db)
    provider = CredentialsProvider(db, environ={"GITHUB_TOKEN": "ghp_env"})
    record_connector_health_from_digest(
        store=store,
        provider=provider,
        warnings=[
            ConnectorWarning(connector="github", code="rate_limited", message="slow"),
        ],
        connector_names={"github"},
    )
    summary = summary_for_catalog_source(store, provider, "github")
    assert summary.current == "rate_limited"
    assert summary.kind == "connector"


def _secrets_count(db: Path) -> int:
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0]


def test_post_credential_test_stores_result_without_changing_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import build_application

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", key)
    db = tmp_path / "post-test.db"
    application = build_application(fake=True, db_path=db)
    client = TestClient(create_app(application))
    provider = application.credentials_service
    provider.save("GITHUB_TOKEN", "ghp_test_secret1234")
    before = _secrets_count(db)

    async def _fake_test(name, prov, **kw):  # noqa: ANN001
        from ai_news_agent.credential_tests import ProbeOutcome

        return ProbeOutcome(result="auth_error", reason="Authentication failed.")

    monkeypatch.setattr(
        "ai_news_agent.api.routers.settings.run_credential_test",
        _fake_test,
    )
    response = client.post("/api/v1/settings/credentials/GITHUB_TOKEN/test")
    assert response.status_code == 200
    assert "ghp_test" not in str(response.json())
    assert _secrets_count(db) == before


def test_post_credential_test_unset_is_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import build_application

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    client = TestClient(create_app(build_application(fake=True, db_path=tmp_path / "unset.db")))
    assert client.post("/api/v1/settings/credentials/GITHUB_TOKEN/test").status_code == 400


def test_get_sources_health_stale_after_credential_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import build_application

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", key)
    db = tmp_path / "sources-health.db"
    application = build_application(fake=True, db_path=db)
    client = TestClient(create_app(application))
    provider = application.credentials_service
    store = application.credential_health_store
    provider.save("GITHUB_TOKEN", "ghp_one")
    v1 = health_version_for_source(provider, "github")
    store.record(source="github", credential_version=v1, kind="test", result="ok")
    provider.save("GITHUB_TOKEN", "ghp_two")
    assert health_version_for_source(provider, "github") != v1
    github = next(
        s for s in client.get("/api/v1/sources").json()["sources"] if s["name"] == "github"
    )
    assert github["health"]["stale"] is True
    assert github["health"]["current"] is None
