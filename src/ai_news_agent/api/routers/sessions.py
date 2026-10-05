"""Session CRUD, transcript pages, and message SSE (Milestone 8A.1 T14)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse

from ai_news_agent.api.deps import get_application
from ai_news_agent.api.schemas.digests import build_digest_view
from ai_news_agent.api.schemas.sessions import (
    MessageListPage,
    MessageOut,
    PostMessageBody,
    RequestOut,
    SessionListPage,
    SessionOut,
    SessionPatch,
    SessionSearchHitOut,
    SessionSearchPageOut,
)
from ai_news_agent.api.schemas.streaming import (
    DeltaPayload,
    DigestPayload,
    DonePayload,
    ErrorPayload,
    ProgressPayload,
    StartedPayload,
    WorkflowErrorPayload,
    session_message_stream_openapi_schema,
)
from ai_news_agent.api.sse import encode_sse
from ai_news_agent.services.chat import (
    ChatEvent,
    DeltaEvent,
    DigestEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    StartedEvent,
)
from ai_news_agent.services.composition import Application
from ai_news_agent.services.session_search import SessionSearchHit, search_sessions
from ai_news_agent.services.session_records import (
    MessageRecord,
    SessionRecord,
    SessionRequestRecord,
)
from ai_news_agent.services.session_service import (
    RequestInProgressError,
    SessionBusyError,
)
from ai_news_agent.sources import ALLOWED_SOURCES
from ai_news_agent.storage import DigestStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

_STREAM_SENTINEL = object()
_DEFAULT_PAGE_LIMIT = 20
_MAX_PAGE_LIMIT = 100


def _session_out(record: SessionRecord) -> SessionOut:
    return SessionOut(
        id=record.id,
        title=record.title,
        connector_names=record.connector_names,
        items_per_source=record.items_per_source,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _search_hit_out(hit: SessionSearchHit) -> SessionSearchHitOut:
    return SessionSearchHitOut(
        session_id=hit.session_id,
        title=hit.title,
        updated_at=hit.updated_at,
        match_kind=hit.match_kind,
        message_id=hit.message_id,
        excerpt=hit.excerpt,
    )


def _request_out(record: SessionRequestRecord) -> RequestOut:
    return RequestOut(
        id=record.id,
        session_id=record.session_id,
        status=record.status,
        user_message_id=record.user_message_id,
        assistant_message_id=record.assistant_message_id,
        run_id=record.run_id,
        error_code=record.error_code,
        error_message=record.error_message,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


def _session_sort_key(record: SessionRecord) -> tuple[float, tuple[int, ...]]:
    return (-record.updated_at.timestamp(), tuple(-ord(char) for char in record.id))


def _encode_session_cursor(record: SessionRecord) -> str:
    payload = {
        "u": record.updated_at.isoformat(),
        "s": record.id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_session_cursor(cursor: str) -> tuple[float, tuple[int, ...]]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
        updated_at = payload["u"]
        session_id = payload["s"]
        ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00")).timestamp()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid cursor") from exc
    return (-ts, tuple(-ord(char) for char in str(session_id)))


def _encode_message_cursor(sequence: int) -> str:
    payload = {"q": sequence}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_message_cursor(cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
        return int(payload["q"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid cursor") from exc


def _chat_event_payload(event: ChatEvent, digest_store: DigestStore) -> tuple[str, dict[str, Any]]:
    if isinstance(event, StartedEvent):
        return "started", StartedPayload(
            request_id=event.request_id,
            user_message_id=event.user_message_id,
        ).model_dump(mode="json")
    if isinstance(event, ProgressEvent):
        return "progress", ProgressPayload(stage=event.stage).model_dump(mode="json")
    if isinstance(event, DeltaEvent):
        return "delta", DeltaPayload(text=event.text).model_dump(mode="json")
    if isinstance(event, DigestEvent):
        digest_view = build_digest_view(
            event.digest,
            news_items=digest_store.get_news_items_for_run(event.run_id),
        )
        return "digest", DigestPayload(
            run_id=event.run_id,
            digest=digest_view,
            markdown=event.markdown,
            warnings=event.warnings,
            errors=[
                WorkflowErrorPayload(
                    stage=error.stage,
                    message=error.message,
                )
                for error in event.errors
            ],
        ).model_dump(mode="json")
    if isinstance(event, DoneEvent):
        return "done", DonePayload(
            request_id=event.request_id,
            message_id=event.message_id,
            run_id=event.run_id,
            path=event.path,
        ).model_dump(mode="json")
    if isinstance(event, ErrorEvent):
        return "error", ErrorPayload(
            request_id=event.request_id,
            code=event.code,
            message=event.message,
            correlation_id=event.correlation_id,
        ).model_dump(mode="json")
    raise TypeError(f"unsupported chat event: {type(event)!r}")


async def _pump_events(source: AsyncIterator[ChatEvent], queue: asyncio.Queue[Any]) -> None:
    try:
        async for event in source:
            await queue.put(event)
    except Exception:
        logger.exception("SSE event pump failed")
        raise
    finally:
        await queue.put(_STREAM_SENTINEL)


async def shielded_event_stream(
    source: AsyncIterator[ChatEvent],
) -> AsyncIterator[ChatEvent]:
    """Yield events from *source* while a background pump survives consumer cancel."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    pump_task = asyncio.create_task(_pump_events(source, queue))

    def _log_pump_failure(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Detached SSE pump failed")

    pump_task.add_done_callback(_log_pump_failure)

    try:
        while True:
            item = await queue.get()
            if item is _STREAM_SENTINEL:
                break
            yield item
    finally:
        if not pump_task.done():
            return
        await pump_task


def _message_out(message: MessageRecord, digest_store: DigestStore) -> MessageOut:
    digest = None
    if message.role == "assistant" and message.run_id is not None:
        stored = digest_store.get_digest_by_run_id(message.run_id)
        if stored is not None:
            digest = build_digest_view(
                stored,
                news_items=digest_store.get_news_items_for_run(message.run_id),
            )
    return MessageOut(
        id=message.id,
        session_id=message.session_id,
        sequence=message.sequence,
        role=message.role,
        content=message.content,
        run_id=message.run_id,
        created_at=message.created_at,
        digest=digest,
    )


def _page_messages(
    messages: list[MessageRecord],
    *,
    limit: int,
    cursor: str | None,
    digest_store: DigestStore,
) -> MessageListPage:
    ordered = sorted(messages, key=lambda message: message.sequence, reverse=True)
    if cursor is not None:
        cursor_sequence = _decode_message_cursor(cursor)
        ordered = [message for message in ordered if message.sequence < cursor_sequence]
    page_desc = ordered[:limit]
    page = list(reversed(page_desc))
    next_cursor = (
        _encode_message_cursor(page_desc[-1].sequence)
        if len(ordered) > len(page_desc)
        else None
    )
    return MessageListPage(
        messages=[_message_out(message, digest_store) for message in page],
        next_cursor=next_cursor,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def create_session(application: Application = Depends(get_application)) -> SessionOut:
    record = application.session_service.create_session()
    return _session_out(record)


@router.get("", response_model=SessionListPage)
def list_sessions(
    limit: int = Query(default=_DEFAULT_PAGE_LIMIT, ge=1, le=_MAX_PAGE_LIMIT),
    cursor: str | None = Query(default=None),
    application: Application = Depends(get_application),
) -> SessionListPage:
    sessions = application.session_service.list_sessions()
    sessions.sort(key=_session_sort_key)
    if cursor is not None:
        cursor_key = _decode_session_cursor(cursor)
        sessions = [session for session in sessions if _session_sort_key(session) > cursor_key]
    page = sessions[:limit]
    next_cursor = (
        _encode_session_cursor(page[-1]) if len(sessions) > len(page) else None
    )
    return SessionListPage(
        sessions=[_session_out(record) for record in page],
        next_cursor=next_cursor,
    )


@router.get("/search", response_model=SessionSearchPageOut)
def search(
    q: str = Query(...),
    limit: int = Query(default=_DEFAULT_PAGE_LIMIT, ge=1, le=_MAX_PAGE_LIMIT),
    cursor: str | None = Query(default=None),
    application: Application = Depends(get_application),
) -> SessionSearchPageOut:
    try:
        page = search_sessions(
            application.session_service.list_sessions(),
            application.session_service.list_all_messages(),
            q,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SessionSearchPageOut(
        hits=[_search_hit_out(hit) for hit in page.hits],
        next_cursor=page.next_cursor,
    )


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: str,
    application: Application = Depends(get_application),
) -> SessionOut:
    record = application.session_service.get_session(session_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    return _session_out(record)


@router.patch("/{session_id}", response_model=SessionOut)
def patch_session(
    session_id: str,
    body: SessionPatch,
    application: Application = Depends(get_application),
) -> SessionOut:
    if application.session_service.get_session(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")

    if body.connector_names is not None:
        if not body.connector_names:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="connector_names must be non-empty when provided",
            )
        invalid = [name for name in body.connector_names if name not in ALLOWED_SOURCES]
        if invalid:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"invalid source: {invalid[0]}",
            )

    if body.items_per_source is not None and not 1 <= body.items_per_source <= 20:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="items_per_source must be between 1 and 20",
        )

    if body.title is not None:
        application.session_service.rename_session(session_id, body.title)
    if body.connector_names is not None or body.items_per_source is not None:
        current = application.session_service.get_session(session_id)
        assert current is not None
        application.session_service.update_preferences(
            session_id,
            connector_names=(
                body.connector_names
                if body.connector_names is not None
                else current.connector_names
            ),
            items_per_source=(
                body.items_per_source
                if body.items_per_source is not None
                else current.items_per_source
            ),
        )

    record = application.session_service.get_session(session_id)
    assert record is not None
    return _session_out(record)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    application: Application = Depends(get_application),
) -> None:
    if application.session_service.get_session(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    try:
        application.session_service.delete_session(session_id)
    except SessionBusyError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "session_busy"},
        ) from exc


@router.get(
    "/{session_id}/requests/{request_id}",
    response_model=RequestOut,
)
def get_request_status(
    session_id: str,
    request_id: str,
    application: Application = Depends(get_application),
) -> RequestOut:
    if application.session_service.get_session(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    record = application.session_service.get_request(session_id, request_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="request not found")
    return _request_out(record)


@router.post(
    "/{session_id}/requests/{request_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
)
def cancel_request(
    session_id: str,
    request_id: str,
    application: Application = Depends(get_application),
) -> Response:
    if application.session_service.get_session(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    accepted = application.session_service.cancel_request(session_id, request_id)
    if accepted:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{session_id}/messages", response_model=MessageListPage)
def list_messages(
    session_id: str,
    limit: int = Query(default=_DEFAULT_PAGE_LIMIT, ge=1, le=_MAX_PAGE_LIMIT),
    cursor: str | None = Query(default=None),
    application: Application = Depends(get_application),
) -> MessageListPage:
    if application.session_service.get_session(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")

    messages = application.session_service.list_messages(session_id)
    return _page_messages(
        messages,
        limit=limit,
        cursor=cursor,
        digest_store=application.digest_store,
    )


@router.post(
    "/{session_id}/messages",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Session chat event stream",
            "content": {
                "text/event-stream": {
                    "schema": session_message_stream_openapi_schema(),
                },
            },
        },
    },
)
async def post_message(
    session_id: str,
    body: PostMessageBody,
    application: Application = Depends(get_application),
) -> StreamingResponse:
    if not body.content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="content must not be blank")

    if application.session_service.get_session(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")

    stream = application.chat_service.stream_events(
        body.content,
        session_id=session_id,
        request_id=body.client_request_id,
        juya_item_mode=body.juya_item_mode,
    )

    try:
        first_event = await anext(stream)
    except StopAsyncIteration as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="stream ended before first event",
        ) from exc
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found") from exc
    except SessionBusyError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "session_busy"},
        ) from exc
    except RequestInProgressError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "request_in_progress"},
        ) from exc

    async def all_events() -> AsyncIterator[ChatEvent]:
        yield first_event
        async for event in stream:
            yield event

    async def sse_body() -> AsyncIterator[str]:
        async for event in shielded_event_stream(all_events()):
            event_name, payload = _chat_event_payload(event, application.digest_store)
            yield encode_sse(event_name, payload)

    return StreamingResponse(sse_body(), media_type="text/event-stream")
