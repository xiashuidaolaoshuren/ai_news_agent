"""Tests for /api/v1 session and meta routes (Milestone 8A.1 T13–T15)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest


def _build_test_client(*, fake: bool, db_path: Path):
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import build_application

    application = build_application(fake=fake, db_path=db_path)
    return TestClient(create_app(application))


def _parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event_name: str | None = None
        data: dict | None = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_name is not None and data is not None:
            events.append((event_name, data))
    return events


def test_post_message_rejects_invalid_juya_item_mode(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "juya-mode-invalid.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "Give me today's AI digest", "juya_item_mode": "chapters"},
    )

    assert response.status_code in (400, 422)


def test_post_message_juya_stories_mode_returns_story_digest_entries(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "juya-stories.db")
    session_id = client.post(
        "/api/v1/sessions",
        json={"connector_names": ["juya"]},
    ).json()["id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "content": "Give me today's AI digest",
            "client_request_id": "req-juya-stories",
            "juya_item_mode": "stories",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    digest_payload = next(payload for name, payload in _parse_sse_events(body) if name == "digest")
    entries = digest_payload["digest"]["entries"]
    assert len(entries) >= 2
    assert entries[0]["item_type"] == "story"
    assert entries[0]["story"]["number"] == 1
    assert entries[1]["story"]["number"] == 2

    transcript = client.get(f"/api/v1/sessions/{session_id}/messages").json()
    assistant = next(m for m in transcript["messages"] if m["role"] == "assistant")
    assert assistant["digest"]["entries"][0]["item_type"] == "story"


def test_post_message_unknown_field_returns_400(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "validation-400.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "hello", "unexpected": True},
    )

    assert response.status_code == 400


def test_openapi_documents_session_message_stream_as_sse(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "openapi-sse.db")
    schema = client.get("/openapi.json").json()
    post = schema["paths"]["/api/v1/sessions/{session_id}/messages"]["post"]
    success = post["responses"]["200"]
    assert "text/event-stream" in success["content"]
    stream_schema = success["content"]["text/event-stream"]["schema"]
    if "oneOf" in stream_schema:
        assert stream_schema.get("discriminator", {}).get("propertyName") == "event"
        assert len(stream_schema["oneOf"]) >= 6
    elif "$ref" in stream_schema:
        ref_name = stream_schema["$ref"].rsplit("/", 1)[-1]
        event_schema = schema["components"]["schemas"][ref_name]
        assert "event" in event_schema.get("properties", {})
    else:
        assert "event" in stream_schema.get("properties", {})
    schema_names = schema["components"]["schemas"]
    assert any(name.endswith("Payload") for name in schema_names)
    assert any("DigestView" in json.dumps(schema_names[name]) for name in schema_names)


def test_fastapi_shell_surface_importable() -> None:
    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import Application, build_application

    assert Application is not None
    assert callable(build_application)
    assert callable(create_app)


def test_api_v1_health_reports_status_and_fake_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "digest.db"
    client = _build_test_client(fake=True, db_path=db_path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "fake": True}


def test_api_v1_sources_lists_defaults_and_opt_in_metadata(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "digest.db")

    response = client.get("/api/v1/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["defaults"] == ["juya"]
    assert [item["name"] for item in payload["sources"]] == [
        "juya",
        "huggingface",
        "github",
        "zhihu",
        "bilibili",
    ]
    by_name = {item["name"]: item for item in payload["sources"]}
    assert by_name["juya"] == {"name": "juya", "default": True, "opt_in": False}
    assert by_name["github"] == {"name": "github", "default": False, "opt_in": True}


def test_api_v1_allows_loopback_cors_origins_only(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "digest.db")

    for origin in ("http://127.0.0.1:5173", "http://localhost:5173"):
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == origin

    blocked = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert blocked.headers.get("access-control-allow-origin") is None

    wildcard = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert wildcard.headers.get("access-control-allow-origin") != "*"


def test_build_application_fake_skips_live_model_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_news_agent.services.composition import build_application

    calls: list[str] = []

    def _track_build_chat_model() -> object:
        calls.append("build_chat_model")
        return object()

    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_chat_model",
        _track_build_chat_model,
    )

    application = build_application(fake=True, db_path=tmp_path / "digest.db")

    assert application.fake is True
    assert calls == []
    assert application.chat_service is not None
    assert application.session_service is not None


def test_encode_sse_formats_event_frame() -> None:
    from ai_news_agent.api.sse import encode_sse

    frame = encode_sse("started", {"request_id": "req-1", "user_message_id": 7})

    assert frame == (
        'event: started\ndata: {"request_id":"req-1","user_message_id":7}\n\n'
    )


def test_post_and_get_session(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sessions-crud.db")

    create = client.post("/api/v1/sessions")
    assert create.status_code == 201
    payload = create.json()
    assert payload["id"]
    assert payload["title"] is None
    assert payload["connector_names"] is None
    assert payload["items_per_source"] is None
    assert payload["created_at"]
    assert payload["updated_at"]

    fetched = client.get(f"/api/v1/sessions/{payload['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == payload["id"]

    missing = client.get("/api/v1/sessions/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


def test_list_sessions_cursor_page(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sessions-page.db")
    ids: list[str] = []
    for idx in range(3):
        response = client.post("/api/v1/sessions")
        ids.append(response.json()["id"])
        client.patch(
            f"/api/v1/sessions/{ids[-1]}",
            json={"title": f"Session {idx}"},
        )

    first = client.get("/api/v1/sessions", params={"limit": 2})
    assert first.status_code == 200
    page = first.json()
    assert "sessions" in page
    assert "next_cursor" in page
    assert len(page["sessions"]) == 2
    assert page["next_cursor"] is not None
    first_ids = {item["id"] for item in page["sessions"]}
    assert len(first_ids) == 2

    second = client.get(
        "/api/v1/sessions",
        params={"limit": 2, "cursor": page["next_cursor"]},
    )
    assert second.status_code == 200
    page2 = second.json()
    assert len(page2["sessions"]) == 1
    assert page2["next_cursor"] is None
    assert page2["sessions"][0]["id"] not in first_ids


def test_patch_session_rename_and_preferences_validation(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sessions-patch.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    patched = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={
            "title": "Renamed",
            "connector_names": ["github", "juya"],
            "items_per_source": 5,
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["title"] == "Renamed"
    assert body["connector_names"] == ["github", "juya"]
    assert body["items_per_source"] == 5

    invalid_source = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"connector_names": ["not-a-source"]},
    )
    assert invalid_source.status_code == 400

    invalid_items = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"items_per_source": 21},
    )
    assert invalid_items.status_code == 400

    missing = client.patch(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000",
        json={"title": "Nope"},
    )
    assert missing.status_code == 404


def test_patch_session_partial_preferences_preserve_sibling(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sessions-partial-patch.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    both = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"connector_names": ["github", "juya"], "items_per_source": 5},
    )
    assert both.status_code == 200
    assert both.json()["connector_names"] == ["github", "juya"]
    assert both.json()["items_per_source"] == 5

    only_items = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"items_per_source": 7},
    )
    assert only_items.status_code == 200
    items_body = only_items.json()
    assert items_body["items_per_source"] == 7
    assert items_body["connector_names"] == ["github", "juya"]

    only_names = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"connector_names": ["zhihu"]},
    )
    assert only_names.status_code == 200
    names_body = only_names.json()
    assert names_body["connector_names"] == ["zhihu"]
    assert names_body["items_per_source"] == 7

    title_only = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": "Renamed only"},
    )
    assert title_only.status_code == 200
    title_body = title_only.json()
    assert title_body["title"] == "Renamed only"
    assert title_body["connector_names"] == ["zhihu"]
    assert title_body["items_per_source"] == 7


def test_delete_session_rules(tmp_path: Path) -> None:
    from ai_news_agent.services.composition import build_application

    db_path = tmp_path / "sessions-delete.db"
    application = build_application(fake=True, db_path=db_path)
    client = _build_test_client(fake=True, db_path=db_path)
    session_id = client.post("/api/v1/sessions").json()["id"]

    application.session_service.begin_request(
        session_id,
        content="busy",
        request_id="active-req",
    )
    busy = client.delete(f"/api/v1/sessions/{session_id}")
    assert busy.status_code == 409
    assert busy.json()["detail"]["code"] == "session_busy"

    application.session_service.complete_request(
        session_id,
        "active-req",
        status="succeeded",
        content="done",
    )
    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 204

    missing = client.delete(f"/api/v1/sessions/{session_id}")
    assert missing.status_code == 404


def test_session_responses_include_digest_count_and_active_request_id(
    tmp_path: Path,
) -> None:
    from ai_news_agent.services.composition import build_application

    db_path = tmp_path / "sessions-stats.db"
    application = build_application(fake=True, db_path=db_path)
    client = _build_test_client(fake=True, db_path=db_path)

    created = client.post("/api/v1/sessions")
    assert created.status_code == 201
    created_body = created.json()
    session_id = created_body["id"]
    assert created_body["digest_count"] == 0
    assert created_body["active_request_id"] is None

    application.session_service.begin_request(
        session_id,
        content="first digest",
        request_id="req-stats-1",
    )
    active = client.get(f"/api/v1/sessions/{session_id}").json()
    assert active["digest_count"] == 0
    assert active["active_request_id"] == "req-stats-1"

    run_id = application.digest_store.save_run(
        requested_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
        timeframe="today",
        topics=["ai"],
        connector_names=["github"],
    )
    application.session_service.complete_request(
        session_id,
        "req-stats-1",
        status="succeeded",
        content="digest text",
        run_id=run_id,
    )
    completed = client.get(f"/api/v1/sessions/{session_id}").json()
    assert completed["digest_count"] == 1
    assert completed["active_request_id"] is None

    application.session_service.begin_request(
        session_id,
        content="tell me more",
        request_id="req-stats-2",
    )
    application.session_service.complete_request(
        session_id,
        "req-stats-2",
        status="succeeded",
        content="follow-up text",
    )
    application.session_service.begin_request(
        session_id,
        content="something failing",
        request_id="req-stats-3",
    )
    application.session_service.complete_request(
        session_id,
        "req-stats-3",
        status="failed",
        content="error text",
        error_code="provider_error",
    )
    application.session_service.begin_request(
        session_id,
        content="cancel this",
        request_id="req-stats-4",
    )
    assert application.session_service.cancel_request(session_id, "req-stats-4") is True

    non_digest = client.get(f"/api/v1/sessions/{session_id}").json()
    assert non_digest["digest_count"] == 1
    assert non_digest["active_request_id"] is None

    application.session_service.begin_request(
        session_id,
        content="another digest",
        request_id="req-stats-5",
    )
    listed = client.get("/api/v1/sessions").json()
    entry = next(item for item in listed["sessions"] if item["id"] == session_id)
    assert entry["digest_count"] == 1
    assert entry["active_request_id"] == "req-stats-5"

    application.session_service.interrupt_active_requests()
    interrupted = client.get(f"/api/v1/sessions/{session_id}").json()
    assert interrupted["digest_count"] == 1
    assert interrupted["active_request_id"] is None

    patched = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": "Stats"},
    ).json()
    assert patched["digest_count"] == 1
    assert patched["active_request_id"] is None


def _seed_digest_transcript(tmp_path: Path) -> tuple[object, str, int]:
    from ai_news_agent.models import Digest, DigestEntry, FollowUpAction, SourceKind
    from ai_news_agent.repositories.session_store import SessionStore
    from ai_news_agent.services.composition import build_application
    from ai_news_agent.storage import DigestStore
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app

    db_path = tmp_path / "messages-digest.db"
    application = build_application(fake=True, db_path=db_path)
    client = TestClient(create_app(application))
    session_id = client.post("/api/v1/sessions").json()["id"]

    store = DigestStore(db_path)
    collected = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    run_id = store.save_run(
        requested_at=collected,
        timeframe="today",
        topics=["ai"],
        connector_names=["github"],
        session_id=session_id,
    )
    digest = Digest(
        generated_at=collected,
        entries=[
            DigestEntry(
                source_kind=SourceKind.GITHUB,
                source_id="repo-1",
                title="Repo 1",
                source_name="GitHub",
                source_url="https://example.com/repo-1",
                summary="summary",
                why_it_matters="why",
                background_knowledge="bg",
                follow_up_action=FollowUpAction.READ,
            )
        ],
        topics=["ai"],
        timeframe="today",
    )
    store.save_digest(run_id, digest)

    session_store = SessionStore(db_path)
    session_store.insert_message(session_id, role="user", content="Give me a digest")
    session_store.insert_message(
        session_id,
        role="assistant",
        content="Digest text",
        run_id=run_id,
    )
    return client, session_id, run_id


def test_list_messages_page_includes_digest_view(tmp_path: Path) -> None:
    client, session_id, run_id = _seed_digest_transcript(tmp_path)

    response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    page = response.json()
    assert "messages" in page
    assert "next_cursor" in page
    assert len(page["messages"]) >= 1
    sequences = [message["sequence"] for message in page["messages"]]
    assert sequences == sorted(sequences)

    assistant = next(
        message for message in page["messages"] if message["role"] == "assistant"
    )
    assert assistant["run_id"] == run_id
    assert assistant["digest"] is not None
    assert assistant["digest"]["entries"][0]["display_rank"] == 1

    missing = client.get(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/messages"
    )
    assert missing.status_code == 404


def test_list_messages_digest_message_exposes_digest_id_and_warnings(
    tmp_path: Path,
) -> None:
    from ai_news_agent.models import ConnectorWarning
    from ai_news_agent.repositories.session_store import SessionStore
    from ai_news_agent.storage import DigestStore

    client, session_id, run_id = _seed_digest_transcript(tmp_path)
    db_path = tmp_path / "messages-digest.db"
    store = DigestStore(db_path)
    store.save_connector_warnings(
        run_id,
        [
            ConnectorWarning(
                connector="github",
                code="rate_limited",
                message="github rate limited",
                detail="retry later",
            )
        ],
    )
    SessionStore(db_path).insert_message(
        session_id,
        role="assistant",
        content="Follow-up answer",
    )

    response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    messages = response.json()["messages"]

    assistant = next(
        message
        for message in messages
        if message["role"] == "assistant" and message["digest"] is not None
    )
    assert assistant["digest_id"] == store.get_digest_id_for_run(run_id)
    assert assistant["warnings"] == [
        {
            "connector": "github",
            "code": "rate_limited",
            "message": "github rate limited",
            "detail": "retry later",
        }
    ]

    user = next(message for message in messages if message["role"] == "user")
    assert user["digest_id"] is None
    assert user["warnings"] == []

    non_digest = next(
        message
        for message in messages
        if message["role"] == "assistant" and message["digest"] is None
    )
    assert non_digest["digest_id"] is None
    assert non_digest["warnings"] == []


def test_list_messages_digest_without_warnings_returns_empty_list(tmp_path: Path) -> None:
    client, session_id, _run_id = _seed_digest_transcript(tmp_path)

    response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    assistant = next(
        message
        for message in response.json()["messages"]
        if message["role"] == "assistant"
    )

    assert assistant["digest_id"] is not None
    assert assistant["warnings"] == []


def test_post_message_progress_structured_fields_on_sse(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sse-progress-structured.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "content": "Give me today's AI digest",
            "client_request_id": "req-progress-structured",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    progress_payloads = [
        payload for name, payload in _parse_sse_events(body) if name == "progress"
    ]
    assert progress_payloads

    calling = next(
        payload
        for payload in progress_payloads
        if payload["stage"].startswith("Calling ")
    )
    assert calling["source"] is not None
    assert calling["status"] == "running"
    assert calling["count"] is None

    done = next(
        payload
        for payload in progress_payloads
        if payload["stage"].startswith("Done ")
    )
    assert done["source"] is not None
    assert done["status"] == "done"
    assert isinstance(done["count"], int)

    parsing = next(
        payload for payload in progress_payloads if payload["stage"] == "Parsing request…"
    )
    assert parsing["source"] is None
    assert parsing["status"] is None
    assert parsing["count"] is None


def test_post_message_streams_sse_and_persists_transcript(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sse-happy.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "content": "Give me today's AI digest",
            "client_request_id": "req-digest-1",
        },
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = response.read().decode()

    events = _parse_sse_events(body)
    event_names = [name for name, _ in events]
    assert "started" in event_names
    assert "progress" in event_names or "delta" in event_names
    assert "digest" in event_names
    assert "done" in event_names

    started = next(payload for name, payload in events if name == "started")
    assert started["request_id"] == "req-digest-1"

    transcript = client.get(f"/api/v1/sessions/{session_id}/messages").json()
    roles = [message["role"] for message in transcript["messages"]]
    assert roles.count("user") == 1
    assert roles.count("assistant") == 1


def test_post_message_digest_sse_event_includes_digest_id(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sse-digest-id.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "content": "Give me today's AI digest",
            "client_request_id": "req-digest-id",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    digest_payload = next(
        payload for name, payload in _parse_sse_events(body) if name == "digest"
    )
    transcript = client.get(f"/api/v1/sessions/{session_id}/messages").json()
    assistant = next(
        message
        for message in transcript["messages"]
        if message["role"] == "assistant"
    )

    assert isinstance(digest_payload["digest_id"], int)
    assert digest_payload["digest_id"] == assistant["digest_id"]
    assert digest_payload["warnings"] == assistant["warnings"]


def test_session_digest_links_run_and_request_to_session(tmp_path: Path) -> None:
    import sqlite3

    from ai_news_agent.storage import DigestStore

    db_path = tmp_path / "sse-session-link.db"
    client = _build_test_client(fake=True, db_path=db_path)
    store = DigestStore(db_path)
    shared_run_id = store.save_run(
        requested_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
        timeframe="today",
        topics=["ai"],
        connector_names=["github"],
    )

    session_id = client.post("/api/v1/sessions").json()["id"]
    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "content": "Give me today's AI digest",
            "client_request_id": "req-linked-1",
        },
    ) as response:
        assert response.status_code == 200
        response.read()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_row = conn.execute(
            "SELECT id, session_id FROM runs WHERE id != ? ORDER BY id DESC LIMIT 1",
            (shared_run_id,),
        ).fetchone()
        request_row = conn.execute(
            "SELECT run_id, status FROM session_requests WHERE id = ?",
            ("req-linked-1",),
        ).fetchone()

    assert run_row is not None
    assert run_row["session_id"] == session_id
    assert request_row is not None
    assert request_row["run_id"] == run_row["id"]
    assert request_row["status"] == "succeeded"

    shared_ctx = store.get_latest_followup_context()
    assert shared_ctx.run_id == shared_run_id

    session_ctx = store.get_followup_context_for_session(session_id)
    assert session_ctx.run_id == run_row["id"]
    assert session_ctx.digest is not None


def test_post_message_status_mapping(tmp_path: Path) -> None:
    from ai_news_agent.services.composition import build_application

    db_path = tmp_path / "sse-status.db"
    application = build_application(fake=True, db_path=db_path)
    client = _build_test_client(fake=True, db_path=db_path)
    session_id = client.post("/api/v1/sessions").json()["id"]

    unknown = client.post(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/messages",
        json={"content": "hello"},
    )
    assert unknown.status_code == 404

    blank = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "   "},
    )
    assert blank.status_code == 400

    application.session_service.begin_request(
        session_id,
        content="first",
        request_id="active-one",
    )
    busy = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "second", "client_request_id": "active-two"},
    )
    assert busy.status_code == 409
    assert busy.json()["detail"]["code"] == "session_busy"

    duplicate = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "retry", "client_request_id": "active-one"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "request_in_progress"


def test_post_message_terminal_request_id_replays_without_new_messages(
    tmp_path: Path,
) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sse-replay.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "list sources", "client_request_id": "req-replay"},
    ) as first:
        assert first.status_code == 200
        first.read()

    before = client.get(f"/api/v1/sessions/{session_id}/messages").json()
    assert len(before["messages"]) == 2

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "ignored content", "client_request_id": "req-replay"},
    ) as replay:
        assert replay.status_code == 200
        body = replay.read().decode()

    events = _parse_sse_events(body)
    assert any(name == "started" for name, _ in events)
    assert any(name == "done" for name, _ in events)

    after = client.get(f"/api/v1/sessions/{session_id}/messages").json()
    assert len(after["messages"]) == 2


def test_post_message_terminal_digest_replay_emits_digest_sse_event(
    tmp_path: Path,
) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "sse-digest-replay.db")
    session_id = client.post("/api/v1/sessions").json()["id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "content": "Give me today's AI digest",
            "client_request_id": "req-digest-replay",
        },
    ) as first:
        assert first.status_code == 200
        first_body = first.read().decode()
    first_events = _parse_sse_events(first_body)
    assert "digest" in [name for name, _ in first_events]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "content": "ignored content",
            "client_request_id": "req-digest-replay",
        },
    ) as replay:
        assert replay.status_code == 200
        replay_body = replay.read().decode()

    replay_events = _parse_sse_events(replay_body)
    event_names = [name for name, _ in replay_events]
    assert "started" in event_names
    assert "delta" in event_names
    assert "digest" in event_names
    assert "done" in event_names
    digest_payload = next(payload for name, payload in replay_events if name == "digest")
    assert "run_id" in digest_payload
    assert "digest" in digest_payload
    assert "markdown" in digest_payload
    assert isinstance(digest_payload["digest_id"], int)


def test_shielded_sse_pump_persists_after_consumer_disconnect(tmp_path: Path) -> None:
    from ai_news_agent.api.routers.sessions import shielded_event_stream
    from ai_news_agent.services.chat import StartedEvent
    from ai_news_agent.services.composition import build_application

    db_path = tmp_path / "sse-pump.db"
    application = build_application(fake=True, db_path=db_path)
    session_id = application.session_service.create_session().id

    async def _consume_partially() -> None:
        stream = application.chat_service.stream_events(
            "list sources",
            session_id=session_id,
            request_id="pump-req",
            chunk_size=1000,
            chunk_delay_s=0,
        )
        shielded = shielded_event_stream(stream)
        event = await anext(shielded)
        assert isinstance(event, StartedEvent)
        await shielded.aclose()

    asyncio.run(_consume_partially())

    # Allow detached pump from partial consume to finish
    for _ in range(50):
        messages = application.session_service.list_messages(session_id)
        if any(message.role == "assistant" for message in messages):
            break
        asyncio.run(asyncio.sleep(0.05))
    else:
        pytest.fail("assistant message was not persisted after consumer disconnect")

    assistant = next(
        message
        for message in application.session_service.list_messages(session_id)
        if message.role == "assistant"
    )
    assert assistant.content


def test_get_request_status_returns_durable_fields(tmp_path: Path) -> None:
    from ai_news_agent.services.composition import build_application

    db_path = tmp_path / "request-status.db"
    application = build_application(fake=True, db_path=db_path)
    client = _build_test_client(fake=True, db_path=db_path)
    session_id = client.post("/api/v1/sessions").json()["id"]

    application.session_service.begin_request(
        session_id,
        content="Give me a digest",
        request_id="req-active",
    )
    active = client.get(f"/api/v1/sessions/{session_id}/requests/req-active")
    assert active.status_code == 200
    active_body = active.json()
    assert active_body["id"] == "req-active"
    assert active_body["session_id"] == session_id
    assert active_body["status"] == "active"
    assert active_body["user_message_id"] == 1
    assert active_body["assistant_message_id"] is None
    assert active_body["run_id"] is None

    application.session_service.complete_request(
        session_id,
        "req-active",
        status="succeeded",
        content="Done",
        run_id=None,
    )
    terminal = client.get(f"/api/v1/sessions/{session_id}/requests/req-active")
    assert terminal.status_code == 200
    terminal_body = terminal.json()
    assert terminal_body["status"] == "succeeded"
    assert terminal_body["assistant_message_id"] == 2

    missing_session = client.get(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/requests/req-active"
    )
    assert missing_session.status_code == 404

    missing_request = client.get(
        f"/api/v1/sessions/{session_id}/requests/missing-req"
    )
    assert missing_request.status_code == 404


def test_post_cancel_request_status_codes(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from ai_news_agent.repositories.session_store import SessionStore
    from ai_news_agent.services.composition import build_application

    db_path = tmp_path / "request-cancel.db"
    application = build_application(fake=True, db_path=db_path)
    client = _build_test_client(fake=True, db_path=db_path)
    session_id = client.post("/api/v1/sessions").json()["id"]

    application.session_service.begin_request(
        session_id,
        content="Please cancel me",
        request_id="req-cancel",
    )
    accepted = client.post(
        f"/api/v1/sessions/{session_id}/requests/req-cancel/cancel"
    )
    assert accepted.status_code == 202
    assert accepted.content == b""

    status = client.get(f"/api/v1/sessions/{session_id}/requests/req-cancel")
    assert status.json()["status"] == "cancelled"

    application.session_service.begin_request(
        session_id,
        content="Post persistence",
        request_id="req-active-run",
    )
    collected = datetime(2026, 5, 7, 10, 0, 0, tzinfo=UTC)
    run_id = application.digest_store.save_run(
        requested_at=collected,
        timeframe="today",
        topics=["RAG"],
        connector_names=["github"],
    )
    SessionStore(db_path).update_request_run_id(
        session_id,
        "req-active-run",
        run_id,
    )
    post_persistence = client.post(
        f"/api/v1/sessions/{session_id}/requests/req-active-run/cancel"
    )
    assert post_persistence.status_code == 204

    application.session_service.complete_request(
        session_id,
        "req-active-run",
        status="succeeded",
        content="Done",
        run_id=run_id,
    )
    terminal = client.post(
        f"/api/v1/sessions/{session_id}/requests/req-active-run/cancel"
    )
    assert terminal.status_code == 204

    unknown_request = client.post(
        f"/api/v1/sessions/{session_id}/requests/missing/cancel"
    )
    assert unknown_request.status_code == 204

    missing_session = client.post(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/requests/req-cancel/cancel"
    )
    assert missing_session.status_code == 404


def test_get_session_search_returns_ranked_hits(tmp_path: Path) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "session-search.db")

    title_session = client.post("/api/v1/sessions").json()["id"]
    client.patch(
        f"/api/v1/sessions/{title_session}",
        json={"title": "Weekly digest planning"},
    )
    user_session = client.post("/api/v1/sessions").json()["id"]
    client.patch(
        f"/api/v1/sessions/{user_session}",
        json={"title": "Other notes"},
    )
    with client.stream(
        "POST",
        f"/api/v1/sessions/{user_session}/messages",
        json={"content": "Weekly digest please", "client_request_id": "search-user"},
    ) as response:
        response.read()

    response = client.get("/api/v1/sessions/search", params={"q": "Weekly digest"})
    assert response.status_code == 200
    payload = response.json()
    assert "hits" in payload
    assert "next_cursor" in payload
    assert len(payload["hits"]) == 2
    by_session = {hit["session_id"]: hit for hit in payload["hits"]}
    assert by_session[title_session]["match_kind"] == "title"
    assert by_session[title_session]["message_id"] is None
    assert "Weekly digest" in by_session[title_session]["excerpt"]
    assert by_session[user_session]["match_kind"] == "user"
    assert by_session[user_session]["message_id"] is not None

    blank = client.get("/api/v1/sessions/search", params={"q": "   "})
    assert blank.status_code == 200
    assert blank.json() == {"hits": [], "next_cursor": None}


def test_get_session_search_cursor_pagination_and_invalid_cursor(
    tmp_path: Path,
) -> None:
    client = _build_test_client(fake=True, db_path=tmp_path / "session-search-page.db")

    for idx in range(3):
        session_id = client.post("/api/v1/sessions").json()["id"]
        client.patch(
            f"/api/v1/sessions/{session_id}",
            json={"title": f"Weekly digest note {idx}"},
        )

    first = client.get(
        "/api/v1/sessions/search",
        params={"q": "Weekly digest", "limit": 2},
    )
    assert first.status_code == 200
    page = first.json()
    assert len(page["hits"]) == 2
    assert page["next_cursor"] is not None
    first_ids = {hit["session_id"] for hit in page["hits"]}

    second = client.get(
        "/api/v1/sessions/search",
        params={
            "q": "Weekly digest",
            "limit": 2,
            "cursor": page["next_cursor"],
        },
    )
    assert second.status_code == 200
    page2 = second.json()
    assert len(page2["hits"]) == 1
    assert page2["next_cursor"] is None
    assert page2["hits"][0]["session_id"] not in first_ids

    invalid = client.get(
        "/api/v1/sessions/search",
        params={"q": "Weekly digest", "cursor": "not-a-cursor"},
    )
    assert invalid.status_code == 400


def test_build_application_live_uses_model_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_news_agent.services.composition import build_application

    calls: list[str] = []

    def _track_build_chat_model() -> object:
        calls.append("build_chat_model")
        return object()

    def _track_build_tool_chat_model() -> object:
        calls.append("build_tool_chat_model")
        return object()

    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_chat_model",
        _track_build_chat_model,
    )
    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_tool_chat_model",
        _track_build_tool_chat_model,
    )
    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_connector_factory",
        lambda **kw: object(),
    )
    monkeypatch.setattr(
        "ai_news_agent.services.composition.build_interface_tool_router",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr("ai_news_agent.services.composition.load_local_env", lambda **_: None)
    monkeypatch.setattr(
        "ai_news_agent.services.composition.configure_bilibili_network_from_env",
        lambda _: None,
    )

    application = build_application(fake=False, db_path=tmp_path / "digest.db")

    assert application.fake is False
    assert "build_chat_model" in calls
    assert "build_tool_chat_model" in calls
    assert application.chat_service is not None
