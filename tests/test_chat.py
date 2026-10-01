"""Tests for follow-up chat service (Task T11)."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_news_agent.chat import ChatService
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
from ai_news_agent.connectors.base import ConnectorRequest, ConnectorResult
from ai_news_agent.graph.state import DigestResult
from ai_news_agent.followup_structured import NO_SAVED_DIGEST
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


class _FakeInterfaceRouter:
    def __init__(
        self,
        *,
        result: InterfaceAgentResult | None = None,
        stream_events: list[tuple[str, bool, InterfaceAgentResult | None]] | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result or InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="unused",
        )
        self._stream_events = stream_events

    async def route(
        self,
        *,
        message: str,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
        correlation_id: str | None = None,
    ) -> InterfaceAgentResult:
        self.calls.append(
            {
                "message": message,
                "digest_request": digest_request,
                "session_connector_names": session_connector_names,
                "session_items_per_source": session_items_per_source,
                "correlation_id": correlation_id,
            }
        )
        return self._result

    async def route_streaming(
        self,
        *,
        message: str,
        digest_request: DigestRequest | None = None,
        session_connector_names: list[str] | None = None,
        session_items_per_source: int | None = None,
        correlation_id: str | None = None,
    ):
        self.calls.append(
            {
                "message": message,
                "digest_request": digest_request,
                "session_connector_names": session_connector_names,
                "session_items_per_source": session_items_per_source,
                "correlation_id": correlation_id,
                "streaming": True,
            }
        )
        if self._stream_events is not None:
            for event in self._stream_events:
                yield event
            return
        yield "", True, self._result


def test_chat_with_interface_router_routes_digest_through_router(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow_runner should not be called directly by ChatService")

    store = DigestStore(tmp_path / "router-digest.db")
    store.init_schema()
    incoming = DigestRequest(topics=["RAG"])
    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.DIGEST,
            text="digest text",
            run_id=7,
        )
    )
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        interface_router=router,
    )

    reply = asyncio.run(
        svc.handle_message_async("ignored message body", digest_request=incoming)
    )

    assert reply == "digest text"
    assert len(router.calls) == 1
    assert router.calls[0]["digest_request"] is incoming
    assert router.calls[0]["message"] == "ignored message body"


def test_chat_maps_interface_digest_result_with_warnings_notice(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow_runner should not be called")

    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    digest = Digest(
        generated_at=now,
        entries=[],
        topics=["RAG"],
        timeframe=None,
    )
    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.DIGEST,
            text="digest body",
            run_id=7,
            digest=digest,
        )
    )
    store = DigestStore(tmp_path / "router-warnings.db")
    store.init_schema()
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        interface_router=router,
    )

    import ai_news_agent.services.chat as services_chat

    monkeypatch.setattr(
        services_chat,
        "format_connector_warnings_notice",
        lambda _warnings, _errors: "Notice:",
    )

    reply = asyncio.run(
        svc.handle_message_async("digest please", digest_request=DigestRequest(topics=["RAG"]))
    )

    assert reply == "Notice:\n\ndigest body"


def test_chat_with_interface_router_routes_structured_followup_through_router(
    tmp_path,
) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "router-structured.db")
    store.init_schema()
    _save_minimal_digest(store)

    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.STRUCTURED,
            text="Sources: https://example.com/r1",
            run_id=1,
        )
    )
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        interface_router=router,
    )

    import ai_news_agent.services.chat as services_chat

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            services_chat,
            "answer_structured_followup",
            lambda _message, _ctx: (_ for _ in ()).throw(
                AssertionError("answer_structured_followup must not be called")
            ),
        )
        reply = asyncio.run(svc.handle_message_async("show sources"))

    assert reply == "Sources: https://example.com/r1"
    assert len(router.calls) == 1
    assert router.calls[0]["message"] == "show sources"


def test_chat_with_interface_router_routes_open_ended_followup_through_router(
    tmp_path,
) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "router-open.db")
    store.init_schema()
    _save_minimal_digest(store)

    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="answer",
        )
    )
    runner = _FakeToolAgentRunner()
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        tool_agent_runner=runner,
        interface_router=router,
    )

    reply = asyncio.run(svc.handle_message_async("what trends do you see?"))

    assert reply == "answer"
    assert runner.calls == []
    assert len(router.calls) == 1


def test_chat_with_interface_router_no_saved_digest_returns_router_text(tmp_path) -> None:
    from ai_news_agent.followup_structured import NO_SAVED_DIGEST

    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "router-no-digest.db")
    store.init_schema()
    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text=NO_SAVED_DIGEST,
        )
    )
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        interface_router=router,
    )

    reply = asyncio.run(svc.handle_message_async("show sources"))

    assert reply == NO_SAVED_DIGEST
    assert len(router.calls) == 1


def test_chat_streaming_via_interface_router_yields_progress_then_chunked_text(
    tmp_path,
) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "router-stream.db")
    store.init_schema()
    router = _FakeInterfaceRouter(
        stream_events=[
            ("Calling generate_ai_news_digest…", False, None),
            (
                "",
                True,
                InterfaceAgentResult(
                    kind=InterfaceAgentResultKind.DIGEST,
                    text="1234567890",
                    run_id=7,
                ),
            ),
        ]
    )
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        interface_router=router,
    )

    chunks = asyncio.run(
        _collect_streaming(
            svc,
            "Generate digest.",
            digest_request=DigestRequest(topics=["AI"]),
            chunk_size=4,
            chunk_delay_s=0,
        )
    )

    assert chunks[0] == "Calling generate_ai_news_digest…"
    assert chunks[-1] == "1234567890"
    assert len(chunks) > 2
    assert "Calling" not in chunks[-1]


def test_chat_routes_explicit_digest_request_through_workflow_runner(tmp_path) -> None:
    captured: list[DigestRequest] = []

    async def fake_runner(req: DigestRequest) -> DigestResult:
        captured.append(req)
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        dr = DigestRequest(topics=["x"])
        return DigestResult(
            request=dr,
            digest=None,
            run_id=None,
            markdown="# md\n",
            text="digest-text-output\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "c.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    incoming = DigestRequest(topics=["RAG"])
    reply = asyncio.run(
        svc.handle_message_async(
            "ignored message body",
            digest_request=incoming,
        )
    )

    assert reply == "digest-text-output\n"
    assert len(captured) == 1
    assert captured[0] is incoming


def test_chat_follow_up_without_saved_digest_returns_guidance(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run for generic follow-up")

    store = DigestStore(tmp_path / "empty.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    reply = asyncio.run(svc.handle_message_async("What does item 2 mean?"))

    assert "No saved digest" in reply


def test_chat_structured_sources_lists_digest_urls(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    item = NewsItem(
        source=SourceKind.GITHUB,
        source_id="r1",
        url="https://example.com/r1",
        title="Repo",
        collected_at=now,
    )
    digest = Digest(
        generated_at=now,
        entries=[
            DigestEntry(
                source_kind=SourceKind.GITHUB,
                source_id="r1",
                title="Repo",
                source_name="GitHub",
                source_url=item.url,
                summary="S",
                why_it_matters="W",
                background_knowledge="B",
                follow_up_action=FollowUpAction.READ,
            )
        ],
        topics=["RAG"],
        timeframe=None,
    )

    store = DigestStore(tmp_path / "ctx.db")
    store.init_schema()
    run_id = store.save_run(
        requested_at=now,
        timeframe=None,
        topics=["RAG"],
        connector_names=["github"],
    )
    store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[]))
    store.save_ranked_items(run_id, [])
    store.save_digest(run_id, digest)

    svc = ChatService(store=store, workflow_runner=fake_runner)
    reply = asyncio.run(svc.handle_message_async("Please show sources"))

    assert "https://example.com/r1" in reply
    assert "Repo" in reply


def test_chat_structured_rank_item_returns_entry_detail(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    item = NewsItem(
        source=SourceKind.GITHUB,
        source_id="r1",
        url="https://example.com/r1",
        title="Repo",
        collected_at=now,
    )
    digest = Digest(
        generated_at=now,
        entries=[
            DigestEntry(
                source_kind=SourceKind.GITHUB,
                source_id="r1",
                title="Repo",
                source_name="GitHub",
                source_url=item.url,
                summary="Digest summary",
                why_it_matters="Because it matters",
                background_knowledge="Background",
                follow_up_action=FollowUpAction.READ,
            )
        ],
        topics=["RAG"],
        timeframe=None,
    )

    store = DigestStore(tmp_path / "rank-item.db")
    store.init_schema()
    run_id = store.save_run(
        requested_at=now,
        timeframe=None,
        topics=["RAG"],
        connector_names=["github"],
    )
    store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[]))
    store.save_ranked_items(run_id, [])
    store.save_digest(run_id, digest)

    svc = ChatService(store=store, workflow_runner=fake_runner)
    reply = asyncio.run(svc.handle_message_async("follow up on item 1"))

    assert "Digest item 1: Repo" in reply
    assert "Digest summary" in reply
    assert "Because it matters" in reply


def test_chat_structured_ranking_recommends_top_selected(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    low = NewsItem(
        source=SourceKind.GITHUB,
        source_id="low",
        url="https://example.com/low",
        title="Low",
        collected_at=now,
    )
    high = NewsItem(
        source=SourceKind.GITHUB,
        source_id="high",
        url="https://example.com/high",
        title="High",
        collected_at=now,
    )
    digest = Digest(generated_at=now, entries=[], topics=["RAG"], timeframe=None)

    store = DigestStore(tmp_path / "rank.db")
    store.init_schema()
    run_id = store.save_run(
        requested_at=now,
        timeframe=None,
        topics=["RAG"],
        connector_names=["github"],
    )
    store.save_connector_result(
        run_id,
        ConnectorResult(items=[low, high], warnings=[]),
    )
    ranked = [
        RankedItem(
            item=low,
            score_total=1.0,
            selected=False,
            selection_reason="skip",
        ),
        RankedItem(
            item=high,
            score_total=9.0,
            selected=True,
            selection_reason="best engagement",
        ),
    ]
    store.save_ranked_items(run_id, ranked)
    store.save_digest(run_id, digest)

    svc = ChatService(store=store, workflow_runner=fake_runner)
    reply = asyncio.run(svc.handle_message_async("Which item should I study first?"))

    assert "High" in reply
    assert "https://example.com/high" in reply
    assert "best engagement" in reply


def test_chat_structured_caveats_lists_warnings_and_entry_notes(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    item = NewsItem(
        source=SourceKind.GITHUB,
        source_id="r1",
        url="https://example.com/r1",
        title="Repo",
        collected_at=now,
    )
    w = ConnectorWarning(connector="github", code="rate", message="slow")
    digest = Digest(
        generated_at=now,
        entries=[
            DigestEntry(
                source_kind=SourceKind.GITHUB,
                source_id="r1",
                title="Repo",
                source_name="GitHub",
                source_url=item.url,
                summary="S",
                why_it_matters="W",
                background_knowledge="B",
                follow_up_action=FollowUpAction.READ,
                confidence_caveat="Metadata only",
            )
        ],
        topics=["RAG"],
        timeframe=None,
    )

    store = DigestStore(tmp_path / "warn.db")
    store.init_schema()
    run_id = store.save_run(
        requested_at=now,
        timeframe=None,
        topics=["RAG"],
        connector_names=["github"],
    )
    store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[w]))
    store.save_ranked_items(run_id, [])
    store.save_digest(run_id, digest)

    svc = ChatService(store=store, workflow_runner=fake_runner)
    reply = asyncio.run(svc.handle_message_async("Any confidence caveats?"))

    assert "rate" in reply
    assert "Metadata only" in reply


class _FakeFollowUpModel:
    def generate_followup_reply(self, *, question: str, grounding: dict) -> str:
        assert "digest" in grounding
        assert grounding["digest"]["topics"] == ["RAG"]
        return f"ECHO:{question.strip()}"


def test_chat_open_ended_uses_llm_when_model_configured(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    item = NewsItem(
        source=SourceKind.GITHUB,
        source_id="r1",
        url="https://example.com/r1",
        title="Repo",
        collected_at=now,
    )
    digest = Digest(
        generated_at=now,
        entries=[
            DigestEntry(
                source_kind=SourceKind.GITHUB,
                source_id="r1",
                title="Repo",
                source_name="GitHub",
                source_url=item.url,
                summary="S",
                why_it_matters="W",
                background_knowledge="B",
                follow_up_action=FollowUpAction.READ,
            )
        ],
        topics=["RAG"],
        timeframe=None,
    )

    store = DigestStore(tmp_path / "llm.db")
    store.init_schema()
    run_id = store.save_run(
        requested_at=now,
        timeframe=None,
        topics=["RAG"],
        connector_names=["github"],
    )
    store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[]))
    store.save_ranked_items(run_id, [])
    store.save_digest(run_id, digest)

    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        chat_model=_FakeFollowUpModel(),
    )
    reply = asyncio.run(svc.handle_message_async("Why does this repo matter?"))

    assert reply == "ECHO:Why does this repo matter?"


def test_chat_open_ended_without_model_returns_fallback(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    item = NewsItem(
        source=SourceKind.GITHUB,
        source_id="r1",
        url="https://example.com/r1",
        title="Repo",
        collected_at=now,
    )
    digest = Digest(
        generated_at=now,
        entries=[
            DigestEntry(
                source_kind=SourceKind.GITHUB,
                source_id="r1",
                title="Repo",
                source_name="GitHub",
                source_url=item.url,
                summary="S",
                why_it_matters="W",
                background_knowledge="B",
                follow_up_action=FollowUpAction.READ,
            )
        ],
        topics=["RAG"],
        timeframe=None,
    )

    store = DigestStore(tmp_path / "nofm.db")
    store.init_schema()
    run_id = store.save_run(
        requested_at=now,
        timeframe=None,
        topics=["RAG"],
        connector_names=["github"],
    )
    store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[]))
    store.save_ranked_items(run_id, [])
    store.save_digest(run_id, digest)

    svc = ChatService(store=store, workflow_runner=fake_runner, chat_model=None)
    reply = asyncio.run(svc.handle_message_async("Explain the tradeoffs abstractly"))

    assert "language model" in reply.lower()


def test_chat_digest_with_url_passes_parsed_request(tmp_path) -> None:
    captured: list[DigestRequest] = []

    async def fake_runner(req: DigestRequest) -> DigestResult:
        captured.append(req)
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="ok\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "intent.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    msg = "Digest https://github.com/acme/widget"
    reply = asyncio.run(svc.handle_message_async(msg))

    assert reply == "ok\n"
    assert len(captured) == 1
    assert captured[0].topics == []
    assert any("acme/widget" in u for u in captured[0].github_manual_urls)
    assert captured[0].github_target_channels == []


def test_chat_digest_single_github_repo_url_stays_focused(tmp_path) -> None:
    captured: list[DigestRequest] = []

    async def fake_runner(req: DigestRequest) -> DigestResult:
        captured.append(req)
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="ok\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "gh-repo.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    msg = "Digest https://github.com/langchain-ai/langgraph"
    asyncio.run(svc.handle_message_async(msg))

    assert len(captured) == 1
    assert captured[0].topics == []
    assert any("langchain-ai/langgraph" in u for u in captured[0].github_manual_urls)
    assert captured[0].github_target_channels == []


@pytest.mark.parametrize(
    "message",
    [
        "Show Hugging Face trending models",
        "huggingface trending models",
        "trending repos",
        "Find Zhihu practitioner insights on RAG",
    ],
)
def test_message_requests_digest_true_for_source_browse_phrases(message: str) -> None:
    from ai_news_agent.services.chat import _message_requests_digest

    assert _message_requests_digest(message) is True


def test_chat_message_digest_keyword_triggers_workflow(tmp_path) -> None:
    seen: list[DigestRequest] = []

    async def fake_runner(req: DigestRequest) -> DigestResult:
        seen.append(req)
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="from-workflow\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "trig.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    reply = asyncio.run(svc.handle_message_async("Give me today's AI digest"))

    assert reply == "from-workflow\n"
    assert len(seen) == 1


def test_chat_session_source_toggles_apply_connector_names(tmp_path) -> None:
    captured: list[DigestRequest] = []

    async def fake_runner(req: DigestRequest) -> DigestResult:
        captured.append(req)
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="ok\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "session.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    asyncio.run(
        svc.handle_message_async(
            "Give me today's AI digest",
            session_connector_names=["github"],
        )
    )

    assert captured[0].connector_names == ["github"]


def test_chat_session_items_per_source_applies_to_digest_request(tmp_path) -> None:
    captured: list[DigestRequest] = []

    async def fake_runner(req: DigestRequest) -> DigestResult:
        captured.append(req)
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="ok\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "items-per-source.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    asyncio.run(
        svc.handle_message_async(
            "Give me today's AI digest",
            session_connector_names=["juya", "huggingface"],
            session_items_per_source=5,
        )
    )

    req = captured[0]
    assert req.connector_names == ["juya", "huggingface"]
    assert req.items_per_source == 5
    assert req.max_items_per_source >= 5


def test_chat_nl_source_phrase_overrides_session_toggles(tmp_path) -> None:
    captured: list[DigestRequest] = []

    async def fake_runner(req: DigestRequest) -> DigestResult:
        captured.append(req)
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="ok\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "override.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    asyncio.run(
        svc.handle_message_async(
            "Give me today's AI digest from bilibili only",
            session_connector_names=["github"],
        )
    )

    assert captured[0].connector_names == ["bilibili"]


async def _collect_streaming(service: ChatService, message: str, **kwargs) -> list[str]:  # noqa: ANN003
    chunks: list[str] = []
    async for chunk in service.handle_message_streaming_async(message, **kwargs):
        chunks.append(chunk)
    return chunks


class _DigestStreamFakeConnector:
    def __init__(self, *, name: str, items: list[NewsItem]) -> None:
        self._name = name
        self._items = items

    def name(self) -> str:
        return self._name

    async def collect(self, _request: ConnectorRequest) -> ConnectorResult:
        return ConnectorResult(items=list(self._items), warnings=[])


class _DigestStreamFakeModel:
    def generate_entry_fields(self, context: dict) -> dict:  # noqa: ARG002
        return {
            "summary": "Test summary",
            "why_it_matters": "Because",
            "background_knowledge": "Bg",
            "follow_up_action": "read",
        }


def _digest_stream_news_item(source_id: str) -> NewsItem:
    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    return NewsItem(
        source=SourceKind.GITHUB,
        source_id=source_id,
        url=f"https://example.com/{source_id}",
        title=f"item-{source_id}",
        collected_at=now,
    )


def test_chat_digest_stream_each_progress_is_single_stage_not_cumulative(
    tmp_path,
) -> None:
    from ai_news_agent.graph.workflow import run_digest_streaming

    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    req = DigestRequest(topics=["RAG"])
    store = DigestStore(tmp_path / "digest-stream-ephemeral.db")
    store.init_schema()
    connectors = [
        _DigestStreamFakeConnector(
            name="github",
            items=[_digest_stream_news_item("r1")],
        )
    ]

    async def collect_progress() -> list[str]:
        lines: list[str] = []
        async for progress, done, _result in run_digest_streaming(
            req,
            connectors=connectors,
            model=_DigestStreamFakeModel(),
            store=store,
            now_provider=lambda: now,
        ):
            if not done and progress:
                lines.append(progress)
        return lines

    progress_lines = asyncio.run(collect_progress())

    assert progress_lines
    for line in progress_lines:
        assert "\n" not in line
    assert progress_lines[0] == "Parsing request…"
    assert "Parsing request" not in progress_lines[-1]


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


def test_chat_digest_sync_includes_anti_bot_warning(tmp_path) -> None:
    warning = _bilibili_anti_bot_warning()

    async def fake_runner(req: DigestRequest) -> DigestResult:
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="digest-body\n",
            ranked_items=[],
            warnings=[warning],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "anti-bot-sync.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    reply = asyncio.run(
        svc.handle_message_async(
            "ignored",
            digest_request=DigestRequest(topics=["AI"]),
        )
    )

    assert "BILIBILI_SESSDATA" in reply
    assert "digest-body" in reply
    assert reply.index("BILIBILI_SESSDATA") < reply.index("digest-body")


def test_chat_digest_streaming_includes_anti_bot_warning(tmp_path) -> None:
    warning = _bilibili_anti_bot_warning()
    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)

    async def fake_streaming_runner(req: DigestRequest):
        yield "Collecting…", False, None
        yield "", True, DigestResult(
            request=req,
            digest=None,
            run_id=1,
            markdown="",
            text="digest-body",
            ranked_items=[],
            warnings=[warning],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    async def fake_runner(_req: DigestRequest) -> DigestResult:
        raise AssertionError("sync runner should not be used")

    store = DigestStore(tmp_path / "anti-bot-stream.db")
    store.init_schema()
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        streaming_workflow_runner=fake_streaming_runner,
    )

    chunks = asyncio.run(
        _collect_streaming(
            svc,
            "Give me today's AI digest",
            chunk_size=80,
            chunk_delay_s=0,
        )
    )

    full = "".join(chunks)
    assert "BILIBILI_SESSDATA" in full
    assert "digest-body" in full
    assert full.index("BILIBILI_SESSDATA") < full.index("digest-body")


def test_chat_digest_warning_banner_absent_without_warnings(tmp_path) -> None:
    async def fake_runner(req: DigestRequest) -> DigestResult:
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="digest-body\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "no-warning-banner.db")
    store.init_schema()
    svc = ChatService(store=store, workflow_runner=fake_runner)

    reply = asyncio.run(
        svc.handle_message_async(
            "ignored",
            digest_request=DigestRequest(topics=["AI"]),
        )
    )

    assert reply == "digest-body\n"
    assert "BILIBILI_SESSDATA" not in reply


def test_chat_streaming_digest_yields_progress_then_chunks(tmp_path) -> None:
    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)

    async def fake_streaming_runner(req: DigestRequest):
        yield "Parsing request…", False, None
        yield "", True, DigestResult(
            request=req,
            digest=None,
            run_id=1,
            markdown="",
            text="ABCDEFGHIJ",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    async def fake_runner(_req: DigestRequest) -> DigestResult:
        raise AssertionError("workflow runner should not be used")

    store = DigestStore(tmp_path / "stream-chat.db")
    store.init_schema()
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        streaming_workflow_runner=fake_streaming_runner,
    )

    chunks = asyncio.run(
        _collect_streaming(
            svc,
            "Give me today's AI digest",
            chunk_size=4,
            chunk_delay_s=0,
        )
    )

    assert chunks[0] == "Parsing request…"
    assert chunks[-1] == "ABCDEFGHIJ"
    assert "Parsing request" not in chunks[-1]
    assert len(chunks) > 2


def test_chat_streaming_follow_up_yields_multiple_chunks(tmp_path) -> None:
    async def fake_runner(_req: DigestRequest) -> DigestResult:
        raise AssertionError("workflow runner should not be used")

    store = DigestStore(tmp_path / "stream-follow.db")
    store.init_schema()
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
    )

    chunks = asyncio.run(
        _collect_streaming(
            svc,
            "What does item 2 mean?",
            chunk_size=10,
            chunk_delay_s=0,
        )
    )

    assert len(chunks) >= 2
    assert chunks[-1].startswith("No saved digest")


class _FakeToolAgentRunner:
    def __init__(self, reply: str = "AGENT_SAYS") -> None:
        self.calls: list[str] = []
        self._reply = reply

    async def run(self, question: str) -> str:
        self.calls.append(question)
        return self._reply


class _StreamingFakeToolAgentRunner(_FakeToolAgentRunner):
    async def run_streaming(self, question: str):  # noqa: ANN201
        self.calls.append(question)
        yield "Calling load_latest_digest…", False, None
        yield "Done load_latest_digest: Loaded digest with 1 entry.", False, None
        yield "", True, self._reply


def test_chat_tool_agent_runner_accepted_as_constructor_arg(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "tool-agent-init.db")
    store.init_schema()
    runner = _FakeToolAgentRunner()

    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        tool_agent_runner=runner,
    )

    assert svc is not None


def _save_minimal_digest(store: DigestStore, *, db_name: str = "ctx") -> None:
    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    item = NewsItem(
        source=SourceKind.GITHUB,
        source_id="r1",
        url="https://example.com/r1",
        title="Repo",
        collected_at=now,
    )
    digest = Digest(
        generated_at=now,
        entries=[
            DigestEntry(
                source_kind=SourceKind.GITHUB,
                source_id="r1",
                title="Repo",
                source_name="GitHub",
                source_url=item.url,
                summary="S",
                why_it_matters="W",
                background_knowledge="B",
                follow_up_action=FollowUpAction.READ,
            )
        ],
        topics=["RAG"],
        timeframe=None,
    )
    run_id = store.save_run(
        requested_at=now,
        timeframe=None,
        topics=["RAG"],
        connector_names=["github"],
    )
    store.save_connector_result(run_id, ConnectorResult(items=[item], warnings=[]))
    store.save_ranked_items(run_id, [])
    store.save_digest(run_id, digest)


def test_chat_open_ended_follow_up_routes_to_tool_agent_when_configured(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "tool-agent-route.db")
    store.init_schema()
    _save_minimal_digest(store)

    runner = _FakeToolAgentRunner(reply="Grounded tool answer.")
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        tool_agent_runner=runner,
    )

    question = "Why does this repo matter?"
    reply = asyncio.run(svc.handle_message_async(question))

    assert runner.calls == [question]
    assert reply == "Grounded tool answer."


class _InterfaceResultToolAgentRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, question: str) -> InterfaceAgentResult:
        self.calls.append(question)
        return InterfaceAgentResult(
            kind=InterfaceAgentResultKind.STRUCTURED,
            text="Grounded answer",
        )


def test_chat_tool_agent_runner_interface_result_normalized_to_text(
    tmp_path: Path,
) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "tool-agent-interface-result.db")
    store.init_schema()
    _save_minimal_digest(store)

    runner = _InterfaceResultToolAgentRunner()
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        tool_agent_runner=runner,
    )

    question = "Why does this matter?"
    reply = asyncio.run(svc.handle_message_async(question))

    assert runner.calls == [question]
    assert reply == "Grounded answer"
    assert isinstance(reply, str)


def test_chat_streaming_follow_up_uses_tool_agent_when_configured(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "tool-agent-stream.db")
    store.init_schema()
    _save_minimal_digest(store)

    runner = _FakeToolAgentRunner(reply="Streaming tool answer.")
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        tool_agent_runner=runner,
    )

    question = "Explain the tradeoffs abstractly"
    chunks = asyncio.run(
        _collect_streaming(
            svc,
            question,
            chunk_size=10,
            chunk_delay_s=0,
        )
    )

    assert runner.calls == [question]
    assert chunks[-1] == "Streaming tool answer."


def test_chat_streaming_follow_up_emits_tool_progress_then_ephemeral_final_answer(
    tmp_path,
) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "tool-agent-stream-ephemeral.db")
    store.init_schema()
    _save_minimal_digest(store)

    runner = _StreamingFakeToolAgentRunner(reply="Final grounded answer only.")
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        tool_agent_runner=runner,
    )

    question = "Why does this repo matter?"
    chunks = asyncio.run(
        _collect_streaming(
            svc,
            question,
            chunk_size=12,
            chunk_delay_s=0,
        )
    )

    assert runner.calls == [question]
    assert any("Calling load_latest_digest" in chunk for chunk in chunks)
    assert chunks[-1] == "Final grounded answer only."
    assert "Calling" not in chunks[-1]
    assert "Done load_latest_digest" not in chunks[-1]


def test_chat_tool_agent_not_called_for_structured_followup(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow should not run")

    store = DigestStore(tmp_path / "tool-agent-structured.db")
    store.init_schema()
    _save_minimal_digest(store)

    runner = _FakeToolAgentRunner()
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        tool_agent_runner=runner,
    )

    reply = asyncio.run(svc.handle_message_async("Please show sources"))

    assert "https://example.com/r1" in reply
    assert runner.calls == []


def test_chat_tool_agent_not_called_for_digest_request(tmp_path) -> None:
    captured: list[DigestRequest] = []

    async def fake_runner(req: DigestRequest) -> DigestResult:
        captured.append(req)
        now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        return DigestResult(
            request=req,
            digest=None,
            run_id=None,
            markdown="",
            text="from-workflow\n",
            ranked_items=[],
            warnings=[],
            errors=[],
            started_at=now,
            finished_at=now,
        )

    store = DigestStore(tmp_path / "tool-agent-digest.db")
    store.init_schema()
    runner = _FakeToolAgentRunner()
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        tool_agent_runner=runner,
    )

    reply = asyncio.run(svc.handle_message_async("Give me today's AI digest"))

    assert reply == "from-workflow\n"
    assert len(captured) == 1
    assert runner.calls == []


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


def test_history_intercept_stub_raises_even_with_fake_router(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow_runner should not be called for history intercept stub")

    store = DigestStore(tmp_path / "history-stub.db")
    store.init_schema()
    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="router should not run",
        )
    )
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        interface_router=router,
    )

    reply = asyncio.run(svc.handle_message_async("search history for rag"))
    assert "No saved digests to search." in reply
    assert router.calls == []


_HISTORY_FIXTURE_DT = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)


def _seed_history_github_digest(store: DigestStore) -> int:
    item = NewsItem(
        source=SourceKind.GITHUB,
        source_id="repo-1",
        url="https://github.com/a/b",
        title="a/b",
        collected_at=_HISTORY_FIXTURE_DT,
        content_confidence=ConfidenceLevel.HIGH,
    )
    entry = DigestEntry(
        source_kind=SourceKind.GITHUB,
        source_id="repo-1",
        title="a/b",
        source_name="GitHub",
        source_url=item.url,
        summary="Summary about transformers",
        why_it_matters="Why",
        background_knowledge="Background",
        follow_up_action=FollowUpAction.READ,
    )
    run_id = store.save_run(
        requested_at=_HISTORY_FIXTURE_DT,
        timeframe="today",
        topics=["RAG"],
        connector_names=["github"],
    )
    store.save_connector_result(
        run_id,
        ConnectorResult(items=[item], warnings=[], raw_count=1),
    )
    store.save_ranked_items(
        run_id,
        [RankedItem(item=item, score_total=1.0, selected=True, selection_reason="best")],
    )
    return store.save_digest(
        run_id,
        Digest(
            generated_at=_HISTORY_FIXTURE_DT,
            entries=[entry],
            topics=["RAG"],
            timeframe="today",
        ),
    )


def test_history_search_intercept_before_router(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow_runner should not be called")

    store = DigestStore(tmp_path / "history-search.db")
    store.init_schema()
    digest_id = _seed_history_github_digest(store)
    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="router should not run",
        )
    )
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        interface_router=router,
    )

    reply = asyncio.run(svc.handle_message_async("search history for transformer"))
    assert f"d{digest_id}:r1" in reply
    assert "a/b" in reply
    assert router.calls == []

    routed = asyncio.run(svc.handle_message_async("show sources"))
    assert routed == "router should not run"
    assert len(router.calls) == 1


def test_history_open_intercept_before_router(tmp_path) -> None:
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow_runner should not be called")

    store = DigestStore(tmp_path / "history-open.db")
    store.init_schema()
    digest_id = _seed_history_github_digest(store)
    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="router should not run",
        )
    )
    svc = ChatService(
        store=store,
        workflow_runner=fake_runner,
        interface_router=router,
    )

    reply = asyncio.run(svc.handle_message_async(f"open history d{digest_id}:r1"))
    assert reply.startswith("Digest item 1: a/b")
    assert router.calls == []


def test_history_open_not_found_not_no_saved_digest(tmp_path) -> None:
    store = DigestStore(tmp_path / "history-open-miss.db")
    store.init_schema()
    _seed_history_github_digest(store)
    router = _FakeInterfaceRouter()
    svc = ChatService(
        store=store,
        workflow_runner=_unused_runner(),
        interface_router=router,
    )

    reply = asyncio.run(svc.handle_message_async("open history d9999:r1"))
    assert reply == "not found"
    assert NO_SAVED_DIGEST not in reply
    assert router.calls == []


def test_history_validation_errors_before_router(tmp_path) -> None:
    store = DigestStore(tmp_path / "history-validation.db")
    store.init_schema()
    router = _FakeInterfaceRouter()
    svc = ChatService(
        store=store,
        workflow_runner=_unused_runner(),
        interface_router=router,
    )

    bare = asyncio.run(svc.handle_message_async("search history"))
    assert "at least one search criterion" in bare
    assert NO_SAVED_DIGEST not in bare
    assert router.calls == []

    bad_source = asyncio.run(
        svc.handle_message_async("search history from arxiv")
    )
    assert "Unknown source" in bad_source
    assert NO_SAVED_DIGEST not in bad_source
    assert router.calls == []


def _unused_runner():
    async def fake_runner(_: DigestRequest) -> DigestResult:
        raise AssertionError("workflow_runner should not be called")

    return fake_runner


def test_history_streaming_search_before_router(tmp_path) -> None:
    store = DigestStore(tmp_path / "history-stream-search.db")
    store.init_schema()
    digest_id = _seed_history_github_digest(store)
    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="router should not run",
        ),
        stream_events=[("", True, InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="router should not run",
        ))],
    )
    svc = ChatService(
        store=store,
        workflow_runner=_unused_runner(),
        interface_router=router,
    )

    chunks = asyncio.run(
        _collect_streaming(svc, "search history for transformer")
    )
    joined = "".join(chunks)
    assert f"d{digest_id}:r1" in joined
    assert router.calls == []


def test_history_streaming_open_before_router(tmp_path) -> None:
    store = DigestStore(tmp_path / "history-stream-open.db")
    store.init_schema()
    digest_id = _seed_history_github_digest(store)
    router = _FakeInterfaceRouter()
    svc = ChatService(
        store=store,
        workflow_runner=_unused_runner(),
        interface_router=router,
    )

    chunks = asyncio.run(
        _collect_streaming(svc, f"open history d{digest_id}:r1")
    )
    joined = "".join(chunks)
    assert "Digest item 1: a/b" in joined
    assert router.calls == []


def test_non_history_streaming_still_routes_through_router(tmp_path) -> None:
    store = DigestStore(tmp_path / "history-stream-route.db")
    store.init_schema()
    router = _FakeInterfaceRouter(
        result=InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="stream routed",
        ),
        stream_events=[("", True, InterfaceAgentResult(
            kind=InterfaceAgentResultKind.CONVERSATIONAL,
            text="stream routed",
        ))],
    )
    svc = ChatService(
        store=store,
        workflow_runner=_unused_runner(),
        interface_router=router,
    )

    chunks = asyncio.run(_collect_streaming(svc, "what trends do you see?"))
    assert "".join(chunks) == "stream routed"
    assert len(router.calls) == 1


def test_services_chat_surface_importable() -> None:
    from ai_news_agent.chat import ChatService as ReexportedChatService
    from ai_news_agent.services.chat import (
        ChatService,
        DeltaEvent,
        DigestEvent,
        DoneEvent,
        ErrorEvent,
        ProgressEvent,
        StartedEvent,
    )

    assert ReexportedChatService is ChatService
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
    ):
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
            "list sources again",
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
            "ignored",
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

    async def slow_followup(session_id: str, message: str) -> str:
        del session_id, message
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

