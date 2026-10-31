"""Tests for follow-up chat service (Task T11)."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_news_agent.services.chat import ChatService
from ai_news_agent.repositories.session_store import SessionStore
from ai_news_agent.services.chat import (
    DeltaEvent,
    DigestEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    StartedEvent,
)
from ai_news_agent.services.session_service import SessionService
from ai_news_agent.connectors.base import ConnectorResult
from ai_news_agent.graph.state import DigestResult
from ai_news_agent.models import (
    ConfidenceLevel,
    ConnectorWarning,
    Digest,
    DigestEntry,
    FollowUpAction,
    NewsItem,
    RankedItem,
    SourceKind,
)
from ai_news_agent.request import DigestRequest
from ai_news_agent.storage import DigestStore
from ai_news_agent.tools.schemas import (
    InterfaceAgentResult,
    InterfaceAgentResultKind,
)


def _bilibili_anti_bot_warning() -> ConnectorWarning:
    return ConnectorWarning(
        connector="bilibili",
        code="anti_bot_blocked",
        message=(
            "Bilibili keyword search blocked (anti-bot). "
            "Set BILIBILI_SESSDATA, BILIBILI_BILI_JCT, and BILIBILI_BUVID3 "
            "in .env, or use video URLs/channels."
        ),
    )


def test_resolve_digest_request_timeframe_defaults_last_7_days_for_bilibili_channel() -> None:
    from ai_news_agent.digest_request_builder import resolve_digest_request

    req = resolve_digest_request("Digest bilibili channel 285286947")

    assert req.bilibili_target_channels == ["285286947"]
    assert req.timeframe == "last_7_days"


def test_resolve_digest_request_preserves_explicit_timeframe_for_bilibili_channel() -> (
    None
):
    from ai_news_agent.digest_request_builder import resolve_digest_request

    req = resolve_digest_request("Digest bilibili channel 285286947 last 30 days")

    assert req.timeframe == "last_30_days"


def test_resolve_digest_request_no_timeframe_default_for_github_channel() -> None:
    from ai_news_agent.digest_request_builder import resolve_digest_request

    req = resolve_digest_request("Digest github user acme")

    assert req.github_target_channels == ["acme"]
    assert req.timeframe is None


def test_services_chat_surface_importable() -> None:
    from ai_news_agent.services.chat import (
        ChatService,
        DeltaEvent,
        DigestEvent,
        DoneEvent,
        ErrorEvent,
        ProgressEvent,
        StartedEvent,
    )

    assert ChatService.__name__ == "ChatService"
    assert StartedEvent.__name__ == "StartedEvent"
    assert ProgressEvent.__name__ == "ProgressEvent"
    assert DeltaEvent.__name__ == "DeltaEvent"
    assert DigestEvent.__name__ == "DigestEvent"
    assert DoneEvent.__name__ == "DoneEvent"
    assert ErrorEvent.__name__ == "ErrorEvent"


async def _collect_stream_events(service: ChatService, message: str, *, session_id: str, **kwargs):  # noqa: ANN003
    events: list = []
    async for event in service.stream_events(message, session_id=session_id, **kwargs):
        events.append(event)
    return events


def test_stream_events_digest_happy_path_sets_session_id(tmp_path: Path) -> None:
    db_path = tmp_path / "stream-digest.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()

    async def fake_streaming_runner(
        req: DigestRequest,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
    ):
        del request_id
        yield "Collecting items…", False, None
        collected = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        run_id = store.save_run(
            requested_at=collected,
            timeframe=req.timeframe,
            topics=list(req.topics),
            connector_names=list(req.connector_names or ["github"]),
        )
        if session_id is not None:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "UPDATE runs SET session_id = ? WHERE id = ?",
                    (session_id, run_id),
                )
                conn.commit()
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
            topics=list(req.topics),
            timeframe=req.timeframe,
        )
        item = NewsItem(
            source=SourceKind.GITHUB,
            source_id="repo-1",
            url="https://example.com/repo-1",
            title="Repo 1",
            collected_at=collected,
        )
        store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[]))
        store.save_ranked_items(run_id, [])
        store.save_digest(run_id, digest)
        yield "", True, DigestResult(
            request=req,
            digest=digest,
            run_id=run_id,
            markdown="# Session digest\n",
            text="# Session digest\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=collected,
            finished_at=collected,
        )

    svc = ChatService(
        store=store,
        workflow_runner=fake_streaming_runner,
        streaming_workflow_runner=fake_streaming_runner,
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "Give me today's AI digest",
            session_id=created.id,
            request_id="req-digest-1",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    assert any(isinstance(e, StartedEvent) for e in events)
    assert any(isinstance(e, ProgressEvent) for e in events)
    assert any(isinstance(e, DeltaEvent) for e in events)
    assert any(isinstance(e, DigestEvent) for e in events)
    assert any(isinstance(e, DoneEvent) for e in events)

    started = next(e for e in events if isinstance(e, StartedEvent))
    assert started.request_id == "req-digest-1"

    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.path == "digest"
    assert done.run_id is not None

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT session_id FROM runs WHERE id = ?",
            (done.run_id,),
        ).fetchone()
    assert row is not None
    assert row["session_id"] == created.id


class _SessionFollowupRouter:
    """Router double exposing the session-scoped follow-up hook."""

    def __init__(self, *, text: str = "router tool answer") -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    async def run_session_followup(
        self,
        *,
        session_id: str,
        message: str,
        correlation_id: str | None = None,
    ) -> InterfaceAgentResult:
        self.calls.append(
            {
                "session_id": session_id,
                "message": message,
                "correlation_id": correlation_id,
            }
        )
        return InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text=self.text,
        )


def _save_session_digest(
    store: DigestStore,
    session_store: SessionStore,
    *,
    session_id: str,
    topics: list[str],
    request_id: str,
    ensure_session: bool = True,
) -> int:
    collected = datetime(2026, 5, 7, 10, 0, 0, tzinfo=UTC)
    run_id = store.save_run(
        requested_at=collected,
        timeframe="today",
        topics=topics,
        connector_names=["github"],
    )
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE runs SET session_id = ? WHERE id = ?",
            (session_id, run_id),
        )
        conn.commit()
    item = NewsItem(
        source=SourceKind.GITHUB,
        source_id=f"repo-{topics[0]}",
        url=f"https://example.com/{topics[0]}",
        title=f"Repo {topics[0]}",
        collected_at=collected,
    )
    digest = Digest(
        generated_at=collected,
        entries=[
            DigestEntry(
                source_kind=SourceKind.GITHUB,
                source_id=item.source_id,
                title=item.title,
                source_name="GitHub",
                source_url=item.url,
                summary="summary",
                why_it_matters="why",
                background_knowledge="bg",
                follow_up_action=FollowUpAction.READ,
            )
        ],
        topics=topics,
        timeframe="today",
    )
    store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[]))
    store.save_ranked_items(run_id, [])
    store.save_digest(run_id, digest)
    if ensure_session:
        session_store.create_session(session_id)
    user_message_id = session_store.insert_message(
        session_id,
        role="user",
        content="digest please",
    )
    session_store.create_request(
        session_id,
        request_id,
        user_message_id=user_message_id,
        correlation_id=f"corr-{request_id}",
    )
    session_store.update_request_run_id(session_id, request_id, run_id)
    session_store.mark_terminal(session_id, request_id, status="succeeded")
    return run_id


def _save_session_digest_ids(
    store: DigestStore,
    session_store: SessionStore,
    *,
    session_id: str,
    topics: list[str],
    request_id: str,
    ensure_session: bool = True,
) -> tuple[int, int]:
    run_id = _save_session_digest(
        store,
        session_store,
        session_id=session_id,
        topics=topics,
        request_id=request_id,
        ensure_session=ensure_session,
    )
    digest_id = store.get_digest_id_for_run(run_id)
    assert digest_id is not None
    return run_id, digest_id


def test_stream_events_targeted_followup_uses_named_digest_skips_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "stream-targeted-followup.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()

    old_run_id, old_digest_id = _save_session_digest_ids(
        store,
        session_store,
        session_id=created.id,
        topics=["older-topic"],
        request_id="req-old-digest",
        ensure_session=False,
    )
    new_run_id, _new_digest_id = _save_session_digest_ids(
        store,
        session_store,
        session_id=created.id,
        topics=["newer-topic"],
        request_id="req-new-digest",
        ensure_session=False,
    )

    def _forbid_interpret(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("interpret_message must not run for targeted follow-up")

    monkeypatch.setattr("ai_news_agent.services.chat.interpret_message", _forbid_interpret)

    async def unused_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("digest runner must not run for targeted follow-up")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "follow up on item 1",
            session_id=created.id,
            request_id="req-targeted",
            followup_target={"digest_id": old_digest_id, "display_rank": 1},
            followup_action="ask",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    started = next(e for e in events if isinstance(e, StartedEvent))
    assert started.intent == "followup"
    latest = store.get_followup_context_for_session(created.id)
    assert latest.run_id == new_run_id
    assert latest.run_id != old_run_id
    deltas = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "older-topic" in deltas or "Repo older-topic" in deltas
    assert "newer-topic" not in deltas


def test_stream_events_targeted_followup_replaces_pending_clarification(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-targeted-clarify.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    _run_id, digest_id = _save_session_digest_ids(
        store,
        session_store,
        session_id=created.id,
        topics=["clarify-topic"],
        request_id="req-clarify-digest",
        ensure_session=False,
    )

    async def unused_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("digest runner must not run")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )

    asyncio.run(
        _collect_stream_events(
            svc,
            "What about Qwen",
            session_id=created.id,
            request_id="req-clarify",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    assert session_service.pending_clarification(created.id) is not None

    asyncio.run(
        _collect_stream_events(
            svc,
            "Deep dive",
            session_id=created.id,
            request_id="req-targeted-clarify",
            followup_target={"digest_id": digest_id, "display_rank": 1},
            followup_action="deep_dive",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    assert session_service.pending_clarification(created.id) is None


def test_stream_events_tell_me_about_streams_general_without_digest_runner(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-general-qwen.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()
    _save_session_digest(
        store,
        SessionStore(db_path),
        session_id=created.id,
        topics=["existing-topic"],
        request_id="req-existing-digest",
        ensure_session=False,
    )

    async def forbid_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("digest runner must not run for general explanation")

    svc = ChatService(
        store=store,
        workflow_runner=forbid_runner,
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "Tell me about Qwen",
            session_id=created.id,
            request_id="req-general-qwen",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    started = next(e for e in events if isinstance(e, StartedEvent))
    assert started.intent == "general"
    deltas = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "general knowledge" in deltas.lower()


def test_stream_events_self_contained_digest_replaces_pending_clarification(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-replace-clarify.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()

    async def fake_streaming_runner(
        req: DigestRequest,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
    ):
        del request_id
        collected = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        run_id = store.save_run(
            requested_at=collected,
            timeframe=req.timeframe,
            topics=list(req.topics),
            connector_names=list(req.connector_names or ["juya"]),
        )
        if session_id is not None:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "UPDATE runs SET session_id = ? WHERE id = ?",
                    (session_id, run_id),
                )
                conn.commit()
        digest = Digest(
            generated_at=collected,
            entries=[],
            topics=list(req.topics),
            timeframe=req.timeframe,
        )
        store.save_digest(run_id, digest)
        yield "", True, DigestResult(
            request=req,
            digest=digest,
            run_id=run_id,
            markdown="digest",
            text="digest",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=collected,
            finished_at=collected,
        )

    svc = ChatService(
        store=store,
        workflow_runner=fake_streaming_runner,
        streaming_workflow_runner=fake_streaming_runner,
        session_service=session_service,
    )

    asyncio.run(
        _collect_stream_events(
            svc,
            "What about agents",
            session_id=created.id,
            request_id="req-clarify-agents",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    assert session_service.pending_clarification(created.id) is not None
    assert session_service.pending_clarification(created.id)["topic"] == "agents"

    asyncio.run(
        _collect_stream_events(
            svc,
            "Recent Llama updates",
            session_id=created.id,
            request_id="req-replace-digest",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    pending = session_service.pending_clarification(created.id)
    assert pending is None


def _save_session_hf_digest(
    store: DigestStore,
    session_store: SessionStore,
    *,
    session_id: str,
    topics: list[str],
    request_id: str,
    ensure_session: bool = True,
    raw_snippet: str | None = "Saved snippet.",
) -> tuple[int, int]:
    collected = datetime(2026, 5, 7, 10, 0, 0, tzinfo=UTC)
    source_id = f"Org/Model-{topics[0]}"
    item = NewsItem(
        source=SourceKind.HUGGINGFACE,
        source_id=source_id,
        url=f"https://huggingface.co/{source_id}",
        title=f"Model {topics[0]}",
        collected_at=collected,
        content_confidence=ConfidenceLevel.HIGH,
        raw_snippet=raw_snippet,
        source_evidence={"trending_score": 88.0, "downloads_30d": 100},
    )
    entry = DigestEntry(
        source_kind=SourceKind.HUGGINGFACE,
        source_id=source_id,
        title=item.title,
        source_name="Hugging Face",
        source_url=item.url,
        summary="HF summary",
        why_it_matters="why",
        background_knowledge="bg",
        follow_up_action=FollowUpAction.READ,
    )
    digest = Digest(
        generated_at=collected,
        entries=[entry],
        topics=topics,
        timeframe="today",
    )
    run_id = store.save_run(
        requested_at=collected,
        timeframe="today",
        topics=topics,
        connector_names=["huggingface"],
    )
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE runs SET session_id = ? WHERE id = ?",
            (session_id, run_id),
        )
        conn.commit()
    store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[]))
    store.save_ranked_items(run_id, [RankedItem(item=item, score_total=1.0, selected=True)])
    store.save_digest(run_id, digest)
    digest_id = store.get_digest_id_for_run(run_id)
    assert digest_id is not None
    if ensure_session:
        session_store.create_session(session_id)
    user_message_id = session_store.insert_message(
        session_id,
        role="user",
        content="digest please",
    )
    session_store.create_request(
        session_id,
        request_id,
        user_message_id=user_message_id,
        correlation_id=f"corr-{request_id}",
    )
    session_store.update_request_run_id(session_id, request_id, run_id)
    session_store.mark_terminal(session_id, request_id, status="succeeded")
    return run_id, digest_id


def test_targeted_deep_dive_hf_returns_family_card(tmp_path: Path) -> None:
    db_path = tmp_path / "targeted-deep-dive-hf.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    _run_id, digest_id = _save_session_hf_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["hf-card"],
        request_id="req-hf",
        ensure_session=False,
    )

    async def unused_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("digest runner must not run")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "Deep dive",
            session_id=created.id,
            request_id="req-deep-dive",
            followup_target={"digest_id": digest_id, "display_rank": 1},
            followup_action="deep_dive",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    deltas = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "Rank 1" in deltas
    assert "Model hf-card" in deltas
    assert "configured language model" not in deltas


def test_targeted_deep_dive_older_digest_does_not_fetch(tmp_path: Path) -> None:
    db_path = tmp_path / "targeted-deep-dive-old.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    _old_run, old_digest_id = _save_session_hf_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["older-hf"],
        request_id="req-old-hf",
        ensure_session=False,
    )
    _new_run, _new_digest_id = _save_session_hf_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["newer-hf"],
        request_id="req-new-hf",
        ensure_session=False,
    )

    factory = MagicMock(return_value=MagicMock())

    svc = ChatService(
        store=store,
        workflow_runner=AsyncMock(),
        session_service=session_service,
        huggingface_connector_factory=factory,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "Deep dive",
            session_id=created.id,
            request_id="req-old-deep-dive",
            followup_target={"digest_id": old_digest_id, "display_rank": 1},
            followup_action="deep_dive",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    deltas = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "saved with this digest" in deltas.lower()
    factory.assert_not_called()


def test_targeted_deep_dive_latest_digest_fetches_once(tmp_path: Path) -> None:
    db_path = tmp_path / "targeted-deep-dive-fetch.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    _run_id, digest_id = _save_session_hf_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["latest-hf"],
        request_id="req-latest-hf",
        ensure_session=False,
    )
    ctx = store.get_followup_context_for_digest(digest_id)
    assert ctx is not None
    base_item = ctx.news_items[0]
    enriched = NewsItem(
        source=base_item.source,
        source_id=base_item.source_id,
        url=base_item.url,
        title=base_item.title,
        collected_at=base_item.collected_at,
        content_confidence=ConfidenceLevel.HIGH,
        raw_snippet="Live README.",
        source_evidence={
            "trending_score": 88.0,
            "downloads_30d": 100,
            "model_card_live_fetched": True,
        },
    )
    mock_connector = MagicMock()
    mock_connector.enrich_news_item = AsyncMock(return_value=(enriched, []))
    mock_connector.aclose = AsyncMock()
    factory = MagicMock(return_value=mock_connector)

    svc = ChatService(
        store=store,
        workflow_runner=AsyncMock(),
        session_service=session_service,
        huggingface_connector_factory=factory,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "Deep dive",
            session_id=created.id,
            request_id="req-fetch-deep-dive",
            followup_target={"digest_id": digest_id, "display_rank": 1},
            followup_action="deep_dive",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    deltas = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "Live README." in deltas
    assert "after digest" in deltas.lower()
    factory.assert_called_once()
    mock_connector.enrich_news_item.assert_awaited_once()


def test_targeted_ask_calls_generate_followup_reply_without_fetch(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "targeted-ask-model.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    _run_id, digest_id = _save_session_hf_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["ask-hf"],
        request_id="req-ask-hf",
        ensure_session=False,
    )

    factory = MagicMock(return_value=MagicMock())
    calls: list[dict[str, object]] = []

    class _Model:
        def generate_followup_reply(self, *, question: str, grounding: dict) -> str:
            calls.append({"question": question, "grounding": grounding})
            return "Grounded answer."

    svc = ChatService(
        store=store,
        workflow_runner=AsyncMock(),
        session_service=session_service,
        chat_model=_Model(),
        huggingface_connector_factory=factory,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "What is the download count?",
            session_id=created.id,
            request_id="req-ask",
            followup_target={"digest_id": digest_id, "display_rank": 1},
            followup_action="ask",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    deltas = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert deltas == "Grounded answer."
    assert len(calls) == 1
    grounding = calls[0]["grounding"]
    assert "entries" not in grounding
    assert "ranked_items" not in grounding
    assert "news_items" not in grounding
    factory.assert_not_called()


def test_targeted_ask_without_model_returns_card_and_unavailable_note(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "targeted-ask-fallback.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    _run_id, digest_id = _save_session_hf_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["ask-fallback"],
        request_id="req-ask-fallback",
        ensure_session=False,
    )

    svc = ChatService(
        store=store,
        workflow_runner=AsyncMock(),
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "What is trending?",
            session_id=created.id,
            request_id="req-ask-fallback-send",
            followup_target={"digest_id": digest_id, "display_rank": 1},
            followup_action="ask",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    deltas = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "Rank 1" in deltas
    assert "Question-specific answering is unavailable." in deltas


def test_stream_events_followup_uses_session_context_not_shared_or_other_session(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-followup.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)

    shared_run_id = _save_session_digest(
        store,
        session_store,
        session_id="unused-for-shared",
        topics=["shared-latest"],
        request_id="req-shared",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE runs SET session_id = NULL WHERE id = ?",
            (shared_run_id,),
        )
        conn.commit()

    session_a = session_service.create_session()
    session_b = session_service.create_session()
    _save_session_digest(
        store,
        session_store,
        session_id=session_a.id,
        topics=["session-a-topic"],
        request_id="req-a",
        ensure_session=False,
    )
    _save_session_digest(
        store,
        session_store,
        session_id=session_b.id,
        topics=["session-b-topic"],
        request_id="req-b",
        ensure_session=False,
    )

    async def unused_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("digest runner must not run for follow-up")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "list sources",
            session_id=session_b.id,
            request_id="req-followup-b",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    deltas = [e.text for e in events if isinstance(e, DeltaEvent)]
    joined = "".join(deltas)
    assert "session-b-topic" in joined or "Repo session-b-topic" in joined
    assert "session-a-topic" not in joined
    assert "shared-latest" not in joined
    assert any(isinstance(e, DoneEvent) for e in events)
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.path == "followup"


def test_stream_events_session_followup_uses_interface_router_tool_agent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "router-followup.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    _save_session_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["router-topic"],
        request_id="req-router",
        ensure_session=False,
    )

    router = _SessionFollowupRouter(text="router tool answer")

    async def unused_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("digest runner must not run for follow-up")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
        interface_router=router,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "Why does the top item matter for my team?",
            session_id=created.id,
            request_id="req-router-followup",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    joined = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "router tool answer" in joined
    assert len(router.calls) == 1
    assert router.calls[0]["session_id"] == created.id
    assert router.calls[0]["message"] == "Why does the top item matter for my team?"
    assert any(isinstance(e, DoneEvent) for e in events)


def test_stream_events_session_structured_followup_skips_interface_router(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "router-structured.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    _save_session_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["router-topic"],
        request_id="req-router-structured",
        ensure_session=False,
    )

    router = _SessionFollowupRouter()

    async def unused_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("digest runner must not run for follow-up")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
        interface_router=router,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "show sources",
            session_id=created.id,
            request_id="req-router-structured-followup",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    joined = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "https://example.com/router-topic" in joined
    assert router.calls == []


def test_stream_events_digest_failure_emits_error_without_raw_exception_detail(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-failure.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()

    async def failing_runner(_: DigestRequest, *, session_id: str | None = None):
        yield "Collecting items…", False, None
        raise RuntimeError("secret internal db password leak")

    svc = ChatService(
        store=store,
        workflow_runner=failing_runner,
        streaming_workflow_runner=failing_runner,
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "Give me today's AI digest",
            session_id=created.id,
            request_id="req-fail",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code == "workflow_error"
    assert "password" not in error.message
    assert "secret" not in error.message

    row = SessionStore(db_path).get_request(created.id, "req-fail")
    assert row is not None
    assert row.status == "failed"
    assert row.error_code == "workflow_error"
    assert row.error_message == error.message
    assert row.error_message is not None
    assert "password" not in row.error_message


async def _collect_stream_events_with_cancel(
    service: ChatService,
    message: str,
    *,
    session_id: str,
    session_service: SessionService,
    request_id: str,
    gate: asyncio.Event,
) -> list:
    events: list = []

    async def fake_streaming(_: DigestRequest, *, session_id: str | None = None):
        yield "Collecting items…", False, None
        await gate.wait()
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        req = DigestRequest(topics=["AI"])
        yield "", True, DigestResult(
            request=req,
            digest=None,
            run_id=999,
            markdown="should not persist",
            text="should not persist",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    service._streaming_workflow_runner = fake_streaming  # noqa: SLF001
    service._workflow_runner = fake_streaming  # noqa: SLF001

    collect_task = asyncio.create_task(
        _collect_stream_events(
            service,
            message,
            session_id=session_id,
            request_id=request_id,
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    await asyncio.sleep(0.05)
    session_service.cancel_request(session_id, request_id)
    gate.set()
    return await collect_task


def test_stream_events_cooperative_cancel_emits_error_without_digest_persist(
    tmp_path: Path,
) -> None:
    from ai_news_agent.services.session_service import CANCELLED_ASSISTANT_MESSAGE

    db_path = tmp_path / "stream-cancel.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()
    gate = asyncio.Event()

    svc = ChatService(
        store=store,
        workflow_runner=lambda _: None,
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events_with_cancel(
            svc,
            "Give me today's AI digest",
            session_id=created.id,
            session_service=session_service,
            request_id="req-cancel",
            gate=gate,
        )
    )

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code == "cancelled"
    assert error.message == CANCELLED_ASSISTANT_MESSAGE
    assert not any(isinstance(e, DigestEvent) for e in events)
    assert not any(isinstance(e, DoneEvent) for e in events)

    row = SessionStore(db_path).get_request(created.id, "req-cancel")
    assert row is not None
    assert row.status == "cancelled"
    assert row.run_id is None


def test_stream_events_terminal_replay_returns_stored_outcome_without_rerun(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-replay.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()

    run_calls: list[str] = []

    async def counting_runner(_: DigestRequest, *, session_id: str | None = None):
        run_calls.append(session_id or "")
        yield "", True, None

    svc = ChatService(
        store=store,
        workflow_runner=counting_runner,
        streaming_workflow_runner=counting_runner,
        session_service=session_service,
    )

    first = asyncio.run(
        _collect_stream_events(
            svc,
            "list sources",
            session_id=created.id,
            request_id="req-replay",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    assert any(isinstance(e, DoneEvent) for e in first)
    assert run_calls == []

    replay = asyncio.run(
        _collect_stream_events(
            svc,
            "list sources",
            session_id=created.id,
            request_id="req-replay",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    assert any(isinstance(e, StartedEvent) for e in replay)
    assert any(isinstance(e, DeltaEvent) for e in replay)
    assert any(isinstance(e, DoneEvent) for e in replay)
    assert run_calls == []
    assert len(SessionStore(db_path).list_messages(created.id)) == 2


def test_stream_events_digest_deltas_and_persistence_use_markdown(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-digest-markdown.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()
    warning = _bilibili_anti_bot_warning()
    notice = warning.message
    markdown = f"⚠ {notice}\n\n# Authoritative Markdown\n"
    plain_text = "Plain text body\n"
    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    digest = Digest(
        generated_at=now,
        entries=[],
        topics=["AI"],
        timeframe="today",
    )

    async def markdown_streaming_runner(
        req: DigestRequest,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
    ):
        del request_id
        yield "Collecting items…", False, None
        run_id = store.save_run(
            requested_at=now,
            timeframe=req.timeframe,
            topics=list(req.topics),
            connector_names=list(req.connector_names or ["github"]),
            session_id=session_id,
        )
        store.save_digest(run_id, digest)
        yield "", True, DigestResult(
            request=req,
            digest=digest,
            run_id=run_id,
            markdown=markdown,
            text=plain_text,
            ranked_items=[],
            warnings=[warning],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    svc = ChatService(
        store=store,
        workflow_runner=lambda _: None,
        streaming_workflow_runner=markdown_streaming_runner,
        session_service=session_service,
    )

    first = asyncio.run(
        _collect_stream_events(
            svc,
            "Give me today's AI digest",
            session_id=created.id,
            request_id="req-md-digest",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    joined = "".join(e.text for e in first if isinstance(e, DeltaEvent))
    digest_event = next(e for e in first if isinstance(e, DigestEvent))
    assert joined == markdown
    assert digest_event.markdown == markdown
    assert joined != plain_text
    assert digest_event.markdown != plain_text

    messages = SessionStore(db_path).list_messages(created.id)
    assistant = messages[-1]
    assert assistant.role == "assistant"
    assert assistant.content == markdown

    replay = asyncio.run(
        _collect_stream_events(
            svc,
            "Give me today's AI digest",
            session_id=created.id,
            request_id="req-md-digest",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )
    replay_joined = "".join(e.text for e in replay if isinstance(e, DeltaEvent))
    replay_digest = next(e for e in replay if isinstance(e, DigestEvent))
    assert replay_joined == markdown
    assert replay_digest.markdown == markdown


def test_stream_events_terminal_digest_replay_emits_digest_event(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-digest-replay.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_store = SessionStore(db_path)
    session_service = SessionService(session_store)
    created = session_service.create_session()
    run_id = _save_session_digest(
        store,
        session_store,
        session_id=created.id,
        topics=["replay-topic"],
        request_id="req-digest-replay",
        ensure_session=False,
    )
    assistant_id = session_store.insert_message(
        created.id,
        role="assistant",
        content="Rendered digest markdown",
        run_id=run_id,
    )
    session_store.mark_terminal(
        created.id,
        "req-digest-replay",
        status="succeeded",
        assistant_message_id=assistant_id,
    )

    async def forbidden_runner(_: DigestRequest, *, session_id: str | None = None):
        raise AssertionError("digest runner must not run on replay")

    svc = ChatService(
        store=store,
        workflow_runner=forbidden_runner,
        streaming_workflow_runner=forbidden_runner,
        session_service=session_service,
    )

    replay = asyncio.run(
        _collect_stream_events(
            svc,
            "digest please",
            session_id=created.id,
            request_id="req-digest-replay",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    assert any(isinstance(e, StartedEvent) for e in replay)
    assert any(isinstance(e, DeltaEvent) for e in replay)
    digest_events = [e for e in replay if isinstance(e, DigestEvent)]
    assert len(digest_events) == 1
    assert digest_events[0].run_id == run_id
    assert digest_events[0].digest is not None
    assert digest_events[0].markdown == "Rendered digest markdown"
    done = next(e for e in replay if isinstance(e, DoneEvent))
    assert done.path == "digest"
    assert done.run_id == run_id


def test_stream_events_followup_cancel_emits_cancelled_error(
    tmp_path: Path,
) -> None:
    from ai_news_agent.services.session_service import CANCELLED_ASSISTANT_MESSAGE

    db_path = tmp_path / "stream-followup-cancel.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()
    gate = asyncio.Event()

    async def unused_runner(_: DigestRequest, *, session_id: str | None = None):
        raise AssertionError("digest runner must not run")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )

    async def slow_followup(
        session_id: str,
        message: str,
        **kwargs: object,
    ) -> str:
        del session_id, message, kwargs
        await gate.wait()
        return "too late"

    svc._handle_session_followup_message_async = slow_followup  # noqa: SLF001

    async def run() -> list:
        collect_task = asyncio.create_task(
            _collect_stream_events(
                svc,
                "show sources",
                session_id=created.id,
                request_id="req-cancel-followup",
                chunk_size=1000,
                chunk_delay_s=0,
            )
        )
        await asyncio.sleep(0.05)
        session_service.cancel_request(created.id, "req-cancel-followup")
        gate.set()
        return await collect_task

    events = asyncio.run(run())
    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code == "cancelled"
    assert error.message == CANCELLED_ASSISTANT_MESSAGE
    assert not any(isinstance(e, DoneEvent) for e in events)

    row = SessionStore(db_path).get_request(created.id, "req-cancel-followup")
    assert row is not None
    assert row.status == "cancelled"


def test_stream_events_history_failure_completes_failed_and_frees_session(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-history-failure.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()

    async def unused_runner(_: DigestRequest, *, session_id: str | None = None):
        raise AssertionError("digest runner must not run")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )

    def boom_history(_cmd):  # noqa: ANN001
        raise RuntimeError("boom-token")

    svc._handle_history_command = boom_history  # noqa: SLF001

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "search history for AI",
            session_id=created.id,
            request_id="req-history-fail",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code == "request_failed"
    assert error.message == "Request failed."
    assert "boom-token" not in error.message
    assert not any(isinstance(e, DoneEvent) for e in events)

    row = SessionStore(db_path).get_request(created.id, "req-history-fail")
    assert row is not None
    assert row.status == "failed"
    assert row.error_code == "request_failed"

    retry = session_service.begin_request(created.id, content="Next message")
    assert retry.status == "active"


def test_stream_events_followup_failure_completes_failed_and_frees_session(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-followup-failure.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()

    async def unused_runner(_: DigestRequest, *, session_id: str | None = None):
        raise AssertionError("digest runner must not run")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )

    async def boom_followup(
        session_id: str,
        message: str,
        **kwargs: object,
    ) -> str:
        del session_id, message, kwargs
        raise RuntimeError("boom-token")

    svc._handle_session_followup_message_async = boom_followup  # noqa: SLF001

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "show sources",
            session_id=created.id,
            request_id="req-followup-fail",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code == "request_failed"
    assert error.message == "Request failed."
    assert "boom-token" not in error.message
    assert not any(isinstance(e, DoneEvent) for e in events)

    row = SessionStore(db_path).get_request(created.id, "req-followup-fail")
    assert row is not None
    assert row.status == "failed"
    assert row.error_code == "request_failed"

    retry = session_service.begin_request(created.id, content="Next message")
    assert retry.status == "active"


def test_stream_events_unsaved_digest_completes_failed_not_succeeded(
    tmp_path: Path,
) -> None:
    from ai_news_agent.graph.state import WorkflowError

    db_path = tmp_path / "stream-unsaved-digest.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()
    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    digest = Digest(
        generated_at=now,
        entries=[],
        topics=["AI"],
        timeframe="today",
    )

    async def unsaved_runner(
        req: DigestRequest,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
    ):
        del req, session_id, request_id
        yield "Saving run…", False, None
        yield "", True, DigestResult(
            request=DigestRequest(topics=["AI"]),
            digest=digest,
            run_id=None,
            markdown="# Digest\n",
            text="# Digest\n",
            ranked_items=[],
            warnings=[],
            errors=[
                WorkflowError(
                    stage="store",
                    message="persistence failed: OperationalError",
                    detail="secret-token",
                )
            ],
            started_at=now,
            finished_at=now,
        )

    svc = ChatService(
        store=store,
        workflow_runner=lambda _: None,
        streaming_workflow_runner=unsaved_runner,
        session_service=session_service,
    )

    events = asyncio.run(
        _collect_stream_events(
            svc,
            "Give me today's AI digest",
            session_id=created.id,
            request_id="req-unsaved",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code == "workflow_error"
    assert "persistence failed" in error.message
    assert "secret-token" not in error.message
    assert not any(isinstance(e, DoneEvent) for e in events)
    assert not any(isinstance(e, DigestEvent) for e in events)
    assert not any(isinstance(e, DeltaEvent) for e in events)

    row = SessionStore(db_path).get_request(created.id, "req-unsaved")
    assert row is not None
    assert row.status == "failed"
    assert row.error_code == "workflow_error"
    assert row.error_message == error.message
    messages = SessionStore(db_path).list_messages(created.id)
    assistant = messages[-1]
    assert assistant.role == "assistant"
    assert assistant.content == error.message
    assert assistant.run_id is None


def test_stream_events_digest_passes_request_id_to_streaming_runner(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream-request-id.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()
    seen: dict[str, str | None] = {"request_id": None}

    async def fake_streaming_runner(
        req: DigestRequest,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
    ):
        del req
        seen["request_id"] = request_id
        assert session_id == created.id
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        yield "Collecting items…", False, None
        yield "", True, DigestResult(
            request=DigestRequest(topics=["AI"]),
            digest=None,
            run_id=None,
            markdown="ok",
            text="ok\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    svc = ChatService(
        store=store,
        workflow_runner=lambda _: None,
        streaming_workflow_runner=fake_streaming_runner,
        session_service=session_service,
    )

    asyncio.run(
        _collect_stream_events(
            svc,
            "Give me today's AI digest",
            session_id=created.id,
            request_id="req-pass-id",
            chunk_size=1000,
            chunk_delay_s=0,
        )
    )

    assert seen["request_id"] == "req-pass-id"


def test_stream_events_cancel_wins_at_completion_emits_cancelled_not_done(
    tmp_path: Path,
) -> None:
    from ai_news_agent.services.session_service import CANCELLED_ASSISTANT_MESSAGE

    db_path = tmp_path / "stream-complete-cancel-race.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()
    gate = asyncio.Event()

    async def unused_runner(_: DigestRequest, *, session_id: str | None = None):
        raise AssertionError("digest runner must not run")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )

    async def slow_followup(
        session_id: str,
        message: str,
        **kwargs: object,
    ) -> str:
        del session_id, message, kwargs
        await gate.wait()
        return "answer after cancel"

    svc._handle_session_followup_message_async = slow_followup  # noqa: SLF001

    async def run() -> list:
        collect_task = asyncio.create_task(
            _collect_stream_events(
                svc,
                "show sources",
                session_id=created.id,
                request_id="req-complete-race",
                chunk_size=1000,
                chunk_delay_s=0,
            )
        )
        await asyncio.sleep(0.05)
        session_service.cancel_request(created.id, "req-complete-race")
        gate.set()
        return await collect_task

    events = asyncio.run(run())
    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code == "cancelled"
    assert error.message == CANCELLED_ASSISTANT_MESSAGE
    assert not any(isinstance(e, DoneEvent) for e in events)


def test_stream_events_history_cancel_emits_cancelled_error(
    tmp_path: Path,
) -> None:
    from ai_news_agent.services.session_service import CANCELLED_ASSISTANT_MESSAGE

    db_path = tmp_path / "stream-history-cancel.db"
    store = DigestStore(db_path)
    store.init_schema()
    session_service = SessionService(SessionStore(db_path))
    created = session_service.create_session()
    gate = asyncio.Event()

    async def unused_runner(_: DigestRequest, *, session_id: str | None = None):
        raise AssertionError("digest runner must not run")

    svc = ChatService(
        store=store,
        workflow_runner=unused_runner,
        session_service=session_service,
    )
    original_stream = svc._stream_session_text_events

    async def gating_stream(**kwargs):  # noqa: ANN003
        await gate.wait()
        async for event in original_stream(**kwargs):
            yield event

    svc._stream_session_text_events = gating_stream  # noqa: SLF001

    async def run() -> list:
        collect_task = asyncio.create_task(
            _collect_stream_events(
                svc,
                "search history for AI",
                session_id=created.id,
                request_id="req-cancel-history",
                chunk_size=1000,
                chunk_delay_s=0,
            )
        )
        await asyncio.sleep(0.05)
        session_service.cancel_request(created.id, "req-cancel-history")
        gate.set()
        return await collect_task

    events = asyncio.run(run())
    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code == "cancelled"
    assert error.message == CANCELLED_ASSISTANT_MESSAGE
    assert not any(isinstance(e, DoneEvent) for e in events)

