"""Single application composition root (Milestone 8A.1 T13)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_news_agent.access import AccessConfig, llm_url_guard
from ai_news_agent.connectors.base import SourceConnector
from ai_news_agent.credential_health import (
    CredentialHealthStore,
    record_connector_health_from_digest,
)
from ai_news_agent.credentials import CredentialsProvider
from ai_news_agent.env import configure_bilibili_network_from_env, load_local_env
from ai_news_agent.graph.state import DigestResult, WorkflowError
from ai_news_agent.models import utcnow
from ai_news_agent.graph.workflow import (
    run_digest,
    run_digest_streaming,
)
from ai_news_agent.llm import build_chat_model, build_tool_chat_model
from ai_news_agent.logging_setup import get_logger
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
from ai_news_agent.source_settings import SourceSettingsService
from ai_news_agent.storage import DigestStore
from ai_news_agent.tools import build_interface_tool_router

logger = get_logger("digest_service")

_LLM_UNCONFIGURED_MESSAGE = (
    "Configure an LLM in Settings (API key) to generate digests."
)
_LLM_UNREADABLE_MESSAGE = (
    "Saved LLM credentials cannot be read. Restore AI_NEWS_AGENT_SECRET_KEY "
    "or replace them in Settings."
)


class _LlmConfigHolder:
    """Build and cache chat/tool models for the current credential version."""

    def __init__(
        self,
        credentials: CredentialsProvider,
        *,
        guard: Any | None = None,
    ) -> None:
        self._credentials = credentials
        self._guard = guard
        self._version: str | None = None
        self._chat_model: Any = None
        self._tool_model: Any = None

    def get(self) -> tuple[Any | None, Any | None]:
        llm = self._credentials.resolve_llm()
        version = llm.version
        configured = llm.status in ("ui", "env") and bool(llm.api_key)
        if not configured:
            if self._version != version:
                self._version = version
                self._chat_model = None
                self._tool_model = None
            return None, None

        if self._version != version or self._chat_model is None:
            self._version = version
            self._chat_model = build_chat_model(
                api_key=llm.api_key,
                base_url=llm.base_url,
                model=llm.model,
                guard=self._guard,
            )
            try:
                self._tool_model = build_tool_chat_model(
                    api_key=llm.api_key,
                    base_url=llm.base_url,
                    model=llm.model,
                    guard=self._guard,
                )
            except ValueError:
                self._tool_model = None
        return self._chat_model, self._tool_model


class _LazyLlmProxy:
    """Delegates chat-model calls to the holder's current built client."""

    def __init__(self, holder: _LlmConfigHolder) -> None:
        self._holder = holder

    def _model(self) -> Any | None:
        return self._holder.get()[0]

    def generate_entry_fields(self, context: dict[str, Any]) -> dict[str, Any]:
        model = self._model()
        if model is None:
            raise ValueError(_LLM_UNCONFIGURED_MESSAGE)
        return model.generate_entry_fields(context)

    def generate_followup_reply(self, *args: Any, **kwargs: Any) -> str:
        model = self._model()
        if model is None:
            raise ValueError(_LLM_UNCONFIGURED_MESSAGE)
        return model.generate_followup_reply(*args, **kwargs)

    def generate_general_answer(self, *args: Any, **kwargs: Any) -> str:
        model = self._model()
        if model is None:
            raise ValueError(_LLM_UNCONFIGURED_MESSAGE)
        return model.generate_general_answer(*args, **kwargs)

    def interpret_conversation(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        model = self._model()
        if model is None:
            raise ValueError(_LLM_UNCONFIGURED_MESSAGE)
        return model.interpret_conversation(*args, **kwargs)


class _LazyToolProxy:
    """Delegates tool-calling model calls to the holder's current client."""

    def __init__(self, holder: _LlmConfigHolder) -> None:
        self._holder = holder

    def _model(self) -> Any | None:
        return self._holder.get()[1]

    def bind_tools(self, tools: Any) -> Any:
        model = self._model()
        if model is None:
            raise ValueError(_LLM_UNCONFIGURED_MESSAGE)
        return model.bind_tools(tools)

    async def ainvoke(self, messages: Any) -> Any:
        model = self._model()
        if model is None:
            raise ValueError(_LLM_UNCONFIGURED_MESSAGE)
        return await model.ainvoke(messages)


def _digest_result_for_llm_block(
    req: DigestRequest,
    *,
    credentials: CredentialsProvider,
) -> DigestResult:
    llm = credentials.resolve_llm()
    message = (
        _LLM_UNREADABLE_MESSAGE
        if llm.status == "unreadable"
        else _LLM_UNCONFIGURED_MESSAGE
    )
    now = utcnow()
    return DigestResult(
        request=req,
        digest=None,
        run_id=None,
        markdown="",
        text=message,
        ranked_items=[],
        warnings=[],
        errors=[WorkflowError(stage="llm", message=message)],
        started_at=now,
        finished_at=now,
    )


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
    """Composition root for the CLI service and FastAPI."""

    fake: bool
    db_path: Path
    access: AccessConfig
    session_service: SessionService
    chat_service: ChatService
    digest_store: DigestStore
    source_settings_service: SourceSettingsService
    credentials_service: CredentialsProvider
    credential_health_store: CredentialHealthStore


def _record_digest_connector_health(
    *,
    result: DigestResult,
    req: DigestRequest,
    fake: bool,
    credentials_service: CredentialsProvider,
    health_store: CredentialHealthStore,
) -> None:
    if fake:
        return
    record_connector_health_from_digest(
        store=health_store,
        provider=credentials_service,
        warnings=list(result.warnings),
        connector_names=set(_names_from(req)),
    )


def build_application(
    *,
    fake: bool,
    db_path: Path,
    access: AccessConfig | None = None,
) -> Application:
    """Construct the application composition root."""
    resolved_access = access if access is not None else AccessConfig.from_environ()
    store = DigestStore(db_path)
    store.init_schema()
    source_settings_service = SourceSettingsService(db_path)
    credentials_service = CredentialsProvider(db_path)
    credential_health_store = CredentialHealthStore(db_path)
    session_service = SessionService(
        SessionStore(db_path),
        source_settings_service=source_settings_service,
    )
    chat_service = _build_chat_service(
        fake=fake,
        store=store,
        session_service=session_service,
        source_settings_service=source_settings_service,
        credentials_service=credentials_service,
        credential_health_store=credential_health_store,
        guard=None if fake else llm_url_guard(resolved_access),
    )
    return Application(
        fake=fake,
        db_path=db_path,
        access=resolved_access,
        session_service=session_service,
        chat_service=chat_service,
        digest_store=store,
        source_settings_service=source_settings_service,
        credentials_service=credentials_service,
        credential_health_store=credential_health_store,
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
    source_settings_service: SourceSettingsService,
    credentials_service: CredentialsProvider,
    credential_health_store: CredentialHealthStore,
    guard: Any | None = None,
) -> ChatService:
    llm_holder: _LlmConfigHolder | None = None
    if fake:
        model: Any = FakeDigestModel()
        tool_agent_runner: Any = _FakeToolAgentRunner()
        interface_router: Any = None
    else:
        llm_holder = _LlmConfigHolder(credentials_service, guard=guard)
        model = _LazyLlmProxy(llm_holder)
        tool_agent_runner = None
        interface_router = None

    creds = None if fake else credentials_service

    async def workflow_runner(
        req: DigestRequest,
        on_stage: Callable[[str], None] | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> DigestResult:
        del on_stage
        if not fake:
            load_local_env(force_reload=True)
            configure_bilibili_network_from_env(None)
            assert llm_holder is not None
            digest_model, _tool_model = llm_holder.get()
            if digest_model is None:
                return _digest_result_for_llm_block(req, credentials=credentials_service)
        else:
            digest_model = model
        connectors = build_connectors(fake=fake, names=_names_from(req), credentials=creds)
        try:
            result = await run_digest(
                req,
                connectors=list(connectors),
                model=digest_model,
                store=store,
                session_id=session_id,
                request_id=request_id,
            )
            _record_digest_connector_health(
                result=result,
                req=req,
                fake=fake,
                credentials_service=credentials_service,
                health_store=credential_health_store,
            )
            return result
        finally:
            await _aclose_connectors(connectors)

    async def streaming_workflow_runner(
        req: DigestRequest,
        on_stage: Callable[[str], None] | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> AsyncIterator[tuple[str, bool, DigestResult | None]]:
        del on_stage
        if not fake:
            load_local_env(force_reload=True)
            configure_bilibili_network_from_env(None)
            assert llm_holder is not None
            digest_model, _tool_model = llm_holder.get()
            if digest_model is None:
                blocked = _digest_result_for_llm_block(req, credentials=credentials_service)
                yield ("failed", True, blocked)
                return
        else:
            digest_model = model
        connectors = build_connectors(fake=fake, names=_names_from(req), credentials=creds)
        try:
            final_result: DigestResult | None = None
            async for event in run_digest_streaming(
                req,
                connectors=list(connectors),
                model=digest_model,
                store=store,
                session_id=session_id,
                request_id=request_id,
            ):
                if len(event) >= 3 and event[2] is not None:
                    final_result = event[2]
                yield event
            if final_result is not None:
                _record_digest_connector_health(
                    result=final_result,
                    req=req,
                    fake=fake,
                    credentials_service=credentials_service,
                    health_store=credential_health_store,
                )
        finally:
            await _aclose_connectors(connectors)

    if not fake and llm_holder is not None:
        interface_router = build_interface_tool_router(
            store=store,
            tool_model=_LazyToolProxy(llm_holder),
            github_factory=build_connector_factory(
                fake=fake, name="github", credentials=credentials_service
            ),
            bilibili_factory=build_connector_factory(
                fake=fake, name="bilibili", credentials=credentials_service
            ),
            juya_factory=build_connector_factory(fake=fake, name="juya", credentials=creds),
            huggingface_factory=build_connector_factory(
                fake=fake, name="huggingface", credentials=credentials_service
            ),
            zhihu_factory=build_connector_factory(
                fake=fake, name="zhihu", credentials=credentials_service
            ),
            openrouter_factory=build_connector_factory(
                fake=fake, name="openrouter", credentials=credentials_service
            ),
            interface_name="api",
        )

    hf_factory = (
        None
        if fake
        else build_connector_factory(
            fake=fake, name="huggingface", credentials=credentials_service
        )
    )
    juya_factory = build_connector_factory(fake=fake, name="juya", credentials=creds)

    return ChatService(
        store=store,
        workflow_runner=workflow_runner,
        streaming_workflow_runner=streaming_workflow_runner,
        chat_model=model,
        tool_agent_runner=tool_agent_runner,
        interface_router=interface_router,
        session_service=session_service,
        source_settings_service=source_settings_service,
        conversation_model=None if fake else model,
        huggingface_connector_factory=hf_factory,
        juya_connector_factory=juya_factory,
    )
