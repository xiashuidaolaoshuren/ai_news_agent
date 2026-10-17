"""Browser conversation interpretation (Milestone: natural requests)."""

from __future__ import annotations

from ai_news_agent.services.conversation import (
    ConversationContext,
    ConversationDecision,
    interpret_message,
    request_from_payload,
    request_metadata,
    request_payload,
)
from ai_news_agent.request import DigestRequest


def test_weekly_model_news_request_becomes_a_bounded_juya_digest() -> None:
    decision = interpret_message("What shipped in open-weight models this week?")

    assert decision.intent == "digest"
    request = decision.request
    assert request is not None
    assert request.connector_names == ["juya"]
    assert request.timeframe == "this_week"
    assert request.topics == ["open-weight models"]
    assert request.topics_are_filters is True
    assert request.strict_timeframe is True


def test_github_tooling_request_keeps_its_per_source_count() -> None:
    decision = interpret_message("Trending agent tooling on GitHub, 5 per source")

    assert decision.intent == "digest"
    request = decision.request
    assert request is not None
    assert request.connector_names == ["github"]
    assert request.items_per_source == 5
    assert request.timeframe is None
    assert request.topics == ["agent tooling"]


def test_latest_juya_request_keeps_latest_scope_and_beginner_audience() -> None:
    decision = interpret_message("Summarize the latest Juya AI 早报 for a beginner")

    assert decision.intent == "digest"
    request = decision.request
    assert request is not None
    assert request.connector_names == ["juya"]
    assert request.timeframe == "latest"
    assert request.strict_timeframe is False
    assert request.audience == "beginner"
    assert request.topics == ["AI"]


def test_questions_about_saved_results_stay_followups() -> None:
    for message in ("Explain item 2", "Make that beginner-friendly"):
        decision = interpret_message(
            message,
            context=ConversationContext(has_digest=True),
        )
        assert decision.intent == "followup", message


def test_standalone_educational_question_is_a_general_explanation() -> None:
    decision = interpret_message("What is RAG?")

    assert decision.intent == "general"
    assert decision.question == "What is RAG?"
    assert decision.request is None


def test_vague_topic_request_asks_one_clarification() -> None:
    class _GeneralModel:
        def interpret_conversation(self, context: dict[str, object]) -> dict[str, object]:
            return {"intent": "general", "question": str(context["message"])}

    decision = interpret_message("Tell me about Qwen", model=_GeneralModel())

    assert decision.intent == "clarify"
    assert decision.clarification is not None
    assert "Qwen" in decision.clarification
    assert decision.pending is not None
    assert decision.pending["message"] == "Tell me about Qwen"


class _FakeModel:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.contexts: list[dict[str, object]] = []

    def interpret_conversation(self, context: dict[str, object]) -> object:
        self.contexts.append(context)
        return self.payload


def test_model_interprets_unmatched_message_and_clamps_invalid_options() -> None:
    model = _FakeModel(
        {
            "intent": "digest",
            "topics": ["Qwen"],
            "sources": ["huggingface", "bogus"],
            "timeframe": "last_7_days",
            "items_per_source": 50,
            "language": "fr",
            "audience": "expert",
        }
    )

    decision = interpret_message("Any Qwen movement?", model=model)

    assert decision.intent == "digest"
    request = decision.request
    assert request is not None
    assert request.connector_names == ["huggingface"]
    assert request.topics == ["Qwen"]
    assert request.topics_are_filters is True
    assert request.items_per_source == 20
    assert request.output_language is None
    assert request.audience is None
    assert request.timeframe == "last_7_days"
    assert request.strict_timeframe is True
    assert model.contexts[0]["message"] == "Any Qwen movement?"


def test_unusable_model_result_never_collects() -> None:
    decision = interpret_message(
        "Any Qwen movement?",
        model=_FakeModel({"intent": "surprise-me"}),
    )

    assert decision.intent == "general"
    assert decision.request is None
    assert decision.question == "Any Qwen movement?"


def test_short_reply_completes_a_pending_clarification() -> None:
    pending = {"message": "Tell me about Qwen", "topic": "Qwen"}

    decision = interpret_message(
        "Recent updates",
        context=ConversationContext(pending=pending),
    )

    assert decision.intent == "digest"
    request = decision.request
    assert request is not None
    assert request.topics == ["Qwen"]
    assert request.topics_are_filters is True
    assert request.timeframe == "latest"


def test_short_reply_can_choose_a_general_explanation() -> None:
    pending = {"message": "Tell me about Qwen", "topic": "Qwen"}

    decision = interpret_message(
        "A general explanation",
        context=ConversationContext(pending=pending),
    )

    assert decision.intent == "general"
    assert decision.question is not None
    assert "Qwen" in decision.question


def test_request_metadata_describes_what_the_run_will_use() -> None:
    request = DigestRequest(
        topics=["AI"],
        topics_are_filters=True,
        timeframe="latest",
        items_per_source=5,
        output_language="zh-CN",
        audience="beginner",
        connector_names=["juya"],
        primary_source="juya",
    )

    assert request_metadata(request) == {
        "sources": ["juya"],
        "per_source": 5,
        "timeframe": "latest",
        "topics": ["AI"],
        "language": "zh-CN",
        "audience": "beginner",
    }


def test_request_payload_round_trips_for_a_later_refresh() -> None:
    request = DigestRequest(
        topics=["Qwen"],
        topics_are_filters=True,
        timeframe="last_7_days",
        items_per_source=5,
        connector_names=["huggingface"],
        primary_source="huggingface",
    )

    restored = request_from_payload(request_payload(request))

    assert restored == request


def test_refresh_reuses_the_last_digest_request_exactly() -> None:
    stored = request_payload(
        DigestRequest(
            topics=["Qwen"],
            topics_are_filters=True,
            timeframe="latest",
            items_per_source=5,
            connector_names=["juya"],
            primary_source="juya",
        )
    )

    decision = interpret_message(
        "Refresh it",
        context=ConversationContext(has_digest=True, last_request=stored),
    )

    assert decision.intent == "digest"
    assert decision.request == request_from_payload(stored)


def test_refresh_without_a_saved_request_stays_a_followup() -> None:
    decision = interpret_message(
        "Refresh it",
        context=ConversationContext(has_digest=True),
    )

    assert decision.intent == "followup"


def test_explicit_repo_url_keeps_its_target_and_selection() -> None:
    decision = interpret_message("Summarize https://github.com/org/repo")

    assert decision.intent == "digest"
    request = decision.request
    assert request is not None
    assert request.connector_names == ["github"]
    assert request.github_manual_urls == ["https://github.com/org/repo"]
    assert request.topics_are_filters is False


__all__ = [
    "ConversationContext",
    "ConversationDecision",
    "interpret_message",
]
