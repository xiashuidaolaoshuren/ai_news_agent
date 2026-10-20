"""Tests for the shared session-followup tool router (Milestone 4 T12)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from ai_news_agent.storage import DigestStore
from ai_news_agent.tools.schemas import (
    InterfaceAgentResult,
    InterfaceAgentResultKind,
)
from test_tools_followup import _seed_full_followup_store


class _FakeToolCallModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.bound_tools: list[Any] | None = None

    def bind_tools(self, tools: Any) -> "_FakeToolCallModel":
        self.bound_tools = list(tools)
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        msg = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return msg


def _noop_factories() -> tuple[Any, Any, Any]:
    def _factory() -> Any:
        raise AssertionError("connector factory should not run")

    return _factory, _factory, _factory


def _build_router(
    tmp_path: Path,
    *,
    store: DigestStore | None = None,
    tool_model: Any | None = None,
) -> Any:
    from ai_news_agent.tools.interface_router import build_interface_tool_router

    if store is None:
        store = DigestStore(tmp_path / "router.db")
        store.init_schema()
    gh, bh, jh = _noop_factories()

    return build_interface_tool_router(
        store=store,
        tool_model=tool_model or _FakeToolCallModel([AIMessage(content="unused")]),
        github_factory=gh,
        bilibili_factory=bh,
        juya_factory=jh,
        interface_name="test",
    )


class _ScriptedSessionRunner:
    """Tool-agent runner double recording calls or raising on demand."""

    def __init__(self, *, text: str = "session tool answer", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[str] = []

    async def run(self, message: str) -> InterfaceAgentResult:
        self.calls.append(message)
        if self.error is not None:
            raise self.error
        return InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text=self.text,
        )


def _seed_session_linked_digest(tmp_path: Path, session_id: str) -> tuple[DigestStore, int]:
    import sqlite3

    from ai_news_agent.repositories.session_store import SessionStore

    store, run_id = _seed_full_followup_store(tmp_path)
    session_store = SessionStore(store.db_path)
    session_store.create_session(session_id)
    user_message_id = session_store.insert_message(
        session_id,
        role="user",
        content="digest please",
    )
    session_store.create_request(
        session_id,
        "req-session-scope",
        user_message_id=user_message_id,
        correlation_id="corr-session-scope",
    )
    session_store.update_request_run_id(session_id, "req-session-scope", run_id)
    session_store.mark_terminal(session_id, "req-session-scope", status="succeeded")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE runs SET session_id = ? WHERE id = ?",
            (session_id, run_id),
        )
        conn.commit()
    return store, run_id


def test_run_session_followup_uses_session_scoped_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_news_agent.tools import interface_router as router_module

    session_id = "sess-scope-1"
    store, run_id = _seed_session_linked_digest(tmp_path, session_id)
    assert store.get_latest_followup_context().run_id is None

    captured: dict[str, Any] = {}
    real_build_registry = router_module.build_tool_registry

    def spy_build_registry(**kwargs: Any) -> Any:
        captured["store"] = kwargs["store"]
        return real_build_registry(**kwargs)

    runner = _ScriptedSessionRunner()
    monkeypatch.setattr(router_module, "build_tool_registry", spy_build_registry)
    monkeypatch.setattr(
        router_module,
        "build_tool_agent_runner",
        lambda **kwargs: runner,
    )

    router = _build_router(tmp_path, store=store)
    result = asyncio.run(
        router.run_session_followup(
            session_id=session_id,
            message="Why does this matter?",
        )
    )

    assert result.kind is InterfaceAgentResultKind.CONVERSATIONAL
    assert result.text == "session tool answer"
    assert runner.calls == ["Why does this matter?"]

    scoped_store = captured["store"]
    assert scoped_store is not store
    scoped_ctx = scoped_store.get_latest_followup_context()
    assert scoped_ctx.run_id == run_id
    assert scoped_ctx.digest is not None
    assert store.get_latest_followup_context().run_id is None


def test_run_session_followup_falls_back_to_guidance_on_runner_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_news_agent.tools import interface_router as router_module

    session_id = "sess-scope-fail"
    store, _run_id = _seed_session_linked_digest(tmp_path, session_id)

    monkeypatch.setattr(
        router_module,
        "build_tool_agent_runner",
        lambda **kwargs: _ScriptedSessionRunner(error=RuntimeError("tool agent exploded")),
    )

    router = _build_router(tmp_path, store=store)
    result = asyncio.run(
        router.run_session_followup(
            session_id=session_id,
            message="Why does this matter?",
        )
    )

    assert result.kind is InterfaceAgentResultKind.FALLBACK
    assert "Try a concrete request" in result.text


def test_run_session_followup_falls_back_when_agent_returns_non_conversational(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_news_agent.tools import interface_router as router_module

    session_id = "sess-scope-mismatch"
    store, _run_id = _seed_session_linked_digest(tmp_path, session_id)

    class _StructuredRunner:
        async def run(self, message: str) -> InterfaceAgentResult:
            return InterfaceAgentResult(
                kind=InterfaceAgentResultKind.STRUCTURED,
                text="structured answer",
                fallback_reason="agent_mismatch",
            )

    monkeypatch.setattr(
        router_module,
        "build_tool_agent_runner",
        lambda **kwargs: _StructuredRunner(),
    )

    router = _build_router(tmp_path, store=store)
    result = asyncio.run(
        router.run_session_followup(session_id=session_id, message="show sources")
    )

    assert result.kind is InterfaceAgentResultKind.FALLBACK
    assert result.fallback_reason == "agent_mismatch"
    assert "Try a concrete request" in result.text


def test_run_session_followup_forwards_connector_factories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_news_agent.tools import interface_router as router_module

    session_id = "sess-scope-factories"
    store, _run_id = _seed_session_linked_digest(tmp_path, session_id)

    def _sentinel() -> Any:
        return object()

    github, bilibili, juya, huggingface, zhihu = (_sentinel() for _ in range(5))
    captured: dict[str, Any] = {}
    real_build_registry = router_module.build_tool_registry

    def spy_build_registry(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return real_build_registry(**kwargs)

    monkeypatch.setattr(router_module, "build_tool_registry", spy_build_registry)
    monkeypatch.setattr(
        router_module,
        "build_tool_agent_runner",
        lambda **kwargs: _ScriptedSessionRunner(),
    )

    router = router_module.build_interface_tool_router(
        store=store,
        tool_model=_FakeToolCallModel([AIMessage(content="unused")]),
        github_factory=github,
        bilibili_factory=bilibili,
        juya_factory=juya,
        huggingface_factory=huggingface,
        zhihu_factory=zhihu,
        interface_name="test",
    )
    asyncio.run(router.run_session_followup(session_id=session_id, message="Why?"))

    assert captured["github_factory"] is github
    assert captured["bilibili_factory"] is bilibili
    assert captured["juya_factory"] is juya
    assert captured["huggingface_factory"] is huggingface
    assert captured["zhihu_factory"] is zhihu


def test_run_session_followup_applies_correlation_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_news_agent.tools import interface_router as router_module

    session_id = "sess-scope-correlation"
    store, _run_id = _seed_session_linked_digest(tmp_path, session_id)

    monkeypatch.setattr(
        router_module,
        "build_tool_agent_runner",
        lambda **kwargs: _ScriptedSessionRunner(text="correlated answer"),
    )

    router = _build_router(tmp_path, store=store)
    result = asyncio.run(
        router.run_session_followup(
            session_id=session_id,
            message="Why?",
            correlation_id="corr-42",
        )
    )

    assert result.correlation_id == "corr-42"


def test_build_interface_tool_router_import_from_tools_package() -> None:
    from ai_news_agent.tools import InterfaceToolRouter as PackageRouter
    from ai_news_agent.tools import build_interface_tool_router as package_build

    assert PackageRouter is not None
    assert package_build is not None
