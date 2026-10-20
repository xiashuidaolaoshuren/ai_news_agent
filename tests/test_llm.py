"""Tests for validated digest-field decoding (Juya live cleanup)."""

from __future__ import annotations

from types import SimpleNamespace

from ai_news_agent.digest_content import empty_digest_fields, extract_digest_fields
from ai_news_agent.llm import OpenAIChatModel


def _fields(summary: str = "S") -> dict[str, str]:
    return {
        "summary": summary,
        "why_it_matters": "W",
        "background_knowledge": "B",
        "follow_up_action": "read",
    }


def test_extract_digest_fields_reads_plain_object() -> None:
    assert extract_digest_fields('{"summary": "S", "why_it_matters": "W"}') == {
        "summary": "S",
        "why_it_matters": "W",
        "background_knowledge": "",
        "follow_up_action": "",
    }


def test_extract_digest_fields_unwraps_fenced_object() -> None:
    raw = '```json\n{"summary": "S", "why_it_matters": "W"}\n```'

    assert extract_digest_fields(raw)["summary"] == "S"


def test_extract_digest_fields_discards_commentary_and_reasoning() -> None:
    raw = (
        "Wait, I must output only the JSON object.\n"
        '<｜end▁of▁thinking｜>{"summary": "S", "why_it_matters": "W"}'
        " trailing note"
    )

    fields = extract_digest_fields(raw)

    assert fields["summary"] == "S"
    assert "JSON" not in fields["summary"]


def test_extract_digest_fields_rejects_truncated_json() -> None:
    raw = 'Let me produce clean JSON. {"summary": "the office is still exa'

    assert extract_digest_fields(raw) == empty_digest_fields()


def test_extract_digest_fields_rejects_non_string_fields() -> None:
    raw = '{"summary": ["not", "a", "string"], "why_it_matters": "W"}'

    assert extract_digest_fields(raw) == empty_digest_fields()


def test_extract_digest_fields_requires_a_summary() -> None:
    raw = '{"why_it_matters": "W", "background_knowledge": "B"}'

    assert extract_digest_fields(raw) == empty_digest_fields()


def test_juya_story_prompt_requests_concise_chinese() -> None:
    from ai_news_agent.llm import _build_summarization_system_prompt

    prompt = _build_summarization_system_prompt(
        {"output_language": "zh-CN", "juya_story": True}
    )

    assert "zh-CN" in prompt
    assert "background_knowledge" in prompt
    assert "one or two sentences" in prompt
    assert "story_summary" in prompt
    assert "no commentary" in prompt.lower()


def test_non_juya_prompt_keeps_generic_guidance() -> None:
    from ai_news_agent.llm import _build_summarization_system_prompt

    prompt = _build_summarization_system_prompt({"output_language": "", "juya_story": False})

    assert "one or two sentences" not in prompt
    assert "story_summary" not in prompt


def test_openai_chat_model_never_returns_raw_text_as_summary() -> None:
    def create(**_kwargs: object) -> SimpleNamespace:
        message = SimpleNamespace(content="I could not produce JSON, sorry.")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = OpenAIChatModel(client=client, model="test")

    fields = model.generate_entry_fields({"title": "T"})

    assert fields["summary"] == ""
    assert "sorry" not in fields["summary"]


def test_openai_chat_model_recovers_wrapped_json() -> None:
    def create(**_kwargs: object) -> SimpleNamespace:
        content = (
            "Here is the object:\n```json\n"
            '{"summary": "S", "why_it_matters": "W", "background_knowledge": "B",'
            ' "follow_up_action": "read"}\n```'
        )
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = OpenAIChatModel(client=client, model="test")

    assert model.generate_entry_fields({"title": "T"}) == _fields()


def test_openai_chat_model_returns_a_validated_conversation_decision() -> None:
    prompts: list[str] = []

    def create(**kwargs: object) -> SimpleNamespace:
        messages = kwargs["messages"]
        prompts.append(str(messages[0]["content"]))  # type: ignore[index]
        content = (
            "```json\n"
            '{"intent": "digest", "topics": ["Qwen"], "sources": ["huggingface"],'
            ' "timeframe": "last_7_days", "items_per_source": 5,'
            ' "language": "en", "audience": null}\n```'
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = OpenAIChatModel(client=client, model="test")

    decision = model.interpret_conversation({"message": "Any Qwen movement?"})

    assert decision["intent"] == "digest"
    assert decision["topics"] == ["Qwen"]
    assert "JSON object" in prompts[0]


def test_openai_chat_model_rejects_unusable_conversation_output() -> None:
    def create(**_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = OpenAIChatModel(client=client, model="test")

    assert model.interpret_conversation({"message": "hello"}) == {}


def test_general_answer_is_labelled_as_general_knowledge() -> None:
    prompts: list[str] = []

    def create(**kwargs: object) -> SimpleNamespace:
        messages = kwargs["messages"]
        prompts.append(str(messages[0]["content"]))  # type: ignore[index]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="RAG combines retrieval."))]
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = OpenAIChatModel(client=client, model="test")

    answer = model.generate_general_answer(question="What is RAG?")

    assert answer == "RAG combines retrieval."
    assert "general knowledge" in prompts[0]
    assert "current" in prompts[0]
