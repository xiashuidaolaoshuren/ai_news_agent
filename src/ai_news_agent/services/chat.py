"""Follow-up chat service and typed session event stream (8A.1 T10)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

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
from ai_news_agent.services.conversation import (
    ConversationContext,
    ConversationDecision,
    interpret_message,
    request_metadata,
    request_payload,
)
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

_TERMINAL_REPLAY_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)
_WORKFLOW_ERROR_CODE = "workflow_error"
_WORKFLOW_ERROR_MESSAGE = "Digest generation failed."
_REQUEST_FAILED_CODE = "request_failed"
_REQUEST_FAILED_MESSAGE = "Request failed."
_CLARIFY_FALLBACK = (
    "Tell me whether you want recent signals on that topic or a general explanation."
)
_GENERAL_FALLBACK = (
    "I can answer general questions once a language model is configured. "
    "For collected signals, ask for a digest, for example: “Give me today's AI digest”."
)


def _interpretation_payload(decision: ConversationDecision) -> dict[str, Any]:
    payload: dict[str, Any] = {"intent": decision.intent}
    if decision.intent == "digest" and decision.request is not None:
        payload["request"] = request_payload(decision.request)
        payload["public"] = request_metadata(decision.request)
    if decision.intent == "clarify" and decision.pending:
        payload["pending"] = decision.pending
    return payload


def _apply_session_defaults(
    request: DigestRequest,
    *,
    session: Any | None,
    juya_item_mode: str | None,
) -> DigestRequest:
    updates: dict[str, Any] = {}
    if request.items_per_source is None and session is not None:
        stored_count = getattr(session, "items_per_source", None)
        if stored_count is not None:
            updates["items_per_source"] = int(stored_count)
    sources = list(request.connector_names or [])
    if request.juya_item_mode is None:
        if juya_item_mode is not None:
            updates["juya_item_mode"] = juya_item_mode
        if "juya" in sources and request.topics_are_filters:
            updates["juya_item_mode"] = "stories"
    if "items_per_source" in updates:
        updates["max_items_per_source"] = max(
            request.max_items_per_source, int(updates["items_per_source"])
        )
    return replace(request, **updates) if updates else request


@dataclass(frozen=True)
class StartedEvent:
    request_id: str
    user_message_id: int
    #: Public resolved-request metadata when this message starts a digest.
    request: dict[str, Any] | None = None
    #: The interpreted intent: digest, followup, general, or clarify.
    intent: str | None = None


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
        conversation_model: Any | None = None,
    ) -> None:
        self._store = store
        self._workflow_runner = workflow_runner
        self._streaming_workflow_runner = streaming_workflow_runner
        self._chat_model = chat_model
        self._tool_agent_runner = tool_agent_runner
        self._interface_router = interface_router
        self._session_service = session_service
        self._conversation_model = conversation_model

    async def stream_events(
        self,
        message: str,
        *,
        session_id: str,
        request_id: str | None = None,
        juya_item_mode: str | None = None,
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

        history_cmd = parse_history_chat_message(message)
        try:
            if history_cmd is not None:
                yield StartedEvent(
                    request_id=record.id,
                    user_message_id=record.user_message_id,
                )
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

            decision = await self._resolve_conversation_decision(session_id, message)
            request = decision.request
            if decision.intent == "digest" and request is not None:
                request = _apply_session_defaults(
                    request,
                    session=self._session_service.get_session(session_id),
                    juya_item_mode=juya_item_mode,
                )
                decision = replace(decision, request=request)
            interpretation = _interpretation_payload(decision)
            self._session_service.set_request_interpretation(
                session_id,
                record.id,
                interpretation,
            )
            yield StartedEvent(
                request_id=record.id,
                user_message_id=record.user_message_id,
                request=interpretation.get("public") or None,
                intent=decision.intent,
            )

            if decision.intent == "digest" and request is not None:
                async for event in self._stream_session_digest_events(
                    session_id=session_id,
                    record=record,
                    request=request,
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

            if decision.intent == "general":
                text = await self._answer_general_question(
                    decision.question or message
                )
                async for event in self._stream_session_text_events(
                    session_id=session_id,
                    record=record,
                    text=text,
                    path="general",
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

            if decision.intent == "clarify":
                async for event in self._stream_session_text_events(
                    session_id=session_id,
                    record=record,
                    text=decision.clarification or _CLARIFY_FALLBACK,
                    path="clarify",
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

    async def _resolve_conversation_decision(
        self,
        session_id: str,
        message: str,
    ) -> ConversationDecision:
        assert self._session_service is not None
        ctx = self._store.get_followup_context_for_session(session_id)
        session = self._session_service.get_session(session_id)
        context = ConversationContext(
            has_digest=ctx.run_id is not None or ctx.digest is not None,
            pending=self._session_service.pending_clarification(session_id),
            last_request=self._session_service.last_digest_request(session_id),
            connector_names=session.connector_names if session is not None else None,
        )
        return await asyncio.to_thread(
            interpret_message,
            message,
            context=context,
            model=self._conversation_model,
        )

    async def _answer_general_question(self, question: str) -> str:
        answer = getattr(self._conversation_model, "generate_general_answer", None)
        if answer is not None and callable(answer):
            try:
                return str(await asyncio.to_thread(answer, question=question))
            except Exception:  # noqa: BLE001 - a model failure gets guidance
                logger.exception("general answer failed")
        return _GENERAL_FALLBACK

    async def _stream_session_digest_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        request: DigestRequest,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        req = request
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
            markdown = _user_facing_digest_markdown(result)
            async for chunk in iter_text_chunks(
                markdown,
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
                    markdown=markdown,
                    warnings=result.warnings,
                    errors=result.errors,
                )
            try:
                message_id = self._session_service.complete_request(
                    session_id,
                    record.id,
                    status="succeeded",
                    content=markdown,
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
            request=(record.interpretation or {}).get("public") or None,
            intent=(record.interpretation or {}).get("intent"),
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




def _user_facing_digest_markdown(result: DigestResult) -> str:
    notice = format_connector_warnings_notice(result.warnings, result.errors)
    if not notice:
        return result.markdown
    if notice in result.markdown:
        return result.markdown
    return f"{notice}\n\n{result.markdown}"




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
