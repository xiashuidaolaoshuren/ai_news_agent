"""Follow-up chat service and typed session event stream (8A.1 T10)."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

from ai_news_agent.graph.state import DigestResult, WorkflowError
from ai_news_agent.models import ConnectorWarning, Digest, SourceKind
from ai_news_agent.logging_setup import get_logger
from ai_news_agent.followup_structured import (
    NO_SAVED_DIGEST,
    answer_structured_followup,
    answer_targeted_deep_dive,
    build_targeted_card,
)
from ai_news_agent.juya_followup import (
    is_juya_news_item,
    is_juya_story_item,
    match_news_item_for_digest_entry,
    parse_juya_sub_news,
)
from ai_news_agent.history_interface import (
    HISTORY_NOT_FOUND,
    HistoryChatCommand,
    format_history_search_text,
    parse_history_chat_message,
)
from ai_news_agent.history_search import search_digest_history, show_historical_item
from ai_news_agent.rendering import format_connector_warnings_notice
from ai_news_agent.request import DigestRequest
from ai_news_agent.services.conversation import (
    ConversationContext,
    ConversationDecision,
    interpret_message,
    is_self_contained_request,
    request_from_payload,
    request_metadata,
    request_payload,
)
from ai_news_agent.services.session_records import SessionRequestRecord
from ai_news_agent.services.session_service import (
    CANCELLED_ASSISTANT_MESSAGE,
    SessionService,
    resolve_session_entry,
)
from ai_news_agent.connectors.base import ConnectorRequest
from ai_news_agent.source_settings import (
    SourceSettingsService,
    finalize_public_counts,
    juya_all_confirmation,
)
from ai_news_agent.storage import DigestStore, FollowupContext
from ai_news_agent.streaming import iter_text_chunks
from ai_news_agent.tools.schemas import (
    InterfaceAgentResult,
    InterfaceAgentResultKind,
)

WorkflowRunner = Callable[[DigestRequest], Awaitable[DigestResult]]
StreamingWorkflowRunner = Callable[
    [DigestRequest],
    AsyncIterator[tuple[str, bool, DigestResult | None]],
]

logger = get_logger("chat")

_TARGETED_ASK_UNAVAILABLE = "Question-specific answering is unavailable."
_LLM_UNCONFIGURED_MESSAGE = (
    "Configure an LLM in Settings (API key) to generate digests."
)

_TERMINAL_REPLAY_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)
_WORKFLOW_ERROR_CODE = "workflow_error"
_WORKFLOW_ERROR_MESSAGE = "Digest generation failed."
_REQUEST_FAILED_CODE = "request_failed"
_REQUEST_FAILED_MESSAGE = "Request failed."
_CLARIFY_FALLBACK = (
    "Tell me whether you want recent signals on that topic or a general explanation."
)
_GENERAL_KNOWLEDGE_LABEL = "*General knowledge.*"
_GENERAL_FALLBACK = (
    f"{_GENERAL_KNOWLEDGE_LABEL}\n\n"
    "I can answer general questions once a language model is configured. "
    "For collected signals, ask for a digest, for example: “Give me today's AI digest”."
)

_JUYA_ALL_CONFIRM_PROMPT = (
    "This digest would summarize {story_count} Juya stories from {issue}. "
    "Continue or cancel when you are ready."
)


def _interpretation_payload(decision: ConversationDecision) -> dict[str, Any]:
    payload: dict[str, Any] = {"intent": decision.intent}
    if decision.intent == "digest" and decision.request is not None:
        payload["request"] = request_payload(decision.request)
        payload["public"] = request_metadata(decision.request)
    if decision.intent == "clarify" and decision.pending:
        payload["pending"] = decision.pending
    return payload


def _apply_session_defaults(
    request: DigestRequest,
    *,
    session: Any | None,
    juya_item_mode: str | None,
) -> DigestRequest:
    updates: dict[str, Any] = {}
    sources = list(request.connector_names or [])
    if request.juya_item_mode is None:
        if juya_item_mode is not None:
            updates["juya_item_mode"] = juya_item_mode
        if "juya" in sources and request.topics_are_filters:
            updates["juya_item_mode"] = "stories"
    return replace(request, **updates) if updates else request


@dataclass(frozen=True)
class StartedEvent:
    request_id: str
    user_message_id: int
    #: Public resolved-request metadata when this message starts a digest.
    request: dict[str, Any] | None = None
    #: The interpreted intent: digest, followup, general, or clarify.
    intent: str | None = None


@dataclass(frozen=True)
class ProgressEvent:
    stage: str


@dataclass(frozen=True)
class DeltaEvent:
    text: str


@dataclass(frozen=True)
class DigestEvent:
    run_id: int
    digest: Digest
    markdown: str
    warnings: list[ConnectorWarning]
    errors: list[WorkflowError]


@dataclass(frozen=True)
class DoneEvent:
    request_id: str
    message_id: int
    run_id: int | None
    path: str


@dataclass(frozen=True)
class ErrorEvent:
    request_id: str
    code: str
    message: str
    correlation_id: str


ChatEvent = (
    StartedEvent
    | ProgressEvent
    | DeltaEvent
    | DigestEvent
    | DoneEvent
    | ErrorEvent
)


class ChatService:
    """Hybrid routing: digest workflow vs deterministic vs LLM-grounded follow-ups.

    For open-ended follow-ups, pass ``chat_model`` with::

        def generate_followup_reply(self, *, question: str, grounding: dict) -> str: ...

    Grounding is built only from ``DigestStore.get_latest_followup_context()`` data.
    """

    def __init__(
        self,
        *,
        store: DigestStore,
        workflow_runner: WorkflowRunner,
        streaming_workflow_runner: StreamingWorkflowRunner | None = None,
        chat_model: Any | None = None,
        tool_agent_runner: Any | None = None,
        interface_router: Any | None = None,
        session_service: SessionService | None = None,
        source_settings_service: SourceSettingsService | None = None,
        conversation_model: Any | None = None,
        huggingface_connector_factory: Callable[[], Any] | None = None,
        juya_connector_factory: Callable[[], Any] | None = None,
        research_handoff: Callable[..., Awaitable[str]] | None = None,
    ) -> None:
        self._store = store
        self._workflow_runner = workflow_runner
        self._streaming_workflow_runner = streaming_workflow_runner
        self._chat_model = chat_model
        self._tool_agent_runner = tool_agent_runner
        self._interface_router = interface_router
        self._session_service = session_service
        self._source_settings_service = source_settings_service
        self._conversation_model = conversation_model
        self._huggingface_connector_factory = huggingface_connector_factory
        self._juya_connector_factory = juya_connector_factory
        self._research_handoff = research_handoff

    async def stream_events(
        self,
        message: str,
        *,
        session_id: str,
        request_id: str | None = None,
        juya_item_mode: str | None = None,
        followup_target: Any | None = None,
        followup_action: str | None = None,
        research_target: Any | None = None,
        research_continuation_of: str | None = None,
        repeat_of_user_message_id: int | None = None,
        replace_source: str | None = None,
        chunk_size: int = 80,
        chunk_delay_s: float = 0.02,
    ) -> AsyncIterator[ChatEvent]:
        if self._session_service is None:
            raise RuntimeError("session_service is required for stream_events")

        followup_target_payload: dict[str, object] | None = None
        if followup_target is not None:
            followup_target_payload = (
                followup_target.model_dump()
                if hasattr(followup_target, "model_dump")
                else dict(followup_target)
            )

        research_target_payload = (
            research_target.model_dump() if hasattr(research_target, "model_dump")
            else dict(research_target) if research_target is not None else None
        )

        def validate_research_target() -> None:
            target = research_target_payload
            if research_continuation_of is not None:
                if not research_continuation_of.strip() or research_continuation_of == request_id:
                    raise ValueError("invalid research continuation")
                prior = self._session_service.get_request(session_id, research_continuation_of)
                binding = (prior.interpretation or {}).get("research") if prior is not None else None
                if prior is None or prior.status != "succeeded" or not isinstance(binding, dict) or not isinstance(binding.get("target"), dict):
                    raise ValueError("research continuation not found in session")
                if target is not None and target != binding["target"]:
                    raise ValueError("research continuation target does not match")
                target = binding["target"]
            if target is not None:
                resolve_session_entry(self._store, self._session_service, session_id, target)

        record = self._session_service.begin_request(
            session_id,
            content=message,
            request_id=request_id,
            juya_item_mode=juya_item_mode,
            followup_target=followup_target_payload,
            followup_action=followup_action,
            research_target=research_target_payload,
            research_continuation_of=research_continuation_of,
            validate_research_target=validate_research_target,
            repeat_of_user_message_id=repeat_of_user_message_id,
            replace_source=replace_source,
        )
        if record.status in _TERMINAL_REPLAY_STATUSES:
            async for event in self._replay_terminal_events(
                session_id,
                record,
                chunk_size=chunk_size,
                chunk_delay_s=chunk_delay_s,
            ):
                yield event
            return

        research_question = message
        research_subject = None
        if research_continuation_of is not None:
            prior = self._session_service.get_request(session_id, research_continuation_of)
            assert prior is not None
            binding = (prior.interpretation or {})["research"]
            research_target_payload = dict(binding["target"])
            research_subject = binding.get("subject")
        if research_target_payload is None and re.fullmatch(r"\s*(?:yes|yes please|please do|go ahead|sure)[.!]?\s*", message, re.I):
            for previous in self._session_service.list_requests(session_id):
                if previous.id == record.id:
                    continue
                if previous.status == "succeeded":
                    offer = (previous.interpretation or {}).get("research_offer")
                    if isinstance(offer, dict) and isinstance(offer.get("target"), dict):
                        research_target_payload = dict(offer["target"])
                        research_question = str(offer.get("question") or "")
                break
        pending = self._session_service.pending_clarification(session_id)
        if research_target_payload is None and pending and pending.get("kind") == "research_entry":
            match = re.fullmatch(r"\s*(?:item|entry|story|rank)\s+(\d+)\s*[.!]?\s*", message, re.I)
            if match and pending.get("digest_id") is not None:
                candidate = {"digest_id": pending["digest_id"], "display_rank": int(match.group(1))}
                try:
                    resolve_session_entry(self._store, self._session_service, session_id, candidate)
                except ValueError:
                    pass
                else:
                    research_target_payload = candidate
                    research_question = str(pending["question"])
        if research_target_payload is None and pending and pending.get("kind") == "research_subject":
            choices = pending.get("subjects", [])
            matches = [value for value in choices if isinstance(value, str) and value.casefold() == message.strip().casefold()]
            if len(matches) == 1:
                research_target_payload = dict(pending["target"])
                research_question = str(pending["question"])
                research_subject = matches[0]
            elif not is_self_contained_request(message):
                async for event in self._stream_research_clarification(
                    session_id=session_id, record=record,
                    text="Which story should I research? " + "; ".join(choices),
                    pending=pending, chunk_size=chunk_size, chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

        if (research_target_payload is None and repeat_of_user_message_id is None
                and re.match(r"^\s*(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?research\b", message, re.I)):
            ranks = re.findall(r"\b(?:item|entry|story|rank)\s+(\d+)\b", message, re.I)
            latest = self._store.get_followup_context_for_session(session_id)
            digest_id = self._store.get_digest_id_for_run(latest.run_id) if latest.run_id is not None else None
            if len(ranks) == 1 and digest_id is not None and latest.digest is not None and 1 <= int(ranks[0]) <= len(latest.digest.entries):
                research_target_payload = {"digest_id": digest_id, "display_rank": int(ranks[0])}
            else:
                async for event in self._stream_research_clarification(
                    session_id=session_id, record=record,
                    text="Which saved entry should I research?",
                    pending={"kind": "research_entry", "digest_id": digest_id, "question": message},
                    chunk_size=chunk_size, chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

        if research_target_payload is not None:
            ctx, entry = resolve_session_entry(self._store, self._session_service, session_id, research_target_payload)
            item = match_news_item_for_digest_entry(entry, ctx.news_items)
            if item is not None and item.source == SourceKind.HUGGINGFACE:
                variants = [{"source_id": item.source_id, "title": item.title}]
                extra_variants = item.source_evidence.get("family_variants")
                if isinstance(extra_variants, list):
                    variants.extend(v for v in extra_variants if isinstance(v, dict))
                matched_variants = []
                for variant in variants:
                    variant_id = variant.get("source_id")
                    if not isinstance(variant_id, str) or not variant_id:
                        continue
                    labels = (variant_id, variant.get("title"))
                    if any(isinstance(label, str) and label and re.search(
                        r"(?<![\w-])" + re.escape(label) + r"(?![\w-])", research_question, re.I
                    ) for label in labels):
                        matched_variants.append(variant_id)
                if len(set(matched_variants)) == 1:
                    research_subject = matched_variants[0]
                requested_sizes = set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?b(?![\w])", research_question, re.I))
                saved_sizes = set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?b(?![\w])", research_subject or item.source_id, re.I))
                named_variants = re.findall(r"\b[\w./]+-\d+(?:\.\d+)?b-[\w.-]+", research_question, re.I)
                if (research_subject is None and
                    ((requested_sizes and {s.casefold() for s in requested_sizes} != {s.casefold() for s in saved_sizes})
                     or (named_variants and not matched_variants))):
                    choices = [v["source_id"] for v in variants if isinstance(v.get("source_id"), str)]
                    async for event in self._stream_research_clarification(
                        session_id=session_id, record=record,
                        text="Which exact saved model variant should I research? " + "; ".join(choices),
                        pending={"kind": "research_subject", "target": research_target_payload,
                                 "question": research_question, "subjects": choices},
                        chunk_size=chunk_size, chunk_delay_s=chunk_delay_s,
                    ):
                        yield event
                    return
            if item is not None and is_juya_news_item(item) and not is_juya_story_item(item):
                subjects = [story.title for story in parse_juya_sub_news(item.raw_snippet or "")]
                if len(subjects) != 1 and research_subject is None:
                    matches = [subject for subject in subjects if subject.casefold() in research_question.casefold()]
                    if len(matches) == 1:
                        research_subject = matches[0]
                    else:
                        async for event in self._stream_research_clarification(
                            session_id=session_id, record=record,
                            text="Which story should I research? " + "; ".join(subjects),
                            pending={"kind": "research_subject", "target": research_target_payload,
                                     "question": research_question, "subjects": subjects},
                            chunk_size=chunk_size, chunk_delay_s=chunk_delay_s,
                        ):
                            yield event
                        return
            self._session_service.set_request_interpretation(
                session_id, record.id,
                {"intent": "research", "research": {"target": research_target_payload, "question": research_question, "subject": research_subject, "continuation_of": research_continuation_of}},
            )
            yield StartedEvent(request_id=record.id, user_message_id=record.user_message_id, intent="research")
            try:
                if self._research_handoff is None:
                    text = "Research is not available yet; no investigation was started."
                else:
                    text = await self._research_handoff(
                        session_id=session_id, request_id=record.id, target=research_target_payload,
                        question=research_question, subject=research_subject, context=ctx, entry=entry,
                        continuation_of=research_continuation_of,
                    )
                async for event in self._stream_session_text_events(
                    session_id=session_id, record=record, text=text, path="research",
                    chunk_size=chunk_size, chunk_delay_s=chunk_delay_s,
                ):
                    yield event
            except Exception as exc:
                async for event in self._emit_request_failed_events(session_id, record, exc=exc):
                    yield event
            return

        if followup_target_payload is not None and followup_action is not None:
            interpretation: dict[str, Any] = {
                "intent": "followup",
                "followup": {
                    "digest_id": int(followup_target_payload["digest_id"]),
                    "display_rank": int(followup_target_payload["display_rank"]),
                    "action": followup_action,
                },
            }
            self._session_service.set_request_interpretation(
                session_id,
                record.id,
                interpretation,
            )
            yield StartedEvent(
                request_id=record.id,
                user_message_id=record.user_message_id,
                intent="followup",
            )
            async for event in self._stream_session_targeted_followup_events(
                session_id=session_id,
                record=record,
                message=message,
                digest_id=int(followup_target_payload["digest_id"]),
                display_rank=int(followup_target_payload["display_rank"]),
                followup_action=followup_action,
                chunk_size=chunk_size,
                chunk_delay_s=chunk_delay_s,
            ):
                yield event
            return

        history_cmd = parse_history_chat_message(message)
        try:
            if repeat_of_user_message_id is not None:
                stored = self._session_service.stored_digest_request(
                    session_id, repeat_of_user_message_id
                )
                repeat_request = request_from_payload(stored)
                if repeat_request is not None:
                    replaced = replace_source is not None
                    if replaced:
                        repeat_request = replace(
                            repeat_request,
                            connector_names=[replace_source],
                            primary_source=replace_source,
                        )
                        if self._source_settings_service is not None:
                            repeat_request = self._source_settings_service.apply(
                                repeat_request
                            )
                    repeat_interpretation: dict[str, Any] = {
                        "intent": "digest",
                        "request": request_payload(repeat_request),
                        "public": request_metadata(repeat_request),
                    }
                    self._session_service.set_request_interpretation(
                        session_id,
                        record.id,
                        repeat_interpretation,
                    )
                    yield StartedEvent(
                        request_id=record.id,
                        user_message_id=record.user_message_id,
                        request=repeat_interpretation.get("public") or None,
                        intent="digest",
                    )
                    async for event in self._stream_confirmation_gated_digest_events(
                        session_id=session_id,
                        record=record,
                        request=repeat_request,
                        chunk_size=chunk_size,
                        chunk_delay_s=chunk_delay_s,
                    ):
                        yield event
                    return

            if history_cmd is not None:
                yield StartedEvent(
                    request_id=record.id,
                    user_message_id=record.user_message_id,
                )
                async for event in self._stream_session_text_events(
                    session_id=session_id,
                    record=record,
                    text=self._handle_history_command(history_cmd),
                    path="followup",
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

            decision = await self._resolve_conversation_decision(session_id, message)
            logger.info(
                "conversation branch=%s session_id=%s",
                decision.intent,
                session_id,
            )
            request = decision.request
            if decision.intent == "digest" and request is not None:
                request = _apply_session_defaults(
                    request,
                    session=self._session_service.get_session(session_id),
                    juya_item_mode=juya_item_mode,
                )
                if self._source_settings_service is not None:
                    request = self._source_settings_service.apply(request)
                decision = replace(decision, request=request)
            interpretation = _interpretation_payload(decision)
            self._session_service.set_request_interpretation(
                session_id,
                record.id,
                interpretation,
            )
            yield StartedEvent(
                request_id=record.id,
                user_message_id=record.user_message_id,
                request=interpretation.get("public") or None,
                intent=decision.intent,
            )

            if decision.intent == "digest" and request is not None:
                async for event in self._stream_confirmation_gated_digest_events(
                    session_id=session_id,
                    record=record,
                    request=request,
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

            if decision.intent == "general":
                text = await self._answer_general_question(
                    decision.question or message
                )
                async for event in self._stream_session_text_events(
                    session_id=session_id,
                    record=record,
                    text=text,
                    path="general",
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

            if decision.intent == "clarify":
                async for event in self._stream_session_text_events(
                    session_id=session_id,
                    record=record,
                    text=decision.clarification or _CLARIFY_FALLBACK,
                    path="clarify",
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return

            async for event in self._stream_session_followup_events(
                session_id=session_id,
                record=record,
                message=message,
                chunk_size=chunk_size,
                chunk_delay_s=chunk_delay_s,
            ):
                yield event
        except Exception as exc:
            async for event in self._emit_request_failed_events(
                session_id,
                record,
                exc=exc,
            ):
                yield event

    async def _resolve_conversation_decision(
        self,
        session_id: str,
        message: str,
    ) -> ConversationDecision:
        assert self._session_service is not None
        ctx = self._store.get_followup_context_for_session(session_id)
        session = self._session_service.get_session(session_id)
        context = ConversationContext(
            has_digest=ctx.run_id is not None or ctx.digest is not None,
            pending=self._session_service.pending_clarification(session_id),
            last_request=self._session_service.last_digest_request(session_id),
            connector_names=session.connector_names if session is not None else None,
        )
        return await asyncio.to_thread(
            interpret_message,
            message,
            context=context,
            model=self._conversation_model,
        )

    async def _answer_general_question(self, question: str) -> str:
        answer = getattr(self._conversation_model, "generate_general_answer", None)
        if answer is not None and callable(answer):
            try:
                return _format_general_answer(str(await asyncio.to_thread(answer, question=question)))
            except Exception:  # noqa: BLE001 - a model failure gets guidance
                logger.exception("general answer failed")
        return _GENERAL_FALLBACK

    async def _stream_confirmation_gated_digest_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        request: DigestRequest,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        """Run a digest, asking first when a large Juya-all selection needs confirmation."""
        if request.juya_item_count_all and not request.juya_all_confirmed:
            preview_items = await self._preview_juya_items(request)
            confirm_payload = juya_all_confirmation(request, preview_items)
            if confirm_payload is not None:
                async for event in self._stream_juya_confirmation_events(
                    session_id=session_id,
                    record=record,
                    request=request,
                    confirm_payload=confirm_payload,
                    chunk_size=chunk_size,
                    chunk_delay_s=chunk_delay_s,
                ):
                    yield event
                return
        async for event in self._stream_session_digest_events(
            session_id=session_id,
            record=record,
            request=request,
            chunk_size=chunk_size,
            chunk_delay_s=chunk_delay_s,
        ):
            yield event

    async def _preview_juya_items(self, request: DigestRequest) -> list[Any]:
        if self._juya_connector_factory is None:
            return []
        connector = self._juya_connector_factory()
        try:
            result = await connector.collect(
                ConnectorRequest(
                    topics=list(request.topics or []),
                    timeframe=request.timeframe,
                    max_items=request.max_items_per_source,
                    juya_manual_urls=list(request.juya_manual_urls),
                    juya_item_mode="stories",
                    juya_collect_all_stories=True,
                    topics_are_filters=request.topics_are_filters,
                    strict_timeframe=request.strict_timeframe,
                )
            )
            return list(result.items)
        finally:
            if hasattr(connector, "aclose"):
                await connector.aclose()

    async def _stream_juya_confirmation_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        request: DigestRequest,
        confirm_payload: dict[str, object],
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        text = _JUYA_ALL_CONFIRM_PROMPT.format(
            story_count=confirm_payload["story_count"],
            issue=confirm_payload["issue"],
        )
        async for chunk in iter_text_chunks(
            text,
            chunk_size=chunk_size,
            delay_s=chunk_delay_s,
        ):
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            yield DeltaEvent(text=chunk)
        cancelled = self._cancelled_error_event(session_id, record)
        if cancelled is not None:
            yield cancelled
            return
        try:
            message_id = self._session_service.attach_interim_assistant(
                session_id,
                record.id,
                content=text,
            )
        except KeyError:
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            raise
        self._session_service.set_request_interpretation(
            session_id,
            record.id,
            {
                "juya_confirmation": {
                    **confirm_payload,
                    "request": request_payload(request),
                },
            },
        )
        yield DoneEvent(
            request_id=record.id,
            message_id=message_id,
            run_id=None,
            path="juya_confirmation",
        )

    async def continue_juya_all(
        self,
        session_id: str,
        request_id: str,
        *,
        chunk_size: int = 80,
        chunk_delay_s: float = 0.02,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        stored = self._session_service.claim_juya_confirmation(
            session_id, request_id
        )
        if stored is None:
            raise KeyError(
                f"pending Juya confirmation not found: session={session_id!r} "
                f"request={request_id!r}"
            )
        record = self._session_service.get_request(session_id, request_id)
        if record is None:
            raise KeyError(
                f"pending Juya confirmation not found: session={session_id!r} "
                f"request={request_id!r}"
            )
        req = request_from_payload(stored.get("request"))
        if req is None:
            raise KeyError("stored Juya confirmation request payload missing")
        req = replace(req, juya_all_confirmed=True)
        yield StartedEvent(
            request_id=record.id,
            user_message_id=record.user_message_id,
            request=request_metadata(req),
            intent="digest",
        )
        async for event in self._stream_session_digest_events(
            session_id=session_id,
            record=record,
            request=req,
            chunk_size=chunk_size,
            chunk_delay_s=chunk_delay_s,
        ):
            yield event

    async def _stream_session_digest_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        request: DigestRequest,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        req = request
        runner = self._iter_streaming_runner(
            req,
            session_id=session_id,
            request_id=record.id,
        )
        while True:
            try:
                progress, done, result = await anext(runner)
            except StopAsyncIteration:
                break
            except Exception:
                logger.exception(
                    "session digest workflow failed session_id=%s",
                    session_id,
                )
                try:
                    self._session_service.complete_request(
                        session_id,
                        record.id,
                        status="failed",
                        content=_WORKFLOW_ERROR_MESSAGE,
                        error_code=_WORKFLOW_ERROR_CODE,
                        error_message=_WORKFLOW_ERROR_MESSAGE,
                    )
                except KeyError:
                    cancelled = self._cancelled_error_event(session_id, record)
                    if cancelled is not None:
                        yield cancelled
                        return
                    raise
                yield ErrorEvent(
                    request_id=record.id,
                    code=_WORKFLOW_ERROR_CODE,
                    message=_WORKFLOW_ERROR_MESSAGE,
                    correlation_id=record.correlation_id,
                )
                return

            if not done:
                cancelled = self._cancelled_error_event(session_id, record)
                if cancelled is not None:
                    yield cancelled
                    return
                if progress:
                    yield ProgressEvent(stage=progress)
                continue

            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            if result is None:
                continue
            if result.run_id is None:
                failure_message = _digest_failure_message(result)
                try:
                    self._session_service.complete_request(
                        session_id,
                        record.id,
                        status="failed",
                        content=failure_message,
                        error_code=_WORKFLOW_ERROR_CODE,
                        error_message=failure_message,
                    )
                except KeyError:
                    cancelled = self._cancelled_error_event(session_id, record)
                    if cancelled is not None:
                        yield cancelled
                        return
                    raise
                yield ErrorEvent(
                    request_id=record.id,
                    code=_WORKFLOW_ERROR_CODE,
                    message=failure_message,
                    correlation_id=record.correlation_id,
                )
                return
            markdown = _user_facing_digest_markdown(result)
            async for chunk in iter_text_chunks(
                markdown,
                chunk_size=chunk_size,
                delay_s=chunk_delay_s,
            ):
                cancelled = self._cancelled_error_event(session_id, record)
                if cancelled is not None:
                    yield cancelled
                    return
                yield DeltaEvent(text=chunk)
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            if result.digest is not None and result.run_id is not None:
                yield DigestEvent(
                    run_id=result.run_id,
                    digest=result.digest,
                    markdown=markdown,
                    warnings=result.warnings,
                    errors=result.errors,
                )
            try:
                message_id = self._session_service.complete_request(
                    session_id,
                    record.id,
                    status="succeeded",
                    content=markdown,
                    run_id=result.run_id,
                )
            except KeyError:
                cancelled = self._cancelled_error_event(session_id, record)
                if cancelled is not None:
                    yield cancelled
                    return
                raise
            if result.digest is not None:
                from collections import Counter

                entry_counts = Counter(
                    entry.source_kind.value for entry in result.digest.entries
                )
                self._session_service.set_request_interpretation(
                    session_id,
                    record.id,
                    {
                        "public": {
                            **(
                                request_metadata(req)
                            ),
                            "counts": finalize_public_counts(
                                req,
                                entry_counts=dict(entry_counts),
                            ),
                        }
                    },
                )
            yield DoneEvent(
                request_id=record.id,
                message_id=message_id,
                run_id=result.run_id,
                path="digest",
            )

    async def _emit_request_failed_events(
        self,
        session_id: str,
        record: SessionRequestRecord,
        *,
        exc: Exception,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        logger.exception(
            "session request failed session_id=%s request_id=%s",
            session_id,
            record.id,
            exc_info=exc,
        )
        cancelled = self._cancelled_error_event(session_id, record)
        if cancelled is not None:
            yield cancelled
            return
        try:
            self._session_service.complete_request(
                session_id,
                record.id,
                status="failed",
                content=_REQUEST_FAILED_MESSAGE,
                error_code=_REQUEST_FAILED_CODE,
                error_message=_REQUEST_FAILED_MESSAGE,
            )
        except KeyError:
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            raise
        yield ErrorEvent(
            request_id=record.id,
            code=_REQUEST_FAILED_CODE,
            message=_REQUEST_FAILED_MESSAGE,
            correlation_id=record.correlation_id,
        )

    def _cancelled_error_event(
        self,
        session_id: str,
        record: SessionRequestRecord,
    ) -> ErrorEvent | None:
        assert self._session_service is not None
        current = self._session_service.get_request(session_id, record.id)
        if current is None or current.status != "cancelled":
            return None
        return ErrorEvent(
            request_id=record.id,
            code="cancelled",
            message=CANCELLED_ASSISTANT_MESSAGE,
            correlation_id=record.correlation_id,
        )

    async def _stream_session_targeted_followup_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        message: str,
        digest_id: int,
        display_rank: int,
        followup_action: str,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        text = await self._handle_targeted_followup_async(
            session_id,
            message,
            digest_id=digest_id,
            display_rank=display_rank,
            followup_action=followup_action,
        )
        cancelled = self._cancelled_error_event(session_id, record)
        if cancelled is not None:
            yield cancelled
            return
        if followup_action == "ask" and self._research_handoff is not None:
            assert self._session_service is not None
            self._session_service.set_request_interpretation(session_id, record.id, {
                "research_offer": {"target": {"digest_id": digest_id, "display_rank": display_rank}, "question": message},
            })
            text += "\n\nWould you like me to research this question for this entry?"
        async for event in self._stream_session_text_events(
            session_id=session_id,
            record=record,
            text=text,
            path="followup",
            chunk_size=chunk_size,
            chunk_delay_s=chunk_delay_s,
        ):
            yield event

    async def _stream_session_followup_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        message: str,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        text = await self._handle_session_followup_message_async(
            session_id,
            message,
        )
        cancelled = self._cancelled_error_event(session_id, record)
        if cancelled is not None:
            yield cancelled
            return
        async for event in self._stream_session_text_events(
            session_id=session_id,
            record=record,
            text=text,
            path="followup",
            chunk_size=chunk_size,
            chunk_delay_s=chunk_delay_s,
        ):
            yield event

    async def _stream_research_clarification(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        text: str,
        pending: dict[str, Any],
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        """Ask the one pending research question and stop before any retrieval."""
        assert self._session_service is not None
        self._session_service.set_request_interpretation(
            session_id,
            record.id,
            {"intent": "clarify", "pending": pending},
        )
        yield StartedEvent(
            request_id=record.id,
            user_message_id=record.user_message_id,
            intent="clarify",
        )
        async for event in self._stream_session_text_events(
            session_id=session_id,
            record=record,
            text=text,
            path="clarify",
            chunk_size=chunk_size,
            chunk_delay_s=chunk_delay_s,
        ):
            yield event

    async def _stream_session_text_events(
        self,
        *,
        session_id: str,
        record: SessionRequestRecord,
        text: str,
        path: str,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        assert self._session_service is not None
        async for chunk in iter_text_chunks(
            text,
            chunk_size=chunk_size,
            delay_s=chunk_delay_s,
        ):
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            yield DeltaEvent(text=chunk)
        cancelled = self._cancelled_error_event(session_id, record)
        if cancelled is not None:
            yield cancelled
            return
        try:
            message_id = self._session_service.complete_request(
                session_id,
                record.id,
                status="succeeded",
                content=text,
            )
        except KeyError:
            cancelled = self._cancelled_error_event(session_id, record)
            if cancelled is not None:
                yield cancelled
                return
            raise
        yield DoneEvent(
            request_id=record.id,
            message_id=message_id,
            run_id=None,
            path=path,
        )

    async def _replay_terminal_events(
        self,
        session_id: str,
        record: SessionRequestRecord,
        *,
        chunk_size: int,
        chunk_delay_s: float,
    ) -> AsyncIterator[ChatEvent]:
        yield StartedEvent(
            request_id=record.id,
            user_message_id=record.user_message_id,
            request=(record.interpretation or {}).get("public") or None,
            intent=(record.interpretation or {}).get("intent"),
        )
        assert self._session_service is not None
        text = ""
        if record.assistant_message_id is not None:
            for message in self._session_service.list_messages(session_id):
                if message.id == record.assistant_message_id:
                    text = message.content
                    break
        async for chunk in iter_text_chunks(
            text,
            chunk_size=chunk_size,
            delay_s=chunk_delay_s,
        ):
            yield DeltaEvent(text=chunk)
        if record.status == "succeeded":
            if record.run_id is not None:
                digest = self._store.get_digest_by_run_id(record.run_id)
                if digest is not None:
                    yield DigestEvent(
                        run_id=record.run_id,
                        digest=digest,
                        markdown=text,
                        warnings=self._store.get_connector_warnings_for_run(
                            record.run_id
                        ),
                        errors=[],
                    )
            yield DoneEvent(
                request_id=record.id,
                message_id=record.assistant_message_id or 0,
                run_id=record.run_id,
                path=("digest" if record.run_id is not None else
                      "research" if (record.interpretation or {}).get("intent") == "research" else "followup"),
            )
            return
        yield ErrorEvent(
            request_id=record.id,
            code=record.error_code or record.status,
            message=record.error_message or text,
            correlation_id=record.correlation_id,
        )

    async def _iter_streaming_runner(
        self,
        req: DigestRequest,
        *,
        session_id: str,
        request_id: str,
    ) -> AsyncIterator[tuple[str, bool, DigestResult | None]]:
        if self._streaming_workflow_runner is not None:
            try:
                stream = self._streaming_workflow_runner(
                    req,
                    session_id=session_id,
                    request_id=request_id,
                )
            except TypeError:
                stream = self._streaming_workflow_runner(req)
            async for event in stream:
                yield event
            return
        try:
            result = await self._workflow_runner(
                req,
                session_id=session_id,
                request_id=request_id,
            )
        except TypeError:
            result = await self._workflow_runner(req)
        yield "", True, result

    async def _handle_targeted_followup_async(
        self,
        session_id: str,
        message: str,
        *,
        digest_id: int,
        display_rank: int,
        followup_action: str,
    ) -> str:
        ctx = self._store.get_followup_context_for_digest(digest_id)
        if ctx is None:
            return NO_SAVED_DIGEST
        if ctx.run_id is None and ctx.digest is None:
            logger.info(
                "targeted follow-up path=no_saved_digest session_id=%s digest_id=%s",
                session_id,
                digest_id,
            )
            return NO_SAVED_DIGEST

        latest = self._store.get_followup_context_for_session(session_id)
        fetch_allowed = (
            ctx.run_id is not None
            and latest.run_id is not None
            and ctx.run_id == latest.run_id
        )

        if followup_action == "deep_dive":
            logger.info(
                "targeted follow-up path=deep_dive session_id=%s rank=%s",
                session_id,
                display_rank,
            )
            return await answer_targeted_deep_dive(
                ctx,
                display_rank,
                self._store,
                fetch_allowed=fetch_allowed,
                digest_id=digest_id,
                huggingface_connector_factory=self._huggingface_connector_factory,
            )

        if followup_action == "ask":
            logger.info(
                "targeted follow-up path=ask session_id=%s rank=%s",
                session_id,
                display_rank,
            )
            fn = getattr(self._chat_model, "generate_followup_reply", None)
            if fn is None or not callable(fn):
                card = build_targeted_card(
                    ctx,
                    display_rank,
                    saved_with_digest=not fetch_allowed,
                )
                return f"{card}\n\n{_TARGETED_ASK_UNAVAILABLE}"
            grounding = _build_targeted_grounding(ctx, display_rank)
            try:
                return str(fn(question=message, grounding=grounding))
            except ValueError as exc:
                if str(exc) != _LLM_UNCONFIGURED_MESSAGE:
                    raise
                card = build_targeted_card(
                    ctx,
                    display_rank,
                    saved_with_digest=not fetch_allowed,
                )
                return f"{card}\n\n{_TARGETED_ASK_UNAVAILABLE}"

        return build_targeted_card(
            ctx,
            display_rank,
            saved_with_digest=not fetch_allowed,
        )

    async def _handle_session_followup_message_async(
        self,
        session_id: str,
        message: str,
    ) -> str:
        ctx = self._store.get_followup_context_for_session(session_id)
        if ctx.run_id is None and ctx.digest is None:
            logger.info("follow-up path=no_saved_digest session_id=%s", session_id)
            return NO_SAVED_DIGEST

        structured = answer_structured_followup(message, ctx)
        if structured is not None:
            logger.info("follow-up path=structured session_id=%s", session_id)
            return structured

        run_session_followup = getattr(
            self._interface_router,
            "run_session_followup",
            None,
        )
        if callable(run_session_followup):
            logger.info("follow-up path=tool_agent session_id=%s", session_id)
            result = await run_session_followup(
                session_id=session_id,
                message=message,
            )
            return _interface_result_to_text(result, store=self._store)

        if self._tool_agent_runner is not None:
            logger.info("follow-up path=tool_agent session_id=%s", session_id)
            result = await self._tool_agent_runner.run(message)
            return _tool_agent_result_to_text(result, store=self._store)

        llm_text = _try_llm_followup(self._chat_model, message, ctx)
        if llm_text is not None:
            logger.info("follow-up path=llm session_id=%s", session_id)
            return llm_text

        logger.info("follow-up path=guidance_fallback session_id=%s", session_id)
        return (
            "I need a configured language model to answer that question. "
            "Try a concrete request like listing sources or asking for caveats."
        )



    def _handle_history_command(self, cmd: HistoryChatCommand) -> str:
        if cmd.error is not None:
            return cmd.error
        if cmd.action == "search":
            if cmd.query is None:
                raise NotImplementedError
            result = search_digest_history(self._store, cmd.query)
            return format_history_search_text(result)
        if cmd.action == "open":
            if cmd.token is None:
                return HISTORY_NOT_FOUND
            text = show_historical_item(self._store, cmd.token)
            return text if text is not None else HISTORY_NOT_FOUND
        raise NotImplementedError


def _format_general_answer(text: str) -> str:
    body = text.strip()
    if "general knowledge" in body.lower():
        return body
    return f"{_GENERAL_KNOWLEDGE_LABEL}\n\n{body}"


def _tool_agent_result_to_text(result: Any, *, store: DigestStore | None = None) -> str:
    if isinstance(result, InterfaceAgentResult):
        return _interface_result_to_text(result, store=store)
    return str(result)


def _interface_result_to_text(
    result: InterfaceAgentResult,
    *,
    store: DigestStore | None = None,
) -> str:
    if result.kind is InterfaceAgentResultKind.DIGEST:
        warnings: list = []
        errors: list = []
        if store is not None and result.run_id is not None:
            ctx = store.get_latest_followup_context()
            if ctx.run_id == result.run_id:
                warnings = ctx.warnings
        notice = format_connector_warnings_notice(warnings, errors)
        if not notice:
            return result.text
        if notice in result.text:
            return result.text
        return f"{notice}\n\n{result.text}"
    return result.text


def _digest_failure_message(result: DigestResult) -> str:
    for error in result.errors:
        if error.message:
            return error.message
    return _WORKFLOW_ERROR_MESSAGE




def _user_facing_digest_markdown(result: DigestResult) -> str:
    notice = format_connector_warnings_notice(result.warnings, result.errors)
    if not notice:
        return result.markdown
    if notice in result.markdown:
        return result.markdown
    return f"{notice}\n\n{result.markdown}"




def _try_llm_followup(model: Any | None, question: str, ctx: FollowupContext) -> str | None:
    if model is None:
        return None
    fn = getattr(model, "generate_followup_reply", None)
    if fn is None or not callable(fn):
        return None
    grounding = _build_grounding_context(ctx)
    return str(fn(question=question, grounding=grounding))


def _build_targeted_grounding(ctx: FollowupContext, rank: int) -> dict[str, Any]:
    if ctx.digest is None or rank < 1 or rank > len(ctx.digest.entries):
        return {"entry": None, "news_item": None}
    entry = ctx.digest.entries[rank - 1]
    news_item = match_news_item_for_digest_entry(entry, ctx.news_items)
    payload: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "source_url": entry.source_url,
            "summary": entry.summary,
            "why_it_matters": entry.why_it_matters,
            "background_knowledge": entry.background_knowledge,
            "confidence_caveat": entry.confidence_caveat,
            "source_kind": entry.source_kind.value,
            "source_id": entry.source_id,
        }
    }
    if news_item is not None:
        payload["news_item"] = {
            "title": news_item.title,
            "url": news_item.url,
            "raw_snippet": news_item.raw_snippet,
            "source_evidence": dict(news_item.source_evidence),
        }
    else:
        payload["news_item"] = None
    return payload


def _build_grounding_context(ctx: FollowupContext) -> dict[str, Any]:
    out: dict[str, Any] = {
        "run_id": ctx.run_id,
        "warnings": [
            {
                "connector": w.connector,
                "code": w.code,
                "message": w.message,
                "detail": w.detail,
            }
            for w in ctx.warnings
        ],
    }
    if ctx.digest:
        out["digest"] = {
            "topics": ctx.digest.topics,
            "timeframe": ctx.digest.timeframe,
            "generated_at": ctx.digest.generated_at.isoformat(),
            "entries": [
                {
                    "title": e.title,
                    "source_url": e.source_url,
                    "summary": e.summary,
                    "why_it_matters": e.why_it_matters,
                    "confidence_caveat": e.confidence_caveat,
                }
                for e in ctx.digest.entries
            ],
        }
    out["ranked_items"] = [
        {
            "title": r.item.title,
            "url": r.item.url,
            "score_total": r.score_total,
            "selected": r.selected,
            "selection_reason": r.selection_reason,
        }
        for r in ctx.ranked_items
    ]
    out["news_items"] = [
        {
            "title": n.title,
            "url": n.url,
            "source": n.source.value,
            "source_id": n.source_id,
        }
        for n in ctx.news_items
    ]
    return out


__all__ = [
    "ChatEvent",
    "ChatService",
    "DeltaEvent",
    "DigestEvent",
    "DoneEvent",
    "ErrorEvent",
    "ProgressEvent",
    "StartedEvent",
]
