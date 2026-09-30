"""Single application composition root (Milestone 8A.1 T13)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_news_agent.connectors.base import SourceConnector
from ai_news_agent.env import configure_bilibili_network_from_env, load_local_env
from ai_news_agent.app.digest_service import DigestServiceRuntime, digest_request_from_json
from ai_news_agent.graph.state import DigestResult
from ai_news_agent.graph.workflow import run_digest, run_digest_streaming
from ai_news_agent.llm import build_chat_model, build_tool_chat_model
from ai_news_agent.repositories.session_store import SessionStore
from ai_news_agent.request import DigestRequest
from ai_news_agent.services.chat import ChatService
from ai_news_agent.services.session_service import SessionService
from ai_news_agent.sources import (
    DEFAULT_SOURCE_NAMES,
    FakeDigestModel,
    build_connector_factory,
    build_connectors,
)
from ai_news_agent.storage import DigestStore
from ai_news_agent.tools import build_interface_tool_router

_FAKE_TOOL_AGENT_REPLY = (
    "Offline fake tool agent: use structured prompts like "
    '"show sources", "study first", or "show caveats".'
)


class _FakeToolAgentRunner:
    """Deterministic tool agent for fake mode (no tool-calling model)."""

    async def run(self, question: str) -> str:  # noqa: ARG002
        return _FAKE_TOOL_AGENT_REPLY

    async def run_streaming(
        self, question: str
    ) -> AsyncIterator[tuple[str, bool, str | None]]:
        del question
        yield "Calling load_latest_digest…", False, None
        yield "Done load_latest_digest: Loaded latest digest.", False, None
        yield "", True, _FAKE_TOOL_AGENT_REPLY


async def _aclose_connectors(connectors: Sequence[SourceConnector]) -> None:
    for connector in connectors:
        closer = getattr(connector, "aclose", None)
        if closer is not None:
            await closer()


@dataclass(frozen=True)
class Application:
    """Composition root for Gradio, CLI service, and FastAPI."""

    fake: bool
    db_path: Path
    session_service: SessionService
    chat_service: ChatService
    digest_store: DigestStore
    openclaw_runtime: DigestServiceRuntime


def build_application(*, fake: bool, db_path: Path) -> Application:
    """Construct the application composition root."""
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    chat_service = _build_chat_service(
        fake=fake,
        store=store,
        session_service=session_service,
    )
    return Application(
        fake=fake,
        db_path=db_path,
        session_service=session_service,
        chat_service=chat_service,
        digest_store=store,
        openclaw_runtime=DigestServiceRuntime(
            fake=fake,
            db_path=db_path,
            store=store,
        ),
    )


def _names_from(req: DigestRequest) -> list[str]:
    return (
        list(req.connector_names)
        if req.connector_names is not None
        else list(DEFAULT_SOURCE_NAMES)
    )


def _build_chat_service(
    *,
    fake: bool,
    store: DigestStore,
    session_service: SessionService,
) -> ChatService:
    if fake:
        model: Any = FakeDigestModel()
        tool_agent_runner: Any = _FakeToolAgentRunner()
        interface_router: Any = None
    else:
        model = build_chat_model()
        tool_model = build_tool_chat_model()
        tool_agent_runner = None
        interface_router = None

    async def workflow_runner(
        req: DigestRequest,
        on_stage: Callable[[str], None] | None = None,
        session_id: str | None = None,
    ) -> DigestResult:
        del on_stage
        if not fake:
            load_local_env(force_reload=True)
            configure_bilibili_network_from_env(None)
        connectors = build_connectors(fake=fake, names=_names_from(req))
        try:
            return await run_digest(
                req,
                connectors=list(connectors),
                model=model,
                store=store,
                session_id=session_id,
            )
        finally:
            await _aclose_connectors(connectors)

    async def streaming_workflow_runner(
        req: DigestRequest,
        on_stage: Callable[[str], None] | None = None,
        session_id: str | None = None,
    ) -> AsyncIterator[tuple[str, bool, DigestResult | None]]:
        del on_stage
        if not fake:
            load_local_env(force_reload=True)
            configure_bilibili_network_from_env(None)
        connectors = build_connectors(fake=fake, names=_names_from(req))
        try:
            async for event in run_digest_streaming(
                req,
                connectors=list(connectors),
                model=model,
                store=store,
                session_id=session_id,
            ):
                yield event
        finally:
            await _aclose_connectors(connectors)

    if not fake:
        interface_router = build_interface_tool_router(
            store=store,
            workflow_runner=workflow_runner,
            streaming_workflow_runner=streaming_workflow_runner,
            tool_model=tool_model,
            digest_model=model,
            github_factory=build_connector_factory(fake=fake, name="github"),
            bilibili_factory=build_connector_factory(fake=fake, name="bilibili"),
            juya_factory=build_connector_factory(fake=fake, name="juya"),
            huggingface_factory=build_connector_factory(fake=fake, name="huggingface"),
            zhihu_factory=build_connector_factory(fake=fake, name="zhihu"),
            build_connectors_fn=lambda req: build_connectors(
                fake=fake, names=_names_from(req)
            ),
            interface_name="api",
        )

    return ChatService(
        store=store,
        workflow_runner=workflow_runner,
        streaming_workflow_runner=streaming_workflow_runner,
        chat_model=model,
        tool_agent_runner=tool_agent_runner,
        interface_router=interface_router,
        session_service=session_service,
    )
