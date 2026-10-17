"""Browser chat messages turned into one executable conversation decision."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, replace
from typing import Any, Literal

from ai_news_agent.digest_request_builder import resolve_digest_request
from ai_news_agent.followup_structured import is_structured_followup
from ai_news_agent.intent import parse_digest_intent
from ai_news_agent.request import DigestRequest
from ai_news_agent.sources import ALLOWED_SOURCES, normalize_source_names

_TIMEFRAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\btoday'?s?\b|\u4eca\u5929\b", re.I), "today"),
    (re.compile(r"\bthis\s+week\b|\u672c\u5468\b|\u8fd9\u5468\b", re.I), "this_week"),
    (
        re.compile(
            r"\blast\s*7\s*days?\b|\u8fc7\u53bb\s*7\s*\u5929\b|\u8fd1\u4e03\u5929\b",
            re.I,
        ),
        "last_7_days",
    ),
    (re.compile(r"\bthis\s+month\b|\u672c\u6708\b", re.I), "this_month"),
    (
        re.compile(
            r"\blatest\b|\brecent\b|\bmost\s+recent\b|\u6700\u65b0\b|\u8fd1\u671f\b",
            re.I,
        ),
        "latest",
    ),
)

_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bwhat\s+(?:shipped|launched|released|dropped|happened)\s+in\s+(.+?)"
        r"(?:\s+(?:this|last|the\s+last)\s+(?:week|month)|\s+today)?\s*\??$",
        re.I,
    ),
    re.compile(r"\btrending\s+(.+?)\s+(?:repos?\s+)?on\s+github\b", re.I),
    re.compile(r"\bsummar(?:y|ize|ise)\s+(?:the\s+)?(.+?)\s*\??$", re.I),
    re.compile(r"\b(?:news|updates?|releases?)\s+(?:about|on|in)\s+(.+?)\s*\??$", re.I),
    re.compile(
        r"\u5173\u4e8e\s*(.+?)\s*\u7684(?:\u6700\u65b0|\u65b0\u95fb|\u8fdb\u5c55)"
        r"\s*[\uff1f?]?$"
    ),
)

_PER_SOURCE_COUNT = re.compile(
    r"\b(\d{1,2})\s*(?:items?\s+)?(?:per|each\s+per|for\s+each)\s+source\b"
    r"|\u6bcf\u4e2a\u6765\u6e90\s*(\d{1,2})\s*[\u6761\u4e2a]?",
    re.I,
)

_SOURCE_WORDS = (
    ("juya", re.compile(r"\bjuya\b|\u65e9\u62a5\b", re.I)),
    ("github", re.compile(r"\bgithub\b", re.I)),
    ("huggingface", re.compile(r"\bhugging\s*face\b|\bhuggingface\b", re.I)),
    ("zhihu", re.compile(r"\bzhihu\b|\u77e5\u4e4e\b", re.I)),
    ("bilibili", re.compile(r"\bbilibili\b|B\u7ad9\b", re.I)),
)

_HF_PURPOSE = re.compile(
    r"\btrending\s+(?:\w+\s+)?models?\b|\b(?:popular|downloads?|likes?)\b"
    r"|\u6a21\u578b\u699c\b|\u70ed\u95e8\u6a21\u578b\b",
    re.I,
)
_GITHUB_PURPOSE = re.compile(
    r"\brepos?\b|\brepositor(?:y|ies)\b|\btooling\b|\bopen[- ]source\s+projects?\b"
    r"|\u5de5\u5177\b",
    re.I,
)
_RELEASE_PURPOSE = re.compile(
    r"\bshipped\b|\blaunched\b|\breleased\b|\breleases?\b|\bnews\b|\bbulletin\b"
    r"|\bdigest\b|\bsummar(?:y|ize|ise)\b|\u65e9\u62a5\b|\u53d1\u5e03\b"
    r"|\u4e0a\u7ebf\b|\u603b\u7ed3\b",
    re.I,
)

_TRAILING_FILLER = re.compile(
    r"\s+(?:for\s+(?:a\s+)?beginner(?:s)?|for\s+newcomers?|beginner[- ]friendly"
    r"|in\s+simple\s+terms)\b.*$|"
    r"\s*(?:for\s+(?:a\s+)?beginner(?:s)?)\s*$",
    re.I,
)
_AUDIENCE = re.compile(
    r"\bfor\s+(?:a\s+)?beginner(?:s)?\b|\bfor\s+newcomers?\b|\bbeginner[- ]friendly\b"
    r"|\bin\s+simple\s+terms\b|\u521d\u5b66\u8005\b|\u5165\u95e8\b",
    re.I,
)
_SOURCE_NAME_IN_TOPIC = re.compile(
    r"\b(?:juya|github|hugging\s*face|huggingface|zhihu|bilibili)\b", re.I
)
_TOPIC_TAIL = re.compile(
    r"\s+(?:news|digest|bulletin|updates?|\u65e9\u62a5|\u65e5\u62a5|\u5468\u62a5)$",
    re.I,
)
_TOPIC_HEAD = re.compile(r"^(?:the\s+)?(?:latest|recent|newest|most\s+recent)\s+", re.I)

_BOUNDED_TIMEFRAMES = frozenset({"today", "this_week", "last_7_days", "this_month"})
#: Periods that must exclude older items; a plain "today's digest" stays a generic ask.
_STRICT_TIMEFRAMES = frozenset({"this_week", "last_7_days", "this_month"})
_ALLOWED_TIMEFRAMES = _BOUNDED_TIMEFRAMES | {"latest"}

_REFERENCES_DIGEST = re.compile(
    r"\b(?:item|entry|story|rank|number|#)\s*\d+\b"
    r"|\b(?:the\s+)?(?:first|second|third|fourth|fifth)\s+(?:one|item|entry|story)\b"
    r"|\b(?:that|those|this\s+digest|the\s+digest|the\s+results?)\b"
    r"|\bmore\s+detail\b|\bgo\s+deeper\b"
    r"|\bbeginner[- ]friendly\b|\bsimpler\b|\brephrase\b"
    r"|\b(?:explain|summarize)\s+(?:it|that|this)\b",
    re.I,
)

_GENERAL_QUESTION = re.compile(
    r"^(?:what(?:'s|\s+is|\s+are)\b|how\s+(?:do|does|can|should|to)\b"
    r"|why\s+(?:do|does|is|are|would)\b|define\b|explain\b"
    r"|\u4ec0\u4e48\u662f|\u5982\u4f55|\u4e3a\u4ec0\u4e48)",
    re.I,
)
_VAGUE_TOPIC = re.compile(
    r"^(?:tell\s+me\s+about|what\s+about|any\s+(?:info|information|news)\s+(?:on|about)"
    r"|\u8bf4\u8bf4|\u4ecb\u7ecd\u4e00\u4e0b)\s*(.+?)\s*\??$",
    re.I,
)

_ANSWER_RECENT = re.compile(
    r"\b(?:recent|latest|newer|updates?|news|what'?s\s+new)\b"
    r"|\u6700\u65b0|\u8fd1\u671f|\u65b0\u95fb|\u8fdb\u5c55",
    re.I,
)
_ANSWER_GENERAL = re.compile(
    r"\b(?:general|explanation|explain|background|overview|what\s+it\s+is)\b"
    r"|\u89e3\u91ca|\u4ecb\u7ecd|\u80cc\u666f",
    re.I,
)
_REFRESH = re.compile(
    r"\brefresh\b|\brun\s+(?:it|that)\s+again\b|\bcheck\s+again\b"
    r"|\bupdate\s+(?:it|that|the\s+digest)\b"
    r"|\u518d(?:\u6765|\u8dd1)\u4e00\u6b21|\u5237\u65b0",
    re.I,
)

_CLARIFY_GUIDANCE = (
    'Ask about a topic, for example: "Give me today\'s AI digest".'
)


@dataclass(frozen=True)
class ConversationContext:
    """What the browser conversation already carries when a message arrives."""

    has_digest: bool = False
    pending: dict[str, Any] | None = None
    last_request: dict[str, Any] | None = None
    connector_names: list[str] | None = None


@dataclass(frozen=True)
class ConversationDecision:
    """One routed outcome for a browser message."""

    intent: Literal["digest", "followup", "general", "clarify"]
    request: DigestRequest | None = None
    question: str | None = None
    clarification: str | None = None
    pending: dict[str, Any] | None = None


def _timeframe_from_text(text: str) -> str | None:
    for pattern, label in _TIMEFRAME_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _topic_from_text(text: str) -> str | None:
    for pattern in _TOPIC_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        topic = match.group(1).strip(" .,:;")
        if topic:
            return topic
    return None


def _clean_topic(topic: str) -> str | None:
    cleaned = _TRAILING_FILLER.sub("", topic).strip(" .,:;")
    cleaned = _SOURCE_NAME_IN_TOPIC.sub(" ", cleaned)
    cleaned = _TOPIC_TAIL.sub("", cleaned.strip())
    cleaned = _TOPIC_HEAD.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")
    return cleaned or None


def _explicit_sources(text: str) -> list[str] | None:
    names = [name for name, pattern in _SOURCE_WORDS if pattern.search(text)]
    if not names:
        return None
    return normalize_source_names(names)


def _infer_sources(text: str) -> list[str]:
    if _HF_PURPOSE.search(text):
        return ["huggingface"]
    if _GITHUB_PURPOSE.search(text):
        return ["github"]
    explicit = _explicit_sources(text)
    if explicit is not None:
        return explicit
    if _RELEASE_PURPOSE.search(text):
        return ["juya"]
    return ["juya"]


def _digest_decision(text: str, *, context: ConversationContext) -> ConversationDecision:
    parsed = parse_digest_intent(text)
    explicit_selectors = parsed.has_explicit_selectors()
    topic = None if explicit_selectors else _topic_from_text(text)
    timeframe = _timeframe_from_text(text) or parsed.timeframe
    explicit = _explicit_sources(text)
    if explicit_selectors:
        sources = list(resolve_digest_request(text).connector_names or ["juya"])
    else:
        sources = explicit or _infer_sources(text)
        if context.connector_names and explicit is None:
            sources = normalize_source_names(context.connector_names)
    topics = [topic] if topic else []
    if topic is not None:
        cleaned = _clean_topic(topic)
        topics = [cleaned] if cleaned else []
    count_match = _PER_SOURCE_COUNT.search(text)
    per_source = None
    if count_match is not None:
        raw_count = count_match.group(1) or count_match.group(2)
        per_source = max(1, min(20, int(raw_count)))
    request = DigestRequest(
        topics=topics or parsed.topics,
        topics_are_filters=bool(topics),
        strict_timeframe=timeframe in _STRICT_TIMEFRAMES,
        timeframe=timeframe,
        items_per_source=per_source,
        output_language=parsed.output_language,
        audience="beginner" if _AUDIENCE.search(text) else None,
        github_manual_urls=list(parsed.github_manual_urls),
        github_target_channels=list(parsed.github_target_channels),
        bilibili_manual_urls=list(parsed.bilibili_manual_urls),
        bilibili_target_channels=list(parsed.bilibili_target_channels),
        juya_manual_urls=list(parsed.juya_manual_urls),
        manual_urls=list(parsed.manual_urls),
        target_channels=list(parsed.target_channels),
        connector_names=sources,
        primary_source=sources[0] if sources else None,
    )
    return ConversationDecision(intent="digest", request=request)


def _validated_topics(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    topics: list[str] = []
    for raw in value[:5]:
        if not isinstance(raw, str):
            continue
        topic = raw.strip()
        if topic:
            topics.append(topic[:80])
    return topics


def _validated_sources(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names = [
        str(raw).strip().lower()
        for raw in value
        if isinstance(raw, str) and str(raw).strip().lower() in ALLOWED_SOURCES
    ]
    return normalize_source_names(names) if names else []


def _validated_timeframe(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    label = value.strip().lower()
    return label if label in _ALLOWED_TIMEFRAMES else None


def _validated_language(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    label = value.strip()
    if label in {"en", "zh-CN", "zh"}:
        return "zh-CN" if label == "zh" else label
    return None


def _validated_count(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return max(1, min(20, value))


def _model_decision(
    text: str,
    *,
    context: ConversationContext,
    model: Any,
) -> ConversationDecision | None:
    interpret = getattr(model, "interpret_conversation", None)
    if interpret is None or not callable(interpret):
        return None
    try:
        raw = interpret(
            {
                "message": text,
                "has_digest": context.has_digest,
                "pending_clarification": context.pending,
                "last_request": context.last_request,
                "session_sources": context.connector_names,
            }
        )
    except Exception:  # noqa: BLE001 - a model failure must not collect
        return None
    if not isinstance(raw, dict):
        return None

    intent = raw.get("intent")
    if intent == "digest":
        topics = _validated_topics(raw.get("topics"))
        timeframe = _validated_timeframe(raw.get("timeframe"))
        sources = _validated_sources(raw.get("sources")) or _infer_sources(text)
        if context.connector_names and not raw.get("sources"):
            sources = normalize_source_names(context.connector_names)
        request = DigestRequest(
            topics=topics,
            topics_are_filters=bool(topics),
            strict_timeframe=timeframe in _STRICT_TIMEFRAMES,
            timeframe=timeframe,
            items_per_source=_validated_count(raw.get("items_per_source")),
            output_language=_validated_language(raw.get("language")),
            audience="beginner" if raw.get("audience") == "beginner" else None,
            connector_names=sources,
            primary_source=sources[0] if sources else None,
        )
        return ConversationDecision(intent="digest", request=request)

    if intent == "followup":
        return ConversationDecision(intent="followup")

    if intent == "general":
        question = raw.get("question")
        if not isinstance(question, str) or not question.strip():
            question = text
        return ConversationDecision(intent="general", question=question.strip())

    if intent == "clarify":
        clarification = raw.get("clarification")
        if not isinstance(clarification, str) or not clarification.strip():
            return None
        return ConversationDecision(
            intent="clarify",
            clarification=clarification.strip()[:400],
            pending={"message": text, "topic": raw.get("topic") or ""},
        )
    return None


def _fallback_decision(text: str, context: ConversationContext) -> ConversationDecision:
    if context.has_digest:
        return ConversationDecision(intent="followup")
    return ConversationDecision(intent="general", question=text)


def request_metadata(request: DigestRequest) -> dict[str, Any]:
    """Public, user-relevant options of one resolved digest request."""
    return {
        "sources": list(request.connector_names or []),
        "per_source": request.items_per_source,
        "timeframe": request.timeframe,
        "topics": list(request.topics or []),
        "language": request.output_language,
        "audience": request.audience,
    }


def request_payload(request: DigestRequest) -> dict[str, Any]:
    """Full request, stored so a later refresh can repeat it exactly."""
    return {field.name: getattr(request, field.name) for field in fields(DigestRequest)}


def request_from_payload(payload: object) -> DigestRequest | None:
    """Rebuild a stored request; unknown or invalid payloads yield ``None``."""
    if not isinstance(payload, dict):
        return None
    known = {field.name for field in fields(DigestRequest)}
    kwargs = {key: value for key, value in payload.items() if key in known}
    try:
        return DigestRequest(**kwargs)
    except (TypeError, ValueError):
        return None


def _resume_decision(
    answer: str,
    pending: dict[str, Any],
    *,
    context: ConversationContext,
) -> ConversationDecision | None:
    original = str(pending.get("message") or "").strip()
    topic = str(pending.get("topic") or "").strip()
    if not original:
        return None
    if _ANSWER_RECENT.search(answer):
        base = _digest_decision(f"{original} {answer}", context=context)
        if topic and base.request is not None:
            return ConversationDecision(
                intent="digest",
                request=replace(
                    base.request,
                    topics=[topic],
                    topics_are_filters=True,
                ),
            )
        return base
    if _ANSWER_GENERAL.search(answer):
        question = original if not topic else f"Explain {topic}"
        return ConversationDecision(intent="general", question=question)
    return None


def interpret_message(
    message: str,
    *,
    context: ConversationContext | None = None,
    model: Any | None = None,
) -> ConversationDecision:
    """Interpret one browser message; see the plan's conversation rules."""
    text = message.strip()
    if not text:
        return ConversationDecision(intent="clarify", clarification=_CLARIFY_GUIDANCE)
    ctx = context or ConversationContext()
    if is_structured_followup(text):
        return ConversationDecision(intent="followup")
    if ctx.pending:
        resumed = _resume_decision(text, ctx.pending, context=ctx)
        if resumed is not None:
            return resumed
    if _REFRESH.search(text):
        stored = request_from_payload(ctx.last_request)
        if stored is not None:
            return ConversationDecision(intent="digest", request=stored)
        return ConversationDecision(intent="followup")
    if _REFERENCES_DIGEST.search(text):
        return ConversationDecision(intent="followup")
    if _RELEASE_PURPOSE.search(text) or _topic_from_text(text) is not None:
        return _digest_decision(text, context=ctx)
    if _GENERAL_QUESTION.search(text) and not ctx.has_digest:
        return ConversationDecision(intent="general", question=text)
    vague = _VAGUE_TOPIC.search(text)
    if vague is not None:
        topic = vague.group(1).strip(" .,:;")
        return ConversationDecision(
            intent="clarify",
            clarification=(
                f"Do you want recent {topic} updates, or a general explanation of {topic}?"
            ),
            pending={"message": text, "topic": topic},
        )
    if model is not None:
        decision = _model_decision(text, context=ctx, model=model)
        if decision is not None:
            return decision
    return _fallback_decision(text, ctx)
