"""Lexical session search scoring and cursor pagination (Milestone 8A.1 T12)."""

from __future__ import annotations

import base64
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from ai_news_agent.services.session_records import MessageRecord, SessionRecord

MatchKind = Literal["title", "user", "assistant"]

_TIER: dict[MatchKind, int] = {"title": 0, "user": 1, "assistant": 2}
_EXCERPT_MAX_LEN = 160


@dataclass(frozen=True)
class SessionSearchHit:
    """One ranked session search hit."""

    session_id: str
    title: str | None
    updated_at: datetime
    match_kind: MatchKind
    message_id: int | None
    excerpt: str


@dataclass(frozen=True)
class SessionSearchPage:
    """Cursor-paginated session search results."""

    hits: list[SessionSearchHit]
    next_cursor: str | None


def search_sessions(
    sessions: list[SessionRecord],
    messages: list[MessageRecord],
    query: str,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> SessionSearchPage:
    """Search session titles and message text; one hit per session."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if cursor is not None:
        cursor_key = _decode_cursor(cursor)
    else:
        cursor_key = None
    if not query.strip():
        return SessionSearchPage(hits=[], next_cursor=None)

    phrase, terms = _query_match_terms(query)
    sessions_by_id = {session.id: session for session in sessions}
    messages_by_session: dict[str, list[MessageRecord]] = {}
    for message in messages:
        messages_by_session.setdefault(message.session_id, []).append(message)
    for session_messages in messages_by_session.values():
        session_messages.sort(key=lambda message: message.sequence)

    hits: list[SessionSearchHit] = []
    for session in sessions:
        hit = _best_session_hit(
            session,
            messages_by_session.get(session.id, []),
            phrase=phrase,
            terms=terms,
        )
        if hit is not None:
            hits.append(hit)

    hits.sort(key=_hit_sort_key)
    if cursor_key is not None:
        hits = [hit for hit in hits if _hit_sort_key(hit) > cursor_key]
    page_hits = hits[:limit]
    next_cursor = (
        _encode_cursor(page_hits[-1]) if len(hits) > len(page_hits) else None
    )
    return SessionSearchPage(hits=page_hits, next_cursor=next_cursor)


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _query_match_terms(query_text: str) -> tuple[str, list[str]]:
    stripped = query_text.strip()
    phrase = _normalize_text(stripped)
    if any(ch.isspace() for ch in stripped):
        terms = [_normalize_text(part) for part in stripped.split()]
        return phrase, terms
    return phrase, [phrase]


def _field_contains_match(field: str, phrase: str, terms: list[str]) -> bool:
    normalized = _normalize_text(field)
    if phrase and phrase in normalized:
        return True
    return any(term in normalized for term in terms)


def _best_session_hit(
    session: SessionRecord,
    session_messages: list[MessageRecord],
    *,
    phrase: str,
    terms: list[str],
) -> SessionSearchHit | None:
    if session.title and _field_contains_match(session.title, phrase, terms):
        excerpt = _extract_excerpt(session.title, phrase=phrase, terms=terms)
        return SessionSearchHit(
            session_id=session.id,
            title=session.title,
            updated_at=session.updated_at,
            match_kind="title",
            message_id=None,
            excerpt=excerpt or session.title[:_EXCERPT_MAX_LEN],
        )

    for message in session_messages:
        if message.role == "user" and _field_contains_match(message.content, phrase, terms):
            excerpt = _extract_excerpt(message.content, phrase=phrase, terms=terms)
            return SessionSearchHit(
                session_id=session.id,
                title=session.title,
                updated_at=session.updated_at,
                match_kind="user",
                message_id=message.id,
                excerpt=excerpt or message.content[:_EXCERPT_MAX_LEN],
            )

    for message in session_messages:
        if message.role == "assistant" and _field_contains_match(
            message.content, phrase, terms
        ):
            excerpt = _extract_excerpt(message.content, phrase=phrase, terms=terms)
            return SessionSearchHit(
                session_id=session.id,
                title=session.title,
                updated_at=session.updated_at,
                match_kind="assistant",
                message_id=message.id,
                excerpt=excerpt or message.content[:_EXCERPT_MAX_LEN],
            )

    return None


def _extract_excerpt(field: str, *, phrase: str, terms: list[str]) -> str | None:
    field_nfc = unicodedata.normalize("NFC", field)
    normalized = _normalize_text(field_nfc)
    match_start = -1
    if phrase and phrase in normalized:
        match_start = normalized.index(phrase)
    else:
        for term in terms:
            if term in normalized:
                match_start = normalized.index(term)
                break
    if match_start < 0:
        return None
    if len(field_nfc) <= _EXCERPT_MAX_LEN:
        return field_nfc
    end = min(len(field_nfc), match_start + _EXCERPT_MAX_LEN)
    return field_nfc[match_start:end]


def _hit_sort_key(hit: SessionSearchHit) -> tuple[int, float, tuple[int, ...]]:
    ts = hit.updated_at.timestamp()
    return (_TIER[hit.match_kind], -ts, tuple(-ord(char) for char in hit.session_id))


def _encode_cursor(hit: SessionSearchHit) -> str:
    payload = {
        "t": _TIER[hit.match_kind],
        "u": hit.updated_at.isoformat(),
        "s": hit.session_id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[int, float, tuple[int, ...]]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
        tier = int(payload["t"])
        updated_at = datetime.fromisoformat(str(payload["u"]).replace("Z", "+00:00"))
        session_id = str(payload["s"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cursor") from exc
    return (tier, -updated_at.timestamp(), tuple(-ord(char) for char in session_id))
