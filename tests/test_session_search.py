"""Tests for lexical session search (Milestone 8A.1 T12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_news_agent.services.session_records import MessageRecord, SessionRecord


def _dt(*, day: int = 1, hour: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, 0, tzinfo=UTC)


def _session(
    session_id: str,
    *,
    title: str | None = None,
    updated_at: datetime | None = None,
) -> SessionRecord:
    created = _dt()
    updated = updated_at or created
    return SessionRecord(
        id=session_id,
        title=title,
        connector_names=None,
        items_per_source=None,
        created_at=created,
        updated_at=updated,
    )


def _message(
    message_id: int,
    session_id: str,
    *,
    role: str,
    content: str,
    sequence: int,
) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        session_id=session_id,
        sequence=sequence,
        role=role,
        content=content,
        run_id=None,
        created_at=_dt(),
    )


def test_session_search_surface_importable() -> None:
    from ai_news_agent.services.session_search import (
        SessionSearchHit,
        SessionSearchPage,
        search_sessions,
    )

    assert SessionSearchHit is not None
    assert SessionSearchPage is not None
    assert callable(search_sessions)


def test_search_sessions_ranks_one_hit_per_session_by_match_tier() -> None:
    from ai_news_agent.services.session_search import search_sessions

    sessions = [
        _session("sess-user", title="Other", updated_at=_dt(day=2)),
        _session("sess-title", title="Weekly digest", updated_at=_dt(day=1)),
        _session("sess-both", title="Weekly digest notes", updated_at=_dt(day=3)),
        _session("sess-asst", title="Chat", updated_at=_dt(day=4)),
        _session("sess-newer", title="Notes", updated_at=_dt(day=5)),
        _session("sess-older", title="Notes", updated_at=_dt(day=4, hour=12)),
    ]
    messages = [
        _message(1, "sess-user", role="user", content="Weekly digest please", sequence=1),
        _message(
            2,
            "sess-both",
            role="user",
            content="Weekly digest follow-up",
            sequence=1,
        ),
        _message(
            3,
            "sess-asst",
            role="assistant",
            content="Here is your Weekly digest",
            sequence=1,
        ),
        _message(4, "sess-newer", role="user", content="Weekly digest", sequence=1),
        _message(5, "sess-older", role="user", content="Weekly digest", sequence=1),
    ]

    page = search_sessions(sessions, messages, "Weekly digest", limit=20)

    assert len(page.hits) == 6
    assert [hit.session_id for hit in page.hits] == [
        "sess-both",
        "sess-title",
        "sess-newer",
        "sess-older",
        "sess-user",
        "sess-asst",
    ]
    both_hit = next(hit for hit in page.hits if hit.session_id == "sess-both")
    assert both_hit.match_kind == "title"
    assert page.hits.index(both_hit) < page.hits.index(
        next(hit for hit in page.hits if hit.session_id == "sess-user")
    )
    assert page.hits.index(
        next(hit for hit in page.hits if hit.session_id == "sess-user")
    ) < page.hits.index(
        next(hit for hit in page.hits if hit.session_id == "sess-asst")
    )
    newer = next(hit for hit in page.hits if hit.session_id == "sess-newer")
    older = next(hit for hit in page.hits if hit.session_id == "sess-older")
    assert page.hits.index(newer) < page.hits.index(older)


def test_search_sessions_includes_message_id_and_bounded_excerpt() -> None:
    from ai_news_agent.services.session_search import search_sessions

    prefix = "x" * 120
    match_text = "needle"
    suffix = "y" * 120
    long_content = f"{prefix}{match_text}{suffix}"
    sessions = [
        _session("sess-title", title=f"{prefix}{match_text}{suffix}"),
        _session("sess-msg", title="Chat"),
    ]
    messages = [
        _message(42, "sess-msg", role="user", content=long_content, sequence=1),
    ]

    page = search_sessions(sessions, messages, match_text, limit=20)

    title_hit = next(hit for hit in page.hits if hit.session_id == "sess-title")
    msg_hit = next(hit for hit in page.hits if hit.session_id == "sess-msg")

    assert title_hit.match_kind == "title"
    assert title_hit.message_id is None
    assert len(title_hit.excerpt) <= 160
    assert title_hit.excerpt.startswith(match_text)

    assert msg_hit.match_kind == "user"
    assert msg_hit.message_id == 42
    assert len(msg_hit.excerpt) <= 160
    assert msg_hit.excerpt.startswith(match_text)
    assert msg_hit.excerpt.endswith(suffix[: 160 - len(match_text)])


def test_search_sessions_supports_cursor_pagination() -> None:
    from ai_news_agent.services.session_search import search_sessions

    sessions = [
        _session("sess-a", title="Alpha digest", updated_at=_dt(day=3)),
        _session("sess-b", title="Beta digest", updated_at=_dt(day=2)),
        _session("sess-c", title="Gamma digest", updated_at=_dt(day=1)),
    ]

    first = search_sessions(sessions, [], "digest", limit=1)
    assert [hit.session_id for hit in first.hits] == ["sess-a"]
    assert first.next_cursor is not None

    second = search_sessions(
        sessions,
        [],
        "digest",
        limit=1,
        cursor=first.next_cursor,
    )
    assert [hit.session_id for hit in second.hits] == ["sess-b"]
    assert second.next_cursor is not None

    third = search_sessions(
        sessions,
        [],
        "digest",
        limit=1,
        cursor=second.next_cursor,
    )
    assert [hit.session_id for hit in third.hits] == ["sess-c"]
    assert third.next_cursor is None


def test_search_sessions_rejects_invalid_limit_and_cursor() -> None:
    import pytest

    from ai_news_agent.services.session_search import search_sessions

    sessions = [_session("sess-a", title="Alpha digest")]

    with pytest.raises(ValueError, match="limit"):
        search_sessions(sessions, [], "digest", limit=0)

    with pytest.raises(ValueError, match="cursor"):
        search_sessions(sessions, [], "digest", cursor="not-a-cursor")


def test_search_sessions_blank_query_returns_empty_page() -> None:
    from ai_news_agent.services.session_search import search_sessions

    sessions = [_session("sess-a", title="Weekly digest")]
    messages = [
        _message(1, "sess-a", role="user", content="Weekly digest please", sequence=1),
    ]

    for query in ("", "   "):
        page = search_sessions(sessions, messages, query, limit=20)
        assert page.hits == []
        assert page.next_cursor is None
