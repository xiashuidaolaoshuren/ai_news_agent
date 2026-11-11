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

    decision = interpret_message("What about Qwen", model=_GeneralModel())

    assert decision.intent == "clarify"
    assert decision.clarification is not None
    assert "Qwen" in decision.clarification
    assert decision.pending is not None
    assert decision.pending["message"] == "What about Qwen"


def test_tell_me_about_a_topic_is_a_general_explanation() -> None:
    contexts = (
        ConversationContext(),
        ConversationContext(has_digest=True),
        ConversationContext(connector_names=["github"]),
        ConversationContext(has_digest=True, connector_names=["zhihu"]),
    )

    for context in contexts:
        decision = interpret_message("Tell me about Qwen", context=context)
        assert decision.intent == "general", context
        assert decision.question == "Tell me about Qwen"
        assert decision.request is None


def test_tell_me_about_a_topic_stays_general_when_a_model_is_configured() -> None:
    class _GeneralModel:
        def interpret_conversation(self, context: dict[str, object]) -> dict[str, object]:
            return {"intent": "general", "question": str(context["message"])}

    decision = interpret_message(
        "Tell me about Qwen",
        context=ConversationContext(has_digest=True),
        model=_GeneralModel(),
    )

    assert decision.intent == "general"
    assert decision.question == "Tell me about Qwen"


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
    assert request.items_per_source == 50
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


def test_explain_entry_above_is_followup_with_or_without_digest() -> None:
    message = "Explain the Qwen entry above"
    for context in (ConversationContext(), ConversationContext(has_digest=True)):
        decision = interpret_message(message, context=context)
        assert decision.intent == "followup", context


def test_recent_topic_updates_is_a_digest_regardless_of_context() -> None:
    contexts = (
        ConversationContext(),
        ConversationContext(has_digest=True),
        ConversationContext(connector_names=["zhihu"]),
        ConversationContext(has_digest=True, connector_names=["zhihu"]),
    )
    for context in contexts:
        decision = interpret_message("Recent Qwen updates", context=context)
        assert decision.intent == "digest", context
        assert decision.request is not None
        assert decision.request.topics == ["Qwen"]


def test_recent_updates_without_topic_stays_a_short_clarification_reply() -> None:
    pending = {"message": "What about Qwen", "topic": "Qwen"}
    decision = interpret_message(
        "Recent updates",
        context=ConversationContext(pending=pending),
    )
    assert decision.intent == "digest"
    assert decision.request is not None
    assert decision.request.topics == ["Qwen"]


def test_self_contained_message_replaces_pending_clarification() -> None:
    pending = {"message": "What about Qwen", "topic": "Qwen"}

    llama = interpret_message(
        "Recent Llama updates",
        context=ConversationContext(pending=pending),
    )
    assert llama.intent == "digest"
    assert llama.request is not None
    assert llama.request.topics == ["Llama"]

    rag = interpret_message(
        "What is RAG?",
        context=ConversationContext(pending=pending),
    )
    assert rag.intent == "general"
    assert rag.question == "What is RAG?"


def test_short_reply_completes_a_pending_clarification() -> None:
    pending = {"message": "What about Qwen", "topic": "Qwen"}

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
    pending = {"message": "What about Qwen", "topic": "Qwen"}

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
        "counts": {"juya": "5"},
        "timeframe": "latest",
        "windows": {"juya": "latest"},
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


def test_openrouter_in_message_selects_openrouter_connector() -> None:
    decision = interpret_message(
        "Summarize openrouter and github agent tooling releases"
    )

    assert decision.intent == "digest"
    request = decision.request
    assert request is not None
    assert "openrouter" in request.connector_names
    assert "github" in request.connector_names


def test_windows_report_openrouter_fallback_without_storing_timeframe() -> None:
    request = DigestRequest(
        connector_names=["openrouter", "github"],
        timeframe=None,
    )
    meta = request_metadata(request)
    assert meta["timeframe"] is None
    assert meta["windows"] == {"openrouter": "last_7_days", "github": ""}

    payload = request_payload(request)
    assert payload["timeframe"] is None
    round_tripped = request_from_payload(payload)
    assert round_tripped is not None
    assert round_tripped.timeframe is None
    assert request_metadata(round_tripped)["windows"]["openrouter"] == "last_7_days"


def test_explicit_timeframe_fills_windows_for_every_source() -> None:
    request = DigestRequest(
        connector_names=["openrouter", "github"],
        timeframe="today",
    )
    assert request_metadata(request)["windows"] == {
        "openrouter": "today",
        "github": "today",
    }


def test_typed_bilibili_request_selects_bilibili_while_hidden_by_default() -> None:
    decision = interpret_message("Summarize bilibili AI news")

    assert decision.intent == "digest"
    request = decision.request
    assert request is not None
    assert "bilibili" in request.connector_names


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
