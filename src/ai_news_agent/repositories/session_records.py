"""Typed session repository records (Milestone 8A.1 T3/T4)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SessionRecord:
    """Typed view of a persisted chat session."""

    id: str
    title: str | None
    connector_names: list[str] | None
    items_per_source: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageRecord:
    """Typed view of an ordered session message."""

    id: int
    session_id: str
    sequence: int
    role: str
    content: str
    run_id: int | None
    created_at: datetime


@dataclass(frozen=True)
class SessionRequestRecord:
    """Typed view of a durable session request."""

    id: str
    session_id: str
    status: str
    user_message_id: int
    assistant_message_id: int | None
    run_id: int | None
    correlation_id: str
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def session_record_from_row(row: sqlite3.Row) -> SessionRecord:
    raw_names = row["connector_names"]
    return SessionRecord(
        id=row["id"],
        title=row["title"],
        connector_names=json.loads(raw_names) if raw_names is not None else None,
        items_per_source=row["items_per_source"],
        created_at=_parse_ts(row["created_at"]),
        updated_at=_parse_ts(row["updated_at"]),
    )


def message_record_from_row(row: sqlite3.Row) -> MessageRecord:
    return MessageRecord(
        id=int(row["id"]),
        session_id=row["session_id"],
        sequence=int(row["sequence"]),
        role=row["role"],
        content=row["content"],
        run_id=row["run_id"],
        created_at=_parse_ts(row["created_at"]),
    )


def request_record_from_row(row: sqlite3.Row) -> SessionRequestRecord:
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


@dataclass(frozen=True)
class SessionRequestStats:
    """Per-session digest count and in-flight request id."""

    digest_count: int
    active_request_id: str | None


__all__ = [
    "MessageRecord",
    "SessionRecord",
    "SessionRequestRecord",
    "SessionRequestStats",
    "message_record_from_row",
    "request_record_from_row",
    "session_record_from_row",
]
