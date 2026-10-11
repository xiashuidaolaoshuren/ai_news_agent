"""Session record re-exports and title rules (Milestone 8A.1 T7)."""

from __future__ import annotations

from ai_news_agent.repositories.session_records import (
    MessageRecord,
    SessionRecord,
    SessionRequestRecord,
    SessionRequestStats,
)

_TITLE_MAX_CHARS = 60


def initial_session_title(content: str) -> str | None:
    """Derive the one-time initial session title from a user message.

    Uses the first nonblank line, collapses whitespace runs to single spaces,
    and truncates to 60 Unicode characters. Blank content yields ``None`` so
    the title stays NULL ("New conversation" is display-only).
    """
    for line in content.splitlines():
        normalized = " ".join(line.split())
        if normalized:
            return normalized[:_TITLE_MAX_CHARS]
    return None


__all__ = [
    "MessageRecord",
    "SessionRecord",
    "SessionRequestRecord",
    "SessionRequestStats",
    "initial_session_title",
]
