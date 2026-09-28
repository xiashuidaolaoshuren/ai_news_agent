"""Session use cases: CRUD, preferences, titles, and delete rules (8A.1 T7)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import replace
from datetime import datetime

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


CANCELLED_ASSISTANT_MESSAGE = "The request was cancelled."


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _session_record(row: sqlite3.Row) -> SessionRecord:
    raw_names = row["connector_names"]
    return SessionRecord(
        id=row["id"],
        title=row["title"],
        connector_names=json.loads(raw_names) if raw_names is not None else None,
        items_per_source=row["items_per_source"],
        created_at=_parse_ts(row["created_at"]),
        updated_at=_parse_ts(row["updated_at"]),
    )


def _message_record(row: sqlite3.Row) -> MessageRecord:
    return MessageRecord(
        id=int(row["id"]),
        session_id=row["session_id"],
        sequence=int(row["sequence"]),
        role=row["role"],
        content=row["content"],
        run_id=row["run_id"],
        created_at=_parse_ts(row["created_at"]),
    )


def _request_record(row: sqlite3.Row) -> SessionRequestRecord:
    completed_at = row["completed_at"]
    return SessionRequestRecord(
        id=row["id"],
        session_id=row["session_id"],
        status=row["status"],
        user_message_id=int(row["user_message_id"]),
        assistant_message_id=row["assistant_message_id"],
        run_id=row["run_id"],
        correlation_id=row["correlation_id"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        started_at=_parse_ts(row["started_at"]),
        completed_at=_parse_ts(completed_at) if completed_at is not None else None,
    )


class SessionService:
    """Session lifecycle use cases over :class:`SessionStore`."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def create_session(self) -> SessionRecord:
        session_id = str(uuid.uuid4())
        self._store.create_session(session_id)
        row = self._store.get_session(session_id)
        assert row is not None
        return _session_record(row)

    def get_session(self, session_id: str) -> SessionRecord | None:
        row = self._store.get_session(session_id)
        return _session_record(row) if row is not None else None

    def list_sessions(self) -> list[SessionRecord]:
        return [_session_record(row) for row in self._store.list_sessions()]

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        return [_message_record(row) for row in self._store.list_messages(session_id)]

    def list_all_messages(self) -> list[MessageRecord]:
        return [_message_record(row) for row in self._store.list_all_messages()]

    def get_request(
        self,
        session_id: str,
        request_id: str,
    ) -> SessionRequestRecord | None:
        row = self._store.get_request(session_id, request_id)
        return _request_record(row) if row is not None else None

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
        row = self._store.get_session(session_id)
        if row is not None and row["title"] is None:
            title = initial_session_title(content)
            if title is not None:
                self._store.rename_session(session_id, title)
        messages = self._store.list_messages(session_id)
        return _message_record(messages[-1])

    def build_request(self, session_id: str, message: str) -> DigestRequest:
        """Compose a request where session preferences act only as defaults.

        Explicit message selectors win for this one request; the stored
        preference is never mutated.
        """
        row = self._store.get_session(session_id)
        if row is None:
            raise KeyError(f"session not found: {session_id}")
        raw_names = row["connector_names"]
        stored_names = json.loads(raw_names) if raw_names is not None else None
        req = resolve_digest_request(message, session_connector_names=stored_names)
        items_per_source = row["items_per_source"]
        if items_per_source is not None:
            req = replace(req, max_items_per_source=int(items_per_source))
        return req

    def delete_session(self, session_id: str) -> None:
        """Delete an inactive session; reject deletion while a request is active."""
        active = [
            row
            for row in self._store.list_requests(session_id)
            if row["status"] == "active"
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
                if existing["status"] == "active":
                    raise RequestInProgressError(
                        f"request {request_id!r} is already active for session {session_id!r}"
                    )
                return _request_record(existing)

        active_requests = [
            row
            for row in self._store.list_requests(session_id)
            if row["status"] == "active"
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
        row = self._store.get_request(session_id, resolved_id)
        assert row is not None
        return _request_record(row)

    def interrupt_active_requests(self) -> int:
        """Mark leftover active requests interrupted after startup or crash."""
        return self._store.interrupt_active_requests()

    def cancel_request(self, session_id: str, request_id: str) -> bool:
        row = self._store.get_request(session_id, request_id)
        if row is None or row["status"] != "active" or row["run_id"] is not None:
            return False

        with SqliteUnitOfWork(self._store.db_path) as uow:
            assistant_message_id = uow.session_store.insert_message(
                session_id,
                role="assistant",
                content=CANCELLED_ASSISTANT_MESSAGE,
            )
            uow.session_store.mark_terminal(
                session_id,
                request_id,
                status="cancelled",
                assistant_message_id=assistant_message_id,
                error_code="cancelled",
            )
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
        row = self._store.get_request(session_id, request_id)
        if row is None or row["status"] != "active":
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
            uow.session_store.mark_terminal(
                session_id,
                request_id,
                status=status,
                assistant_message_id=assistant_message_id,
                error_code=error_code,
                error_message=error_message,
            )
        return assistant_message_id


__all__ = [
    "CANCELLED_ASSISTANT_MESSAGE",
    "RequestInProgressError",
    "SessionBusyError",
    "SessionService",
]