"""Session use cases: CRUD, preferences, titles, and delete rules (8A.1 T7)."""

from __future__ import annotations

import uuid
from dataclasses import replace

from ai_news_agent.digest_request_builder import resolve_digest_request
from ai_news_agent.repositories.session_store import SessionStore
from ai_news_agent.repositories.unit_of_work import SqliteUnitOfWork
from ai_news_agent.request import DigestRequest
from ai_news_agent.telemetry import new_correlation_id
from ai_news_agent.services.session_records import (
    MessageRecord,
    SessionRecord,
    SessionRequestRecord,
    initial_session_title,
)


class SessionBusyError(Exception):
    """A session-scoped operation was rejected because a request is active."""


class RequestInProgressError(Exception):
    """The same request ID is already active for this session."""


class _CancelRaceLost(Exception):
    """Internal signal: digest persistence committed before cancellation landed."""


CANCELLED_ASSISTANT_MESSAGE = "The request was cancelled."


class SessionService:
    """Session lifecycle use cases over :class:`SessionStore`."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def create_session(self) -> SessionRecord:
        session_id = str(uuid.uuid4())
        self._store.create_session(session_id)
        record = self._store.get_session(session_id)
        assert record is not None
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self._store.get_session(session_id)

    def list_sessions(self) -> list[SessionRecord]:
        return self._store.list_sessions()

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        return self._store.list_messages(session_id)

    def list_all_messages(self) -> list[MessageRecord]:
        return self._store.list_all_messages()

    def get_request(
        self,
        session_id: str,
        request_id: str,
    ) -> SessionRequestRecord | None:
        return self._store.get_request(session_id, request_id)

    def rename_session(self, session_id: str, title: str) -> None:
        self._store.rename_session(session_id, title)

    def update_preferences(
        self,
        session_id: str,
        *,
        connector_names: list[str] | None,
        items_per_source: int | None,
    ) -> None:
        self._store.update_preferences(
            session_id,
            connector_names=connector_names,
            items_per_source=items_per_source,
        )

    def record_user_message(self, session_id: str, *, content: str) -> MessageRecord:
        self._store.insert_message(session_id, role="user", content=content)
        session = self._store.get_session(session_id)
        if session is not None and session.title is None:
            title = initial_session_title(content)
            if title is not None:
                self._store.rename_session(session_id, title)
        messages = self._store.list_messages(session_id)
        return messages[-1]

    def build_request(
        self,
        session_id: str,
        message: str,
        *,
        juya_item_mode: str | None = None,
    ) -> DigestRequest:
        """Compose a request where session preferences act only as defaults.

        Explicit message selectors win for this one request; the stored
        preference is never mutated.
        """
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"session not found: {session_id}")
        req = resolve_digest_request(
            message,
            session_connector_names=session.connector_names,
        )
        if session.items_per_source is not None:
            value = int(session.items_per_source)
            req = replace(
                req,
                items_per_source=value,
                max_items_per_source=max(req.max_items_per_source, value),
            )
        if juya_item_mode is not None:
            req = replace(req, juya_item_mode=juya_item_mode)
        return req

    def delete_session(self, session_id: str) -> None:
        """Delete an inactive session; reject deletion while a request is active."""
        active = [
            request
            for request in self._store.list_requests(session_id)
            if request.status == "active"
        ]
        if active:
            raise SessionBusyError(f"session {session_id} has an active request")
        self._store.delete_session(session_id)

    def begin_request(
        self,
        session_id: str,
        *,
        content: str,
        request_id: str | None = None,
    ) -> SessionRequestRecord:
        if self._store.get_session(session_id) is None:
            raise KeyError(f"session not found: {session_id}")

        if request_id is not None:
            existing = self._store.get_request(session_id, request_id)
            if existing is not None:
                if existing.status == "active":
                    raise RequestInProgressError(
                        f"request {request_id!r} is already active for session {session_id!r}"
                    )
                return existing

        active_requests = [
            request
            for request in self._store.list_requests(session_id)
            if request.status == "active"
        ]
        if active_requests:
            raise SessionBusyError(f"session {session_id} has an active request")

        resolved_id = request_id if request_id is not None else str(uuid.uuid4())
        message = self.record_user_message(session_id, content=content)
        self._store.create_request(
            session_id,
            resolved_id,
            user_message_id=message.id,
            correlation_id=new_correlation_id(),
        )
        record = self._store.get_request(session_id, resolved_id)
        assert record is not None
        return record

    def interrupt_active_requests(self) -> int:
        """Mark leftover active requests interrupted after startup or crash."""
        return self._store.interrupt_active_requests()

    def cancel_request(self, session_id: str, request_id: str) -> bool:
        request = self._store.get_request(session_id, request_id)
        if (
            request is None
            or request.status != "active"
            or request.run_id is not None
        ):
            return False

        try:
            with SqliteUnitOfWork(self._store.db_path) as uow:
                assistant_message_id = uow.session_store.insert_message(
                    session_id,
                    role="assistant",
                    content=CANCELLED_ASSISTANT_MESSAGE,
                )
                if not uow.session_store.mark_cancelled_if_active(
                    session_id,
                    request_id,
                    assistant_message_id=assistant_message_id,
                ):
                    raise _CancelRaceLost
        except _CancelRaceLost:
            return False
        return True

    def complete_request(
        self,
        session_id: str,
        request_id: str,
        *,
        status: str,
        content: str,
        run_id: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> int:
        request = self._store.get_request(session_id, request_id)
        if request is None or request.status != "active":
            raise KeyError(
                f"active request not found: session={session_id!r} request={request_id!r}"
            )

        with SqliteUnitOfWork(self._store.db_path) as uow:
            assistant_message_id = uow.session_store.insert_message(
                session_id,
                role="assistant",
                content=content,
                run_id=run_id,
            )
            if not uow.session_store.mark_terminal_if_active(
                session_id,
                request_id,
                status=status,
                assistant_message_id=assistant_message_id,
                error_code=error_code,
                error_message=error_message,
            ):
                raise KeyError(
                    f"active request not found: session={session_id!r} request={request_id!r}"
                )
            if run_id is not None:
                uow.session_store.update_request_run_id(
                    session_id,
                    request_id,
                    run_id,
                )
        return assistant_message_id


__all__ = [
    "CANCELLED_ASSISTANT_MESSAGE",
    "RequestInProgressError",
    "SessionBusyError",
    "SessionService",
]
