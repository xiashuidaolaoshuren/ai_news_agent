"""Shared live-mode tool router for browser-session follow-ups (Milestone 4 T12)."""

from __future__ import annotations

from typing import Any

from ai_news_agent.logging_setup import get_logger
from ai_news_agent.storage import DigestStore
from ai_news_agent.tools.agent import _DEFAULT_FALLBACK, build_tool_agent_runner
from ai_news_agent.tools.registry import ConnectorFactory, build_tool_registry
from ai_news_agent.tools.schemas import (
    InterfaceAgentResult,
    InterfaceAgentResultKind,
)

logger = get_logger("interface_router")

_OPEN_ENDED_GUIDANCE = (
    "I need a configured language model to answer that question. "
    "Try a concrete request like listing sources or asking for caveats."
)


class _SessionScopedStore:
    """Store view whose shared follow-up context is one session's own digest.

    Everything else delegates to the real store so tool calls, digests, and
    history reads behave identically. Used to keep browser-session follow-ups
    isolated from other sessions' context.
    """

    def __init__(self, store: Any, session_id: str) -> None:
        self._store = store
        self._session_id = session_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def get_latest_followup_context(self) -> Any:
        return self._store.get_followup_context_for_session(self._session_id)


class InterfaceToolRouter:
    """Answers open-ended session follow-ups through the bounded tool agent."""

    def __init__(
        self,
        *,
        store: DigestStore,
        tool_model: Any,
        github_factory: ConnectorFactory,
        bilibili_factory: ConnectorFactory,
        juya_factory: ConnectorFactory,
        huggingface_factory: ConnectorFactory | None = None,
        zhihu_factory: ConnectorFactory | None = None,
        interface_name: str,
        fallback_text: str = _DEFAULT_FALLBACK,
    ) -> None:
        self._store = store
        self._tool_model = tool_model
        self._github_factory = github_factory
        self._bilibili_factory = bilibili_factory
        self._juya_factory = juya_factory
        self._huggingface_factory = huggingface_factory
        self._zhihu_factory = zhihu_factory
        self._interface_name = interface_name
        self._fallback_text = fallback_text

    async def run_session_followup(
        self,
        *,
        session_id: str,
        message: str,
        correlation_id: str | None = None,
    ) -> InterfaceAgentResult:
        """Answer an open-ended follow-up using only this session's digest context."""
        scoped_store = _SessionScopedStore(self._store, session_id)
        registry = build_tool_registry(
            store=scoped_store,
            github_factory=self._github_factory,
            bilibili_factory=self._bilibili_factory,
            juya_factory=self._juya_factory,
            huggingface_factory=self._huggingface_factory,
            zhihu_factory=self._zhihu_factory,
        )
        runner = build_tool_agent_runner(
            registry=registry,
            model=self._tool_model,
            fallback_text=self._fallback_text,
        )

        agent_result: InterfaceAgentResult | None = None
        fallback_reason = "model_failure"
        try:
            agent_result = await runner.run(message)
        except Exception as exc:
            logger.error(
                "session follow-up agent failed session_id=%s interface=%s error=%r",
                session_id,
                self._interface_name,
                exc,
            )
        else:
            if agent_result.kind is InterfaceAgentResultKind.CONVERSATIONAL:
                return self._with_correlation(agent_result, correlation_id)
            fallback_reason = agent_result.fallback_reason or "agent_mismatch"

        logger.info(
            "interface deterministic_fallback intent=open_ended_followup "
            "reason=%s interface=%s",
            fallback_reason,
            self._interface_name,
        )
        progress_lines = (
            list(agent_result.progress_lines or []) if agent_result is not None else []
        )
        return self._with_correlation(
            InterfaceAgentResult(
                kind=InterfaceAgentResultKind.FALLBACK,
                text=_OPEN_ENDED_GUIDANCE,
                fallback_reason=fallback_reason,
                progress_lines=progress_lines,
            ),
            correlation_id,
        )

    def _with_correlation(
        self,
        result: InterfaceAgentResult,
        correlation_id: str | None,
    ) -> InterfaceAgentResult:
        if correlation_id is None:
            return result
        return result.model_copy(update={"correlation_id": correlation_id})


def build_interface_tool_router(
    *,
    store: DigestStore,
    tool_model: Any,
    github_factory: ConnectorFactory,
    bilibili_factory: ConnectorFactory,
    juya_factory: ConnectorFactory,
    huggingface_factory: ConnectorFactory | None = None,
    zhihu_factory: ConnectorFactory | None = None,
    interface_name: str,
    fallback_text: str = _DEFAULT_FALLBACK,
) -> InterfaceToolRouter:
    """Construct the shared tool router for live browser-session follow-ups."""
    return InterfaceToolRouter(
        store=store,
        tool_model=tool_model,
        github_factory=github_factory,
        bilibili_factory=bilibili_factory,
        juya_factory=juya_factory,
        huggingface_factory=huggingface_factory,
        zhihu_factory=zhihu_factory,
        interface_name=interface_name,
        fallback_text=fallback_text,
    )


__all__ = ["InterfaceToolRouter", "build_interface_tool_router"]
