"""Follow-up chat service and typed session event stream (8A.1 T10)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, TypeVar

from ai_news_agent.digest_request_builder import resolve_digest_request
from ai_news_agent.graph.state import DigestResult, WorkflowError
from ai_news_agent.models import ConnectorWarning, Digest
from ai_news_agent.logging_setup import get_logger
from ai_news_agent.followup_structured import NO_SAVED_DIGEST, answer_structured_followup
from ai_news_agent.history_interface import (
    HISTORY_NOT_FOUND,
    HistoryChatCommand,
    format_history_search_text,
    parse_history_chat_message,
)
from ai_news_agent.history_search import search_digest_history, show_historical_item
from ai_news_agent.rendering import format_connector_warnings_notice
from ai_news_agent.request import DigestRequest
from ai_news_agent.services.session_records import SessionRequestRecord
from ai_news_agent.services.session_service import (
    CANCELLED_ASSISTANT_MESSAGE,
    SessionService,
)
from ai_news_agent.storage import DigestStore, FollowupContext
from ai_news_agent.streaming import iter_text_chunks
from ai_news_agent.tools.schemas import (
    InterfaceAgentResult,
    InterfaceAgentResultKind,
)

WorkflowRunner = Callable[[DigestRequest], Awaitable[DigestResult]]
StreamingWorkflowRunner = Callable[
    [DigestRequest],
    AsyncIterator[tuple[str, bool, DigestResult | None]],
]

logger = get_logger("chat")

_StreamPayloadT = TypeVar("_StreamPayloadT")

_TERMINAL_REPLAY_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)
_WORKFLOW_ERROR_CODE = "workflow_error"
_WORKFLOW_ERROR_MESSAGE = "Digest generation failed."
_REQUEST_FAILED_CODE = "request_failed"
_REQUEST_FAILED_MESSAGE = "Request failed."


@dataclass(frozen=True)
class StartedEvent:
    request_id: str
    user_message_id: int


@dataclass(frozen=True)
class ProgressEvent:
    stage: str


@dataclass(frozen=True)
class DeltaEvent:
    text: str


@dataclass(frozen=True)
class DigestEvent:
    run_id: int
    digest: Digest
    markdown: str
    warnings: list[ConnectorWarning]
    errors: list[WorkflowError]


@dataclass(frozen=True)
class DoneEvent:
    request_id: str
    message_id: int
    run_id: int | None
    path: str


@dataclass(frozen=True)
class ErrorEvent:
    request_id: str
    code: str
    message: str
    correlation_id: str


ChatEvent = (
    StartedEvent
    | ProgressEvent
    | DeltaEvent
    | DigestEvent
    | DoneEvent
    | ErrorEvent
)


class ChatService:
    """Hybrid routing: digest workflow vs deterministic vs LLM-grounded follow-ups.

    For open-ended follow-ups, pass ``chat_model`` with::

        def generate_followup_reply(self, *, question: str, grounding: dict) -> str: ...

    Grounding is built only from ``DigestStore.get_latest_followup_context()`` data.
    """

    def __init__(
        self,
        *,
        store: DigestStore,
        workflow_runner: WorkflowRunner,
        streaming_workflow_runner: StreamingWorkflowRunner | None = None,
        chat_model: Any | None = None,
        tool_agent_runner: Any | None = None,
        interface_router: Any | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self._store = store
        self._workflow_runner = workflow_runner
        self._streaming_workflow_runner = streaming_workflow_runner
        self._chat_model = chat_model
        self._tool_agent_runner = tool_agent_runner
        self._interface_router = interface_router
        self._session_service = session_service

    def handle_message(
        self,
        message: str,
        *,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
    ) -> str:
        """Sync wrapper for UI/CLI callers."""
        return asyncio.run(
            self.handle_message_async(
                message,
                digest_request=digest_request,
                session_connector_names=session_connector_names,
                session_items_per_source=session_items_per_source,
            )
        )

    async def handle_message_async(
        self,
        message: str,
        *,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
    ) -> str:
        preview = _message_preview(message)
        logger.info("chat message received preview=%r", preview)

        history_cmd = parse_history_chat_message(message)
        if history_cmd is not None:
            logger.info("chat path=history action=%s", history_cmd.action)
            return self._handle_history_command(history_cmd)

        if self._interface_router is not None:
            result = await self._interface_router.route(
                message=message,
                digest_request=digest_request,
                session_connector_names=session_connector_names,
                session_items_per_source=session_items_per_source,
            )
            return _interface_result_to_text(result, store=self._store)

        if digest_request is not None or _message_requests_digest(message):
            req = _resolve_digest_request(
                message,
                digest_request=digest_request,
                session_connector_names=session_connector_names,
                session_items_per_source=session_items_per_source,
            )
            t0 = time.perf_counter()
            result = await self._workflow_runner(req)
            elapsed = time.perf_counter() - t0
            _log_digest_result(result, elapsed=elapsed)
            return _user_facing_digest_text(result)

        return await self._handle_followup_message_async(message)

    async def _handle_followup_message_async(self, message: str) -> str:
        ctx = self._store.get_latest_followup_context()
        if ctx.run_id is None and ctx.digest is None:
            logger.info("follow-up path=no_saved_digest")
            return NO_SAVED_DIGEST

        structured = answer_structured_followup(message, ctx)
        if structured is not None:
            logger.info("follow-up path=structured")
            return structured

        if self._tool_agent_runner is not None:
            logger.info("follow-up path=tool_agent")
            result = await self._tool_agent_runner.run(message)
            return _tool_agent_result_to_text(result, store=self._store)

        llm_text = _try_llm_followup(self._chat_model, message, ctx)
        if llm_text is not None:
            logger.info("follow-up path=llm")
            return llm_text

        logger.info("follow-up path=guidance_fallback")
        return (
            "I need a configured language model to answer that question. "
            "Try a concrete request like listing sources or asking for caveats."
        )

    async def handle_message_streaming_async(
        self,
        message: str,
        *,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
        chunk_size: int = 80,
        chunk_delay_s: float = 0.02,
    ) -> AsyncIterator[str]:
        preview = _message_preview(message)
        logger.info("chat streaming message received preview=%r", preview)

        history_cmd = parse_history_chat_message(message)
        if history_cmd is not None:
            logger.info("chat streaming path=history action=%s", history_cmd.action)
            text = self._handle_history_command(history_cmd)
            async for chunk in iter_text_chunks(
                text,
                chunk_size=chunk_size,
                delay_s=chunk_delay_s,
            ):
                yield chunk
            return

        if self._interface_router is not None:
            async def _router_events() -> AsyncIterator[
                tuple[str, bool, InterfaceAgentResult | None]
            ]:
                async for progress, done, payload in self._interface_router.route_streaming(
                    message=message,
                    digest_request=digest_request,
                    session_connector_names=session_connector_names,
                    session_items_per_source=session_items_per_source,
                ):
                    yield progress, done, payload

            async for chunk in _stream_ephemeral_progress_then_chunks(
                _router_events(),
                chunk_size=chunk_size,
                chunk_delay_s=chunk_delay_s,
                extract_final_text=lambda result: _interface_result_to_text(
                    result, store=self._store
                ),
            ):
                yield chunk
            return

        if digest_request is not None or _message_requests_digest(message):
            req = _resolve_digest_request(
                message,
                digest_request=digest_request,
                session_connector_names=session_connector_names,
                session_items_per_source=session_items_per_source,
            )
            if self._streaming_workflow_runner is not None:
                t0 = time.perf_counter()
                final_result: DigestResult | None = None

                async def _digest_events() -> AsyncIterator[
                    tuple[str, bool, DigestResult | None]
                ]:
                    nonlocal final_result
                    async for progress, done, result in self._streaming_workflow_runner(
                        req
                    ):
                        if done and result is not None:
                            final_result = result
                        yield progress, done, result

                async for chunk in _stream_ephemeral_progress_then_chunks(
                    _digest_events(),
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                    extract_final_text=_user_facing_digest_text,
                ):
                    yield chunk
                if final_result is not None:
                    _log_digest_result(
                        final_result, elapsed=time.perf_counter() - t0
                    )
                return

            t0 = time.perf_counter()
            result = await self._workflow_runner(req)
            elapsed = time.perf_counter() - t0
            _log_digest_result(result, elapsed=elapsed)
            async for chunk in iter_text_chunks(
                _user_facing_digest_text(result),
                chunk_size=chunk_size,
                delay_s=chunk_delay_s,
            ):
                yield chunk
            return

        if self._tool_agent_runner is not None:
            async for chunk in self._stream_followup_tool_agent_async(
                message,
                chunk_size=chunk_size,
                chunk_delay_s=chunk_delay_s,
            ):
                yield chunk
            return

        text = await self._handle_followup_message_async(message)
        async for chunk in iter_text_chunks(
            text,
            chunk_size=chunk_size,
            delay_s=chunk_delay_s,
        ):
            yield chunk

    async def stream_events(
        self,
        message: str,
        *,
        session_id: str,
        request_id: str | None = None,
        chunk_size: int = 80,
        chunk_delay_s: float = 0.02,
    ) -> AsyncIterator[ChatEvent]:
        if self._session_service is None:
            raise RuntimeError("session_service is required for stream_events")

        record = self._session_service.begin_request(
            session_id,
            content=message,
            request_id=request_id,
        )
        if record.status in _TERMINAL_REPLAY_STATUSES:
            async for event in self._replay_terminal_events(
                session_id,
                record,
                chunk_size=chunk_size,
                chunk_delay_s=chunk_delay_s,
            ):
                yield event
            return

        yield StartedEvent(
            request_id=record.id,
            user_message_id=record.user_message_id,
        )

        history_cmd = parse_history_chat_message(message)
        try:
            if history_cmd is not None:
                async for event in self._stream_session_text_events(
                    session_id=session_id,
                    record=record,
                    text=self._handle_history_command(history_cmd),
                    path="followup",
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

            if _message_requests_digest(message):
                async for event in self._stream_session_digest_events(
                    session_id=session_id,
                    record=record,
                    message=message,
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

            async for event in self._stream_session_followup_events(
                session_id=session_id,
                record=record,
                message=message,
                chunk_size=chunk_size,
                chunk_delay_s=chunk_delay_s,
            ):
                yield event
        except Exception as exc:
            async for event in self._emit_request_failed_events(
                session_id,
                record,
                exc=exc,
            ):
                yield event

    async def _stream_session_digest_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        message: str,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        req = self._session_service.build_request(session_id, message)
        runner = self._iter_streaming_runner(
            req,
            session_id=session_id,
            request_id=record.id,
        )
        while True:
            try:
                progress, done, result = await anext(runner)
            except StopAsyncIteration:
                break
            except Exception:
                logger.exception(
                    "session digest workflow failed session_id=%s",
                    session_id,
                )
                try:
                    self._session_service.complete_request(
                        session_id,
                        record.id,
                        status="failed",
                        content=_WORKFLOW_ERROR_MESSAGE,
                        error_code=_WORKFLOW_ERROR_CODE,
                        error_message=_WORKFLOW_ERROR_MESSAGE,
                    )
                except KeyError:
                    cancelled = self._cancelled_error_event(session_id, record)
                    if cancelled is not None:
                        yield cancelled
                        return
                    raise
                yield ErrorEvent(
                    request_id=record.id,
                    code=_WORKFLOW_ERROR_CODE,
                    message=_WORKFLOW_ERROR_MESSAGE,
                    correlation_id=record.correlation_id,
                )
                return

            if not done:
                cancelled = self._cancelled_error_event(session_id, record)
                if cancelled is not None:
                    yield cancelled
                    return
                if progress:
                    yield ProgressEvent(stage=progress)
                continue

            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            if result is None:
                continue
            if result.run_id is None:
                failure_message = _digest_failure_message(result)
                try:
                    self._session_service.complete_request(
                        session_id,
                        record.id,
                        status="failed",
                        content=failure_message,
                        error_code=_WORKFLOW_ERROR_CODE,
                        error_message=failure_message,
                    )
                except KeyError:
                    cancelled = self._cancelled_error_event(session_id, record)
                    if cancelled is not None:
                        yield cancelled
                        return
                    raise
                yield ErrorEvent(
                    request_id=record.id,
                    code=_WORKFLOW_ERROR_CODE,
                    message=failure_message,
                    correlation_id=record.correlation_id,
                )
                return
            text = _user_facing_digest_text(result)
            async for chunk in iter_text_chunks(
                text,
                chunk_size=chunk_size,
                delay_s=chunk_delay_s,
            ):
                cancelled = self._cancelled_error_event(session_id, record)
                if cancelled is not None:
                    yield cancelled
                    return
                yield DeltaEvent(text=chunk)
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            if result.digest is not None and result.run_id is not None:
                yield DigestEvent(
                    run_id=result.run_id,
                    digest=result.digest,
                    markdown=result.markdown,
                    warnings=result.warnings,
                    errors=result.errors,
                )
            try:
                message_id = self._session_service.complete_request(
                    session_id,
                    record.id,
                    status="succeeded",
                    content=text,
                    run_id=result.run_id,
                )
            except KeyError:
                cancelled = self._cancelled_error_event(session_id, record)
                if cancelled is not None:
                    yield cancelled
                    return
                raise
            yield DoneEvent(
                request_id=record.id,
                message_id=message_id,
                run_id=result.run_id,
                path="digest",
            )

    async def _emit_request_failed_events(
        self,
        session_id: str,
        record: SessionRequestRecord,
        *,
        exc: Exception,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        logger.exception(
            "session request failed session_id=%s request_id=%s",
            session_id,
            record.id,
            exc_info=exc,
        )
        cancelled = self._cancelled_error_event(session_id, record)
        if cancelled is not None:
            yield cancelled
            return
        try:
            self._session_service.complete_request(
                session_id,
                record.id,
                status="failed",
                content=_REQUEST_FAILED_MESSAGE,
                error_code=_REQUEST_FAILED_CODE,
                error_message=_REQUEST_FAILED_MESSAGE,
            )
        except KeyError:
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            raise
        yield ErrorEvent(
            request_id=record.id,
            code=_REQUEST_FAILED_CODE,
            message=_REQUEST_FAILED_MESSAGE,
            correlation_id=record.correlation_id,
        )

    def _cancelled_error_event(
        self,
        session_id: str,
        record: SessionRequestRecord,
    ) -> ErrorEvent | None:
        assert self._session_service is not None
        current = self._session_service.get_request(session_id, record.id)
        if current is None or current.status != "cancelled":
            return None
        return ErrorEvent(
            request_id=record.id,
            code="cancelled",
            message=CANCELLED_ASSISTANT_MESSAGE,
            correlation_id=record.correlation_id,
        )

    async def _stream_session_followup_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        message: str,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        text = await self._handle_session_followup_message_async(session_id, message)
        cancelled = self._cancelled_error_event(session_id, record)
        if cancelled is not None:
            yield cancelled
            return
        async for event in self._stream_session_text_events(
            session_id=session_id,
            record=record,
            text=text,
            path="followup",
            chunk_size=chunk_size,
            chunk_delay_s=chunk_delay_s,
        ):
            yield event

    async def _stream_session_text_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        text: str,
        path: str,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        async for chunk in iter_text_chunks(
            text,
            chunk_size=chunk_size,
            delay_s=chunk_delay_s,
        ):
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            yield DeltaEvent(text=chunk)
        cancelled = self._cancelled_error_event(session_id, record)
        if cancelled is not None:
            yield cancelled
            return
        try:
            message_id = self._session_service.complete_request(
                session_id,
                record.id,
                status="succeeded",
                content=text,
            )
        except KeyError:
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            raise
        yield DoneEvent(
            request_id=record.id,
            message_id=message_id,
            run_id=None,
            path=path,
        )

    async def _replay_terminal_events(
        self,
        session_id: str,
        record: SessionRequestRecord,
        *,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        yield StartedEvent(
            request_id=record.id,
            user_message_id=record.user_message_id,
        )
        assert self._session_service is not None
        text = ""
        if record.assistant_message_id is not None:
            for message in self._session_service.list_messages(session_id):
                if message.id == record.assistant_message_id:
                    text = message.content
                    break
        async for chunk in iter_text_chunks(
            text,
            chunk_size=chunk_size,
            delay_s=chunk_delay_s,
        ):
            yield DeltaEvent(text=chunk)
        if record.status == "succeeded":
            if record.run_id is not None:
                digest = self._store.get_digest_by_run_id(record.run_id)
                if digest is not None:
                    yield DigestEvent(
                        run_id=record.run_id,
                        digest=digest,
                        markdown=text,
                        warnings=self._store.get_connector_warnings_for_run(
                            record.run_id
                        ),
                        errors=[],
                    )
            yield DoneEvent(
                request_id=record.id,
                message_id=record.assistant_message_id or 0,
                run_id=record.run_id,
                path="digest" if record.run_id is not None else "followup",
            )
            return
        yield ErrorEvent(
            request_id=record.id,
            code=record.error_code or record.status,
            message=record.error_message or text,
            correlation_id=record.correlation_id,
        )

    async def _iter_streaming_runner(
        self,
        req: DigestRequest,
        *,
        session_id: str,
        request_id: str,
    ) -> AsyncIterator[tuple[str, bool, DigestResult | None]]:
        if self._streaming_workflow_runner is not None:
            try:
                stream = self._streaming_workflow_runner(
                    req,
                    session_id=session_id,
                    request_id=request_id,
                )
            except TypeError:
                stream = self._streaming_workflow_runner(req)
            async for event in stream:
                yield event
            return
        try:
            result = await self._workflow_runner(
                req,
                session_id=session_id,
                request_id=request_id,
            )
        except TypeError:
            result = await self._workflow_runner(req)
        yield "", True, result

    async def _handle_session_followup_message_async(
        self,
        session_id: str,
        message: str,
    ) -> str:
        ctx = self._store.get_followup_context_for_session(session_id)
        if ctx.run_id is None and ctx.digest is None:
            logger.info("follow-up path=no_saved_digest session_id=%s", session_id)
            return NO_SAVED_DIGEST

        structured = answer_structured_followup(message, ctx)
        if structured is not None:
            logger.info("follow-up path=structured session_id=%s", session_id)
            return structured

        run_session_followup = getattr(
            self._interface_router,
            "run_session_followup",
            None,
        )
        if callable(run_session_followup):
            logger.info("follow-up path=tool_agent session_id=%s", session_id)
            result = await run_session_followup(
                session_id=session_id,
                message=message,
            )
            return _interface_result_to_text(result, store=self._store)

        if self._tool_agent_runner is not None:
            logger.info("follow-up path=tool_agent session_id=%s", session_id)
            result = await self._tool_agent_runner.run(message)
            return _tool_agent_result_to_text(result, store=self._store)

        llm_text = _try_llm_followup(self._chat_model, message, ctx)
        if llm_text is not None:
            logger.info("follow-up path=llm session_id=%s", session_id)
            return llm_text

        logger.info("follow-up path=guidance_fallback session_id=%s", session_id)
        return (
            "I need a configured language model to answer that question. "
            "Try a concrete request like listing sources or asking for caveats."
        )

    async def _stream_followup_tool_agent_async(
        self,
        message: str,
        *,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[str]:
        ctx = self._store.get_latest_followup_context()
        if ctx.run_id is None and ctx.digest is None:
            logger.info("follow-up path=no_saved_digest")
            yield NO_SAVED_DIGEST
            return

        structured = answer_structured_followup(message, ctx)
        if structured is not None:
            logger.info("follow-up path=structured")
            async for chunk in iter_text_chunks(
                structured,
                chunk_size=chunk_size,
                delay_s=chunk_delay_s,
            ):
                yield chunk
            return

        logger.info("follow-up path=tool_agent")
        runner = self._tool_agent_runner
        run_streaming = getattr(runner, "run_streaming", None)
        if callable(run_streaming):
            async for chunk in _stream_ephemeral_progress_then_chunks(
                run_streaming(message),
                chunk_size=chunk_size,
                chunk_delay_s=chunk_delay_s,
                extract_final_text=lambda result: _tool_agent_result_to_text(
                    result,
                    store=self._store,
                ),
            ):
                yield chunk
            return

        text = _tool_agent_result_to_text(
            await runner.run(message),
            store=self._store,
        )
        async for chunk in iter_text_chunks(
            text,
            chunk_size=chunk_size,
            delay_s=chunk_delay_s,
        ):
            yield chunk


    def _handle_history_command(self, cmd: HistoryChatCommand) -> str:
        if cmd.error is not None:
            return cmd.error
        if cmd.action == "search":
            if cmd.query is None:
                raise NotImplementedError
            result = search_digest_history(self._store, cmd.query)
            return format_history_search_text(result)
        if cmd.action == "open":
            if cmd.token is None:
                return HISTORY_NOT_FOUND
            text = show_historical_item(self._store, cmd.token)
            return text if text is not None else HISTORY_NOT_FOUND
        raise NotImplementedError


async def _stream_ephemeral_progress_then_chunks(
    events: AsyncIterator[tuple[str, bool, _StreamPayloadT | None]],
    *,
    chunk_size: int,
    chunk_delay_s: float,
    extract_final_text: Callable[[_StreamPayloadT], str],
) -> AsyncIterator[str]:
    """Yield ephemeral progress lines, then chunked final text without progress."""
    async for progress, done, payload in events:
        if not done:
            if progress:
                yield progress
            continue
        if payload is None:
            continue
        text = extract_final_text(payload)
        async for chunk in iter_text_chunks(
            text,
            chunk_size=chunk_size,
            delay_s=chunk_delay_s,
        ):
            yield chunk


def _tool_agent_result_to_text(result: Any, *, store: DigestStore | None = None) -> str:
    if isinstance(result, InterfaceAgentResult):
        return _interface_result_to_text(result, store=store)
    return str(result)


def _interface_result_to_text(
    result: InterfaceAgentResult,
    *,
    store: DigestStore | None = None,
) -> str:
    if result.kind is InterfaceAgentResultKind.DIGEST:
        warnings: list = []
        errors: list = []
        if store is not None and result.run_id is not None:
            ctx = store.get_latest_followup_context()
            if ctx.run_id == result.run_id:
                warnings = ctx.warnings
        notice = format_connector_warnings_notice(warnings, errors)
        if not notice:
            return result.text
        if notice in result.text:
            return result.text
        return f"{notice}\n\n{result.text}"
    return result.text


def _digest_failure_message(result: DigestResult) -> str:
    for error in result.errors:
        if error.message:
            return error.message
    return _WORKFLOW_ERROR_MESSAGE


def _user_facing_digest_text(result: DigestResult) -> str:
    notice = format_connector_warnings_notice(result.warnings, result.errors)
    if not notice:
        return result.text
    if notice in result.text:
        return result.text
    return f"{notice}\n\n{result.text}"


def _apply_session_items_per_source(
    req: DigestRequest,
    session_items_per_source: int | None,
) -> DigestRequest:
    if session_items_per_source is None:
        return req
    return replace(
        req,
        items_per_source=session_items_per_source,
        max_items_per_source=max(req.max_items_per_source, session_items_per_source),
    )


def _resolve_digest_request(
    message: str,
    *,
    digest_request: DigestRequest | None,
    session_connector_names: list[str] | None,
    session_items_per_source: int | None = None,
) -> DigestRequest:
    if digest_request is not None:
        req = digest_request
        logger.info(
            "digest path=explicit_request topics=%d connector_names=%s items_per_source=%s",
            len(req.topics),
            req.connector_names,
            req.items_per_source,
        )
        return req

    req = resolve_digest_request(message, session_connector_names=session_connector_names)
    req = _apply_session_items_per_source(req, session_items_per_source)
    logger.info(
        "digest path=resolved_request explicit=%s timeframe=%r connector_names=%s "
        "items_per_source=%s",
        req.has_explicit_selectors(),
        req.timeframe,
        req.connector_names,
        req.items_per_source,
    )
    return req


def _log_digest_result(result: DigestResult, *, elapsed: float) -> None:
    logger.info(
        "digest completed run_id=%s entries=%d warnings=%d errors=%d elapsed=%.2fs",
        result.run_id,
        len(result.digest.entries) if result.digest else 0,
        len(result.warnings),
        len(result.errors),
        elapsed,
    )
    if result.warnings:
        for w in result.warnings:
            if w.detail:
                logger.warning(
                    "[%s] %s: %s | detail=%s",
                    w.connector,
                    w.code,
                    w.message,
                    w.detail[:300],
                )
            else:
                logger.warning(
                    "[%s] %s: %s",
                    w.connector,
                    w.code,
                    w.message,
                )
    if result.errors:
        for err in result.errors:
            logger.error(
                "workflow stage=%s: %s",
                err.stage,
                err.message,
            )


def _message_preview(message: str, *, max_len: int = 120) -> str:
    s = " ".join(message.split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _message_requests_digest(message: str) -> bool:
    low = message.strip().lower()
    if not low:
        return False
    triggers = (
        "digest",
        "today's ai",
        "todays ai",
        "give me today's",
        "give me todays",
        "generate digest",
        "run digest",
        "ai digest",
        "news digest",
    )
    if any(t in low for t in triggers):
        return True
    from ai_news_agent.intent import parse_connector_names_from_message

    return parse_connector_names_from_message(message) is not None


def _try_llm_followup(model: Any | None, question: str, ctx: FollowupContext) -> str | None:
    if model is None:
        return None
    fn = getattr(model, "generate_followup_reply", None)
    if fn is None or not callable(fn):
        return None
    grounding = _build_grounding_context(ctx)
    return str(fn(question=question, grounding=grounding))


def _build_grounding_context(ctx: FollowupContext) -> dict[str, Any]:
    out: dict[str, Any] = {
        "run_id": ctx.run_id,
        "warnings": [
            {
                "connector": w.connector,
                "code": w.code,
                "message": w.message,
                "detail": w.detail,
            }
            for w in ctx.warnings
        ],
    }
    if ctx.digest:
        out["digest"] = {
            "topics": ctx.digest.topics,
            "timeframe": ctx.digest.timeframe,
            "generated_at": ctx.digest.generated_at.isoformat(),
            "entries": [
                {
                    "title": e.title,
                    "source_url": e.source_url,
                    "summary": e.summary,
                    "why_it_matters": e.why_it_matters,
                    "confidence_caveat": e.confidence_caveat,
                }
                for e in ctx.digest.entries
            ],
        }
    out["ranked_items"] = [
        {
            "title": r.item.title,
            "url": r.item.url,
            "score_total": r.score_total,
            "selected": r.selected,
            "selection_reason": r.selection_reason,
        }
        for r in ctx.ranked_items
    ]
    out["news_items"] = [
        {
            "title": n.title,
            "url": n.url,
            "source": n.source.value,
            "source_id": n.source_id,
        }
        for n in ctx.news_items
    ]
    return out


__all__ = [
    "ChatEvent",
    "ChatService",
    "DeltaEvent",
    "DigestEvent",
    "DoneEvent",
    "ErrorEvent",
    "ProgressEvent",
    "StartedEvent",
]
