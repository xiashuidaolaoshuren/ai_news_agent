"""Tests for the persistent local digest HTTP service."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_news_agent.app import digest_service
from ai_news_agent.app.digest_service import (
    DigestServiceRuntime,
    build_digest_request_payload,
)
from ai_news_agent.request import DigestRequest
from ai_news_agent.sources import DEFAULT_SOURCE_NAMES
from ai_news_agent.tools.schemas import (
    InterfaceAgentResult,
    InterfaceAgentResultKind,
)


class _FakeInterfaceRouter:
    def __init__(
        self,
        *,
        result: InterfaceAgentResult | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result or InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="unused",
        )

    async def route(
        self,
        *,
        message: str,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
        correlation_id: str | None = None,
        on_stage=None,
        allow_digest: bool = True,
    ) -> InterfaceAgentResult:
        self.calls.append(
            {
                "message": message,
                "digest_request": digest_request,
                "session_connector_names": session_connector_names,
                "correlation_id": correlation_id,
                "on_stage": on_stage,
                "allow_digest": allow_digest,
            }
        )
        return self._result


class _OnStageInvokingRouter:
    """Simulates agent-success digest by invoking on_stage without workflow_runner."""

    def __init__(
        self,
        *,
        result: InterfaceAgentResult | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result or InterfaceAgentResult(
            kind=InterfaceAgentResultKind.DIGEST,
            text="digest body",
            run_id=7,
        )

    async def route(
        self,
        *,
        message: str,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
        correlation_id: str | None = None,
        on_stage=None,
    ) -> InterfaceAgentResult:
        self.calls.append(
            {
                "message": message,
                "digest_request": digest_request,
                "correlation_id": correlation_id,
                "on_stage": on_stage,
            }
        )
        if on_stage is not None:
            on_stage("parse_request")
            on_stage("collect_sources")
        return self._result


class _WorkflowInvokingRouter:
    """Simulates deterministic digest fallback by calling the runtime workflow runner."""

    def __init__(self, runtime: DigestServiceRuntime) -> None:
        self._runtime = runtime
        self.calls: list[dict[str, object]] = []

    async def route(
        self,
        *,
        message: str,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
        correlation_id: str | None = None,
        on_stage=None,
    ) -> InterfaceAgentResult:
        self.calls.append(
            {
                "message": message,
                "digest_request": digest_request,
                "correlation_id": correlation_id,
                "on_stage": on_stage,
            }
        )
        assert digest_request is not None
        digest_result = await self._runtime._workflow_runner(digest_request, on_stage=on_stage)
        return InterfaceAgentResult(
            kind=InterfaceAgentResultKind.DIGEST,
            text=digest_result.text,
            run_id=digest_result.run_id,
            digest=digest_result.digest,
        )


class _ConcurrentOverwriteRouter:
    """Simulates fallback while another request overwrites runtime._active_on_stage."""

    def __init__(self, runtime: DigestServiceRuntime) -> None:
        self._runtime = runtime
        self.calls: list[dict[str, object]] = []

    async def route(
        self,
        *,
        message: str,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
        correlation_id: str | None = None,
        on_stage=None,
    ) -> InterfaceAgentResult:
        self.calls.append(
            {
                "message": message,
                "digest_request": digest_request,
                "correlation_id": correlation_id,
                "on_stage": on_stage,
            }
        )
        assert digest_request is not None
        if on_stage is not None and hasattr(self._runtime, "_active_on_stage"):
            self._runtime._active_on_stage = lambda stage: on_stage(f"stale_{stage}")
        digest_result = await self._runtime._workflow_runner(digest_request, on_stage=on_stage)
        return InterfaceAgentResult(
            kind=InterfaceAgentResultKind.DIGEST,
            text=digest_result.text,
            run_id=digest_result.run_id,
            digest=digest_result.digest,
        )


def test_main_runs_uvicorn_with_composition_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

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
            str(tmp_path / "main.db"),
        ]
    )

    assert code == 0
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["port"] == 9999
    paths = {route.path for route in captured["app"].routes}
    assert {"/health", "/digest", "/followup"} <= paths


def test_build_digest_request_payload_maps_hints() -> None:
    payload = build_digest_request_payload(
        timeframe_hint="week",
        sources_hint="github",
        topics_hint="RAG, agents",
    )
    assert payload["timeframe"] == "last_7_days"
    assert payload["sources"] == "github"
    assert payload["topics"] == ["RAG", "agents"]


def test_build_digest_request_payload_omits_topics_when_absent() -> None:
    payload = build_digest_request_payload()
    assert payload["timeframe"] == "today"
    assert payload["sources"] == ",".join(DEFAULT_SOURCE_NAMES)
    assert "topics" not in payload


def _build_app_client(*, fake: bool, db_path: Path):
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import build_application

    application = build_application(fake=fake, db_path=db_path)
    return TestClient(create_app(application)), application


def test_health_endpoint_returns_ok(tmp_path: Path) -> None:
    client, _application = _build_app_client(fake=True, db_path=tmp_path / "health.db")

    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["fake"] is True


def test_digest_endpoint_returns_markdown_text(tmp_path: Path) -> None:
    client, _application = _build_app_client(
        fake=True,
        db_path=tmp_path / "digest-happy.db",
    )

    resp = client.post(
        "/digest",
        json={
            "timeframe": "today",
            "sources": "github",
            "fake": True,
            "correlation_id": "test-corr-1",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["correlation_id"] == "test-corr-1"
    assert "AI News Digest" in data["text"]
    assert "Fake GitHub repo" in data["text"]
    assert isinstance(data["elapsed_s"], float)
    assert data["elapsed_s"] >= 0
    assert "stages" in data


def test_digest_service_runtime_live_builds_interface_tool_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router_calls: list[dict[str, object]] = []
    fake_router = MagicMock(name="InterfaceToolRouter")

    def spy_build_interface_tool_router(**kwargs: object) -> MagicMock:
        router_calls.append(kwargs)
        return fake_router

    monkeypatch.setattr(digest_service, "build_chat_model", lambda: MagicMock(name="ChatModel"))
    monkeypatch.setattr(
        digest_service,
        "build_tool_chat_model",
        lambda: MagicMock(name="ToolChatModel"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_connector_factory",
        lambda **kw: MagicMock(name="ConnectorFactory"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_interface_tool_router",
        spy_build_interface_tool_router,
        raising=False,
    )

    runtime = DigestServiceRuntime(fake=False, db_path=tmp_path / "live-router.db")

    assert len(router_calls) == 1
    assert router_calls[0]["interface_name"] == "openclaw"
    assert router_calls[0]["tool_model"] is not None
    assert router_calls[0]["digest_model"] is not None
    assert callable(router_calls[0]["build_connectors_fn"])
    assert callable(router_calls[0]["workflow_runner"])
    assert router_calls[0]["streaming_workflow_runner"] is None
    assert "juya_factory" in router_calls[0]
    assert "huggingface_factory" in router_calls[0]
    assert "zhihu_factory" in router_calls[0]
    assert runtime._interface_router is fake_router


def test_digest_service_runtime_live_passes_juya_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory_calls: list[dict[str, object]] = []
    router_calls: list[dict[str, object]] = []

    def recording_build_connector_factory(**kwargs: object) -> MagicMock:
        factory_calls.append(dict(kwargs))
        return MagicMock(name=f"ConnectorFactory-{kwargs.get('name')}")

    def spy_build_interface_tool_router(**kwargs: object) -> MagicMock:
        router_calls.append(kwargs)
        return MagicMock(name="InterfaceToolRouter")

    monkeypatch.setattr(digest_service, "build_chat_model", lambda: MagicMock(name="ChatModel"))
    monkeypatch.setattr(
        digest_service,
        "build_tool_chat_model",
        lambda: MagicMock(name="ToolChatModel"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_connector_factory",
        recording_build_connector_factory,
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_interface_tool_router",
        spy_build_interface_tool_router,
        raising=False,
    )

    DigestServiceRuntime(fake=False, db_path=tmp_path / "live-juya-factory.db")

    assert any(call.get("name") == "juya" for call in factory_calls)
    assert any(call.get("name") == "huggingface" for call in factory_calls)
    assert any(call.get("name") == "zhihu" for call in factory_calls)
    assert len(router_calls) == 1
    assert router_calls[0]["juya_factory"] is not None
    assert router_calls[0]["huggingface_factory"] is not None
    assert router_calls[0]["zhihu_factory"] is not None


def test_digest_service_runtime_fake_mode_has_no_interface_router(tmp_path: Path) -> None:
    runtime = DigestServiceRuntime(fake=True, db_path=tmp_path / "fake-router.db")
    assert runtime._interface_router is None


def _live_app_client_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: InterfaceAgentResult | None = None,
):
    from ai_news_agent.services import composition

    monkeypatch.setattr(composition, "build_chat_model", lambda: MagicMock(name="ChatModel"))
    monkeypatch.setattr(
        composition,
        "build_tool_chat_model",
        lambda: MagicMock(name="ToolChatModel"),
        raising=False,
    )
    monkeypatch.setattr(
        composition,
        "build_connector_factory",
        lambda **kw: MagicMock(name="ConnectorFactory"),
        raising=False,
    )
    monkeypatch.setattr(
        composition,
        "build_interface_tool_router",
        lambda **kwargs: MagicMock(name="InterfaceToolRouter"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service, "build_chat_model", lambda: MagicMock(name="ChatModel")
    )
    monkeypatch.setattr(
        digest_service,
        "build_tool_chat_model",
        lambda: MagicMock(name="ToolChatModel"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_connector_factory",
        lambda **kw: MagicMock(name="ConnectorFactory"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_interface_tool_router",
        lambda **kwargs: MagicMock(name="InterfaceToolRouter"),
        raising=False,
    )
    router = _FakeInterfaceRouter(
        result=result
        or InterfaceAgentResult(
            kind=InterfaceAgentResultKind.DIGEST,
            text="digest body",
            run_id=7,
        )
    )
    client, application = _build_app_client(fake=False, db_path=tmp_path / "live-svc.db")
    application.openclaw_runtime._interface_router = router
    return client, application, router


@pytest.fixture
def live_app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return _live_app_client_factory(tmp_path, monkeypatch)


def test_live_digest_routes_through_router(live_app_client) -> None:
    client, _application, router = live_app_client

    resp = client.post(
        "/digest",
        json={
            "timeframe": "today",
            "sources": "github",
            "correlation_id": "live-corr-1",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "digest body"
    assert data["run_id"] == 7
    assert data["correlation_id"] == "live-corr-1"
    assert isinstance(data["elapsed_s"], float)
    assert "stages" in data
    assert len(router.calls) == 1
    assert router.calls[0]["digest_request"] is not None


def test_live_digest_passes_correlation_id_to_router(live_app_client) -> None:
    client, _application, router = live_app_client

    resp = client.post(
        "/digest",
        json={"timeframe": "today", "sources": "github", "correlation_id": "corr-9"},
    )

    assert resp.status_code == 200
    assert resp.json()["correlation_id"] == "corr-9"
    assert router.calls[-1]["correlation_id"] == "corr-9"


def test_live_digest_fallback_preserves_stage_timings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_service, "build_chat_model", lambda: MagicMock(name="ChatModel"))
    monkeypatch.setattr(
        digest_service,
        "build_tool_chat_model",
        lambda: MagicMock(name="ToolChatModel"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_connector_factory",
        lambda **kw: MagicMock(name="ConnectorFactory"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_interface_tool_router",
        lambda **kwargs: MagicMock(name="InterfaceToolRouter"),
        raising=False,
    )
    original_build_connectors = digest_service.build_connectors
    monkeypatch.setattr(
        digest_service,
        "build_connectors",
        lambda *, fake, names: original_build_connectors(fake=True, names=names),
    )
    runtime = DigestServiceRuntime(fake=False, db_path=tmp_path / "stages.db")
    runtime._interface_router = _WorkflowInvokingRouter(runtime)

    request = DigestRequest(topics=["AI"], connector_names=["github"])
    result, stages, _elapsed = asyncio.run(
        runtime.run_digest(request, correlation_id="stage-corr", message="")
    )

    assert "AI News Digest" in result.text
    assert stages
    assert any(name for name in stages)


def test_live_digest_agent_success_preserves_stage_timings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_service, "build_chat_model", lambda: MagicMock(name="ChatModel"))
    monkeypatch.setattr(
        digest_service,
        "build_tool_chat_model",
        lambda: MagicMock(name="ToolChatModel"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_connector_factory",
        lambda **kw: MagicMock(name="ConnectorFactory"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_interface_tool_router",
        lambda **kwargs: MagicMock(name="InterfaceToolRouter"),
        raising=False,
    )
    runtime = DigestServiceRuntime(fake=False, db_path=tmp_path / "agent-stages.db")
    router = _OnStageInvokingRouter()
    runtime._interface_router = router

    request = DigestRequest(topics=["AI"], connector_names=["github"])
    result, stages, _elapsed = asyncio.run(
        runtime.run_digest(request, correlation_id="agent-stage-corr", message="")
    )

    assert result.run_id == 7
    assert stages
    assert "parse_request" in stages
    assert "collect_sources" in stages
    assert router.calls[-1]["on_stage"] is not None


def test_live_digest_fallback_uses_per_request_on_stage_not_instance_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_service, "build_chat_model", lambda: MagicMock(name="ChatModel"))
    monkeypatch.setattr(
        digest_service,
        "build_tool_chat_model",
        lambda: MagicMock(name="ToolChatModel"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_connector_factory",
        lambda **kw: MagicMock(name="ConnectorFactory"),
        raising=False,
    )
    monkeypatch.setattr(
        digest_service,
        "build_interface_tool_router",
        lambda **kwargs: MagicMock(name="InterfaceToolRouter"),
        raising=False,
    )
    original_build_connectors = digest_service.build_connectors
    monkeypatch.setattr(
        digest_service,
        "build_connectors",
        lambda *, fake, names: original_build_connectors(fake=True, names=names),
    )
    runtime = DigestServiceRuntime(fake=False, db_path=tmp_path / "per-request-on-stage.db")
    runtime._interface_router = _ConcurrentOverwriteRouter(runtime)

    request = DigestRequest(topics=["AI"], connector_names=["github"])
    _result, stages, _elapsed = asyncio.run(
        runtime.run_digest(request, correlation_id="per-request-corr", message="")
    )

    assert not hasattr(runtime, "_active_on_stage")
    assert stages
    assert "parse_request" in stages
    assert "stale_parse_request" not in stages


def test_digest_endpoint_rejects_unknown_source(tmp_path: Path) -> None:
    client, _application = _build_app_client(
        fake=True,
        db_path=tmp_path / "digest-unknown-source.db",
    )

    resp = client.post("/digest", json={"sources": "arxiv", "fake": True})

    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    assert "detail" not in data


def test_digest_endpoint_rejects_invalid_json_body(tmp_path: Path) -> None:
    client, _application = _build_app_client(
        fake=True,
        db_path=tmp_path / "digest-bad-json.db",
    )

    resp = client.post(
        "/digest",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid JSON body"}


def test_digest_endpoint_rejects_fake_mode_mismatch(tmp_path: Path) -> None:
    client, _application = _build_app_client(
        fake=True,
        db_path=tmp_path / "digest-fake-mismatch.db",
    )

    resp = client.post(
        "/digest",
        json={"sources": "github", "fake": False},
    )

    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    assert "fake" in data["error"]


def test_digest_endpoint_maps_unexpected_failure_to_safe_500(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RaisingRouter:
        async def route(self, **kwargs: object) -> object:
            raise RuntimeError("provider exploded with secret-token")

    live_client, application, _router = _live_app_client_factory(tmp_path, monkeypatch)
    application.openclaw_runtime._interface_router = _RaisingRouter()

    resp = live_client.post(
        "/digest",
        json={"timeframe": "today", "sources": "github", "correlation_id": "boom-1"},
    )

    assert resp.status_code == 500
    data = resp.json()
    assert "error" in data
    assert data["correlation_id"] == "boom-1"


def test_followup_endpoint_requires_message(tmp_path: Path) -> None:
    client, _application = _build_app_client(
        fake=True,
        db_path=tmp_path / "followup-blank.db",
    )

    resp = client.post("/followup", json={})

    assert resp.status_code == 400
    assert "message" in resp.json()["error"]


def test_followup_endpoint_no_digest(tmp_path: Path) -> None:
    client, _application = _build_app_client(
        fake=True,
        db_path=tmp_path / "followup-no-digest.db",
    )

    resp = client.post(
        "/followup",
        json={"message": "show sources", "correlation_id": "f1"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["correlation_id"] == "f1"
    assert data["path"] == "no_digest"
    assert "No saved digest" in data["text"]


def test_followup_endpoint_after_digest(tmp_path: Path) -> None:
    client, _application = _build_app_client(
        fake=True,
        db_path=tmp_path / "followup-after-digest.db",
    )

    digest_resp = client.post(
        "/digest",
        json={
            "timeframe": "today",
            "sources": "github",
            "fake": True,
            "correlation_id": "digest-1",
        },
    )
    assert digest_resp.status_code == 200

    resp = client.post(
        "/followup",
        json={"message": "show sources", "correlation_id": "follow-1"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["correlation_id"] == "follow-1"
    assert data["path"] == "structured"
    assert "Fake GitHub repo" in data["text"]
    assert data["run_id"] is not None


def test_followup_endpoint_rank_item_after_digest(tmp_path: Path) -> None:
    client, _application = _build_app_client(
        fake=True,
        db_path=tmp_path / "followup-rank.db",
    )
    client.post(
        "/digest",
        json={"timeframe": "today", "sources": "github", "fake": True},
    )

    resp = client.post(
        "/followup",
        json={"message": "follow up on item 1", "correlation_id": "rank-1"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == "structured"
    assert data["correlation_id"] == "rank-1"
    assert "Digest item 1:" in data["text"]


def test_live_followup_routes_structured_through_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _application, router = _live_app_client_factory(
        tmp_path,
        monkeypatch,
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.STRUCTURED,
            text="Sources: https://example.com/r1",
            run_id=3,
        ),
    )

    resp = client.post(
        "/followup",
        json={"message": "show sources", "correlation_id": "f-structured"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == "structured"
    assert data["text"] == "Sources: https://example.com/r1"
    assert data["run_id"] == 3
    assert data["correlation_id"] == "f-structured"
    assert len(router.calls) == 1
    assert router.calls[0]["allow_digest"] is False


def test_live_followup_passes_correlation_id_to_router(live_app_client) -> None:
    client, _application, router = live_app_client

    resp = client.post(
        "/followup",
        json={"message": "show sources", "correlation_id": "f-9"},
    )

    assert resp.status_code == 200
    assert resp.json()["correlation_id"] == "f-9"
    assert router.calls[-1]["correlation_id"] == "f-9"


def test_live_followup_maps_digest_result_to_guidance_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_news_agent.followup_structured import OPENCLAW_GUIDANCE_FALLBACK

    client, application, _router = _live_app_client_factory(tmp_path, monkeypatch)
    application.openclaw_runtime._interface_router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.DIGEST,
            text="# Digest body",
            run_id=9,
        )
    )

    resp = client.post("/followup", json={"message": "generate a digest about AI"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == "guidance"
    assert data["text"] == OPENCLAW_GUIDANCE_FALLBACK
    assert data["run_id"] == 9


def test_live_followup_maps_no_saved_digest_to_no_digest_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_news_agent.followup_structured import NO_SAVED_DIGEST

    client, application, _router = _live_app_client_factory(tmp_path, monkeypatch)
    application.openclaw_runtime._interface_router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text=NO_SAVED_DIGEST,
        )
    )

    resp = client.post("/followup", json={"message": "show sources"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == "no_digest"
    assert data["text"] == NO_SAVED_DIGEST
    assert data["run_id"] is None
