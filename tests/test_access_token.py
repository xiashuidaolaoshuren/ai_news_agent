"""Tests for owner access token, remote mode, and CORS (B11)."""

from __future__ import annotations

from pathlib import Path

import pytest
import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from ai_news_agent.access import AccessConfig, LlmEndpointGuard, validate_llm_base_url
from ai_news_agent.api.app import create_app
from ai_news_agent.credential_tests import ProbeOutcome, run_credential_test
from ai_news_agent.credentials import CredentialsProvider
from ai_news_agent.services.composition import build_application

_LOOPBACK_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")

_ACCESS_ENV_VARS = (
    "AI_NEWS_AGENT_REMOTE",
    "AI_NEWS_AGENT_ACCESS_TOKEN",
    "AI_NEWS_AGENT_CORS_ORIGINS",
    "AI_NEWS_AGENT_ALLOW_LOCAL_LLM",
)


@pytest.fixture(autouse=True)
def _clear_access_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ACCESS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_from_environ_defaults_to_local_mode_with_loopback_origins() -> None:
    access = AccessConfig.from_environ({})

    assert access.remote is False
    assert access.access_token is None
    assert access.cors_origins == _LOOPBACK_ORIGINS
    assert access.allow_local_llm is False


def test_from_environ_remote_with_token() -> None:
    access = AccessConfig.from_environ(
        {"AI_NEWS_AGENT_REMOTE": "1", "AI_NEWS_AGENT_ACCESS_TOKEN": "tok"}
    )

    assert access.remote is True
    assert access.access_token == "tok"


def test_from_environ_remote_flag_parameter_enables_remote_mode() -> None:
    access = AccessConfig.from_environ(
        {"AI_NEWS_AGENT_ACCESS_TOKEN": "tok"}, remote_flag=True
    )

    assert access.remote is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_from_environ_falsey_values_keep_local_mode(value: str) -> None:
    access = AccessConfig.from_environ(
        {"AI_NEWS_AGENT_REMOTE": value, "AI_NEWS_AGENT_ACCESS_TOKEN": "tok"}
    )

    assert access.remote is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_from_environ_truthy_values_enable_remote_mode(value: str) -> None:
    access = AccessConfig.from_environ(
        {"AI_NEWS_AGENT_REMOTE": value, "AI_NEWS_AGENT_ACCESS_TOKEN": "tok"}
    )

    assert access.remote is True


def test_from_environ_remote_without_token_raises() -> None:
    with pytest.raises(RuntimeError):
        AccessConfig.from_environ({"AI_NEWS_AGENT_REMOTE": "1"})


def test_from_environ_remote_with_blank_token_raises() -> None:
    with pytest.raises(RuntimeError):
        AccessConfig.from_environ(
            {"AI_NEWS_AGENT_REMOTE": "1", "AI_NEWS_AGENT_ACCESS_TOKEN": "   "}
        )


def test_from_environ_parses_cors_origins_strips_and_drops_empties() -> None:
    access = AccessConfig.from_environ(
        {"AI_NEWS_AGENT_CORS_ORIGINS": " https://a.example , , https://b.example "}
    )

    assert access.cors_origins == ("https://a.example", "https://b.example")


def test_from_environ_empty_cors_origins_keep_loopback_defaults() -> None:
    access = AccessConfig.from_environ({"AI_NEWS_AGENT_CORS_ORIGINS": "  "})

    assert access.cors_origins == _LOOPBACK_ORIGINS


def test_from_environ_rejects_wildcard_origins() -> None:
    with pytest.raises(RuntimeError):
        AccessConfig.from_environ({"AI_NEWS_AGENT_CORS_ORIGINS": "*"})
    with pytest.raises(RuntimeError):
        AccessConfig.from_environ({"AI_NEWS_AGENT_CORS_ORIGINS": "https://*.example"})


def test_from_environ_allow_local_llm_truthy() -> None:
    access = AccessConfig.from_environ({"AI_NEWS_AGENT_ALLOW_LOCAL_LLM": "yes"})

    assert access.allow_local_llm is True


def _service_main_with_sentinel(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, dict]]:
    calls: list[tuple[object, dict]] = []

    def fake_run(app: object, **kwargs: object) -> None:
        calls.append((app, kwargs))

    # Keep the test hermetic: the real .env must not leak into os.environ for
    # later tests (dotenv mutation is not reverted by monkeypatch).
    monkeypatch.setattr(
        "ai_news_agent.app.digest_service.load_local_env", lambda *a, **k: None
    )
    monkeypatch.setattr("ai_news_agent.app.digest_service.uvicorn.run", fake_run)
    return calls


def test_service_remote_flag_without_token_refuses_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _service_main_with_sentinel(monkeypatch)
    from ai_news_agent.app.digest_service import main

    code = main(["--remote", "--db-path", str(tmp_path / "svc-remote.db")])

    assert code == 2
    assert calls == []


def test_service_env_remote_without_token_refuses_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _service_main_with_sentinel(monkeypatch)
    monkeypatch.setenv("AI_NEWS_AGENT_REMOTE", "1")
    from ai_news_agent.app.digest_service import main

    code = main(["--db-path", str(tmp_path / "svc-env.db")])

    assert code == 2
    assert calls == []


def test_service_remote_with_token_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _service_main_with_sentinel(monkeypatch)
    monkeypatch.setenv("AI_NEWS_AGENT_ACCESS_TOKEN", "tok")
    from ai_news_agent.app.digest_service import main

    code = main(["--remote", "--db-path", str(tmp_path / "svc-ok.db")])

    assert code == 0
    assert len(calls) == 1


def test_build_application_accepts_access_config(tmp_path: Path) -> None:
    access = AccessConfig(remote=True, access_token="tok")

    application = build_application(
        fake=True, db_path=tmp_path / "app-access.db", access=access
    )

    assert application.access == access


def test_build_application_defaults_to_local_access(tmp_path: Path) -> None:
    application = build_application(fake=True, db_path=tmp_path / "app-local.db")

    assert application.access.remote is False
    assert application.access.access_token is None


def test_cli_service_parser_accepts_remote_flag() -> None:
    from ai_news_agent.cli import build_arg_parser

    ns = build_arg_parser().parse_args(["service", "--remote", "--db-path", "x.db"])

    assert ns.remote is True


def _remote_client(db_path: Path, *, allow_local: bool = False) -> TestClient:
    application = build_application(
        fake=True,
        db_path=db_path,
        access=AccessConfig(
            remote=True,
            access_token="secret-token",
            allow_local_llm=allow_local,
        ),
    )
    return TestClient(create_app(application))


def test_remote_mode_requires_bearer_on_api_routes(tmp_path: Path) -> None:
    client = _remote_client(tmp_path / "remote-401.db")

    assert client.get("/api/v1/settings/language").status_code == 401
    wrong = client.get(
        "/api/v1/settings/language",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert wrong.status_code == 401
    ok = client.get(
        "/api/v1/settings/language",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert ok.status_code == 200


def test_remote_mode_401_carries_detail_and_challenge_header(tmp_path: Path) -> None:
    client = _remote_client(tmp_path / "remote-401-shape.db")

    response = client.get("/api/v1/sessions")

    assert response.status_code == 401
    assert response.json()["detail"]
    assert response.headers["www-authenticate"] == "Bearer"


def test_remote_mode_health_stays_open(tmp_path: Path) -> None:
    client = _remote_client(tmp_path / "remote-health.db")

    assert client.get("/api/v1/health").status_code == 200


def test_remote_mode_gates_sse_message_requests(tmp_path: Path) -> None:
    client = _remote_client(tmp_path / "remote-sse.db")

    response = client.post("/api/v1/sessions/does-not-exist/messages", json={"content": "hi"})

    assert response.status_code == 401


def test_local_mode_with_configured_token_enforces_bearer(tmp_path: Path) -> None:
    application = build_application(
        fake=True,
        db_path=tmp_path / "local-token.db",
        access=AccessConfig(remote=False, access_token="secret-token"),
    )
    client = TestClient(create_app(application))

    assert client.get("/api/v1/settings/language").status_code == 401
    ok = client.get(
        "/api/v1/settings/language",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert ok.status_code == 200


def test_cors_uses_env_origin_and_allows_put_and_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_CORS_ORIGINS", "https://app.example")
    application = build_application(fake=True, db_path=tmp_path / "cors-env.db")
    client = TestClient(create_app(application))

    preflight = client.options(
        "/api/v1/settings/language",
        headers={
            "Origin": "https://app.example",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://app.example"
    assert "PUT" in preflight.headers["access-control-allow-methods"]
    assert "authorization" in preflight.headers["access-control-allow-headers"].lower()


def test_cors_does_not_allow_unlisted_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_CORS_ORIGINS", "https://app.example")
    application = build_application(fake=True, db_path=tmp_path / "cors-bad.db")
    client = TestClient(create_app(application))

    response = client.get(
        "/api/v1/settings/language", headers={"Origin": "https://evil.example"}
    )

    assert "access-control-allow-origin" not in response.headers


def test_cors_defaults_keep_loopback_dev_origins_and_allow_put(tmp_path: Path) -> None:
    application = build_application(fake=True, db_path=tmp_path / "cors-default.db")
    client = TestClient(create_app(application))

    preflight = client.options(
        "/api/v1/settings/language",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "PUT" in preflight.headers["access-control-allow-methods"]


def _local_client(db_path: Path, *, host: str = "testclient") -> TestClient:
    application = build_application(fake=True, db_path=db_path)
    return TestClient(create_app(application), client=(host, 50000))


def test_local_mode_non_loopback_credential_write_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", Fernet.generate_key().decode())
    client = _local_client(tmp_path / "local-write.db", host="192.0.2.10")

    put = client.put(
        "/api/v1/settings/credentials/GITHUB_TOKEN", json={"value": "ghp_refused"}
    )
    delete = client.delete("/api/v1/settings/credentials/llm")

    assert put.status_code == 403
    assert delete.status_code == 403


def test_local_mode_loopback_credential_write_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", Fernet.generate_key().decode())
    client = _local_client(tmp_path / "local-loopback.db", host="127.0.0.1")

    saved = client.put(
        "/api/v1/settings/credentials/GITHUB_TOKEN", json={"value": "ghp_saved1234"}
    )
    deleted = client.delete("/api/v1/settings/credentials/GITHUB_TOKEN")

    assert saved.status_code == 200
    assert deleted.status_code == 204


def test_local_mode_ipv6_loopback_credential_write_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", Fernet.generate_key().decode())
    client = _local_client(tmp_path / "local-ipv6.db", host="::1")

    saved = client.put(
        "/api/v1/settings/credentials/GITHUB_TOKEN", json={"value": "ghp_saved1234"}
    )

    assert saved.status_code == 200


def test_local_mode_reads_stay_open_from_non_loopback(tmp_path: Path) -> None:
    client = _local_client(tmp_path / "local-read.db", host="192.0.2.10")

    assert client.get("/api/v1/settings/credentials").status_code == 200
    assert client.get("/api/v1/settings/language").status_code == 200


def test_local_mode_credential_test_route_is_not_a_write(tmp_path: Path) -> None:
    client = _local_client(tmp_path / "local-test-route.db", host="192.0.2.10")

    response = client.post("/api/v1/settings/credentials/GITHUB_TOKEN/test")

    assert response.status_code == 400


_REMOTE_AUTH = {"Authorization": "Bearer secret-token"}


def test_validate_llm_base_url_accepts_public_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    validate_llm_base_url("https://api.openai.com/v1", allow_local=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com/v1",
        "ftp://api.openai.com/v1",
        "https://10.0.0.5/v1",
        "https://172.16.0.2/v1",
        "https://192.168.1.10/v1",
        "https://127.0.0.1:11434/v1",
        "https://169.254.1.1/v1",
        "https://[::1]/v1",
        "https://0.0.0.0/v1",
        "https://localhost:11434/v1",
    ],
)
def test_validate_llm_base_url_rejects_private_or_plain(url: str) -> None:
    with pytest.raises(ValueError):
        validate_llm_base_url(url, allow_local=False)


def test_validate_llm_base_url_rejects_hostname_resolving_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))],
    )

    with pytest.raises(ValueError):
        validate_llm_base_url("https://llm.internal.example/v1", allow_local=False)


def test_validate_llm_base_url_rejects_unresolvable_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object) -> list[tuple]:
        raise OSError("dns down")

    monkeypatch.setattr("socket.getaddrinfo", boom)

    with pytest.raises(ValueError):
        validate_llm_base_url("https://llm.example/v1", allow_local=False)


def test_validate_llm_base_url_allow_local_bypasses_network_rule() -> None:
    validate_llm_base_url("http://127.0.0.1:11434/v1", allow_local=True)


def test_remote_mode_rejects_private_llm_base_url_without_saving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", Fernet.generate_key().decode())
    client = _remote_client(tmp_path / "remote-llm-url.db")

    response = client.put(
        "/api/v1/settings/credentials/llm",
        headers=_REMOTE_AUTH,
        json={
            "api_key": "sk-ui-llm-key",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "gpt-test",
        },
    )

    assert response.status_code == 400
    listed = client.get("/api/v1/settings/credentials", headers=_REMOTE_AUTH).json()
    llm = next(c for c in listed["credentials"] if c["name"] == "llm")
    assert llm["status"] == "unset"


def test_remote_mode_saves_public_https_llm_base_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    client = _remote_client(tmp_path / "remote-llm-ok.db")

    response = client.put(
        "/api/v1/settings/credentials/llm",
        headers=_REMOTE_AUTH,
        json={
            "api_key": "sk-ui-llm-key",
            "base_url": "https://llm.example/v1",
            "model": "gpt-test",
        },
    )

    assert response.status_code == 200


def test_remote_mode_allow_local_llm_saves_local_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", Fernet.generate_key().decode())
    client = _remote_client(tmp_path / "remote-llm-local.db", allow_local=True)

    response = client.put(
        "/api/v1/settings/credentials/llm",
        headers=_REMOTE_AUTH,
        json={
            "api_key": "sk-ui-llm-key",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "gpt-test",
        },
    )

    assert response.status_code == 200


def test_local_mode_saves_plain_http_llm_base_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_SECRET_KEY", Fernet.generate_key().decode())
    client = _local_client(tmp_path / "local-llm-url.db", host="127.0.0.1")

    response = client.put(
        "/api/v1/settings/credentials/llm",
        json={
            "api_key": "sk-ui-llm-key",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "gpt-test",
        },
    )

    assert response.status_code == 200


def test_build_chat_model_accepts_guard_and_builds_guarded_http_client() -> None:
    from ai_news_agent.llm import build_chat_model

    guard = LlmEndpointGuard()

    model = build_chat_model(
        api_key="sk-test",
        base_url="https://llm.example/v1",
        model="gpt-test",
        guard=guard,
    )

    assert model is not None
    assert model._client._client is not None  # noqa: SLF001


def test_build_tool_chat_model_accepts_guard() -> None:
    from ai_news_agent.llm import build_tool_chat_model

    guard = LlmEndpointGuard()

    model = build_tool_chat_model(
        api_key="sk-test",
        base_url="https://llm.example/v1",
        model="gpt-test",
        guard=guard,
    )

    assert model is not None


def test_llm_guard_blocks_sync_redirect_to_private_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    guard = LlmEndpointGuard()
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://10.0.0.5/v1/chat"})

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [guard.sync_request_hook]},
        follow_redirects=True,
    )

    with pytest.raises(ValueError):
        client.get("https://llm.example/v1/chat")

    assert hits == ["https://llm.example/v1/chat"]


def test_llm_guard_blocks_async_redirect_to_private_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    guard = LlmEndpointGuard()
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://10.0.0.5/v1/chat"})

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            event_hooks={"request": [guard.async_request_hook]},
            follow_redirects=True,
        ) as client:
            with pytest.raises(ValueError):
                await client.get("https://llm.example/v1/chat")

    asyncio.run(_run())
    assert hits == ["https://llm.example/v1/chat"]


def test_build_application_wires_llm_guard_in_remote_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[dict] = []
    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_chat_model",
        lambda **kwargs: captured.append(kwargs) or object(),
    )
    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_tool_chat_model",
        lambda **kwargs: None,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    build_application(
        fake=False,
        db_path=tmp_path / "guard-remote.db",
        access=AccessConfig(remote=True, access_token="tok"),
    )

    assert captured
    assert isinstance(captured[0]["guard"], LlmEndpointGuard)


def test_build_application_omits_llm_guard_in_local_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[dict] = []
    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_chat_model",
        lambda **kwargs: captured.append(kwargs) or object(),
    )
    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_tool_chat_model",
        lambda **kwargs: None,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    build_application(
        fake=False,
        db_path=tmp_path / "guard-local.db",
        access=AccessConfig(),
    )

    assert captured
    assert captured[0]["guard"] is None


def _dummy_llm_model() -> object:
    class _Completions:
        def create(self, **kwargs: object) -> None:
            return None

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    class _Model:
        _client = _Client()
        _model = "gpt-test"

    return _Model()


def test_run_credential_test_threads_guard_to_llm_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    captured: dict = {}

    def fake_build(**kwargs: object) -> object:
        captured.update(kwargs)
        return _dummy_llm_model()

    monkeypatch.setattr("ai_news_agent.credential_tests.build_chat_model", fake_build)
    db = tmp_path / "probe-guard.db"
    build_application(fake=True, db_path=db)
    provider = CredentialsProvider(db, environ={"OPENAI_API_KEY": "sk-env"})
    guard = LlmEndpointGuard()

    outcome = asyncio.run(run_credential_test("llm", provider, guard=guard))

    assert outcome.result == "ok"
    assert captured["guard"] is guard


def test_remote_mode_test_route_passes_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    async def fake_test(name: str, provider: object, **kwargs: object) -> ProbeOutcome:
        captured.update(kwargs)
        return ProbeOutcome(result="ok", reason="ok")

    monkeypatch.setattr("ai_news_agent.api.routers.settings.run_credential_test", fake_test)
    client = _remote_client(tmp_path / "remote-route-guard.db")

    response = client.post(
        "/api/v1/settings/credentials/llm/test", headers=_REMOTE_AUTH
    )

    assert response.status_code == 200
    assert isinstance(captured.get("guard"), LlmEndpointGuard)
