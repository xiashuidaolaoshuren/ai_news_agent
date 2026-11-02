"""Tests for CredentialsProvider (B9)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from ai_news_agent.credentials import (
    CREDENTIAL_ENV_NAMES,
    LLM_ENV_NAMES,
    CredentialsProvider,
    MissingSecretKeyError,
)
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
    from ai_news_agent.services.composition import build_application

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    application = build_application(fake=False, db_path=tmp_path / "live-no-llm.db")
    assert application.chat_service is not None


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


def test_cli_digest_exits_when_llm_unconfigured(tmp_path: Path, capsys) -> None:
    from argparse import Namespace

    from ai_news_agent.cli import _run_digest_command

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
