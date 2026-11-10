"""Hugging Face family-card helpers for structured rank follow-up."""

from __future__ import annotations

from ai_news_agent.huggingface_model_card import normalize_model_card_snippet
from ai_news_agent.models import DigestEntry, NewsItem
from ai_news_agent.rendering import _escape_markdown_inline

__all__ = [
    "format_huggingface_family_card",
]

_FIELD_SEP = " — "

_POPULARITY_CAVEAT = (
    "Hub trending reflects popularity, not model quality or fitness for your use case."
)
_MISSING_EVIDENCE_CAVEAT = (
    "Hub stats and card snippet are not available for this saved item."
)
_LIVE_SNIPPET_CAVEAT = (
    "Snippet is from a live Hub model card fetched after digest time; "
    "Trending, Downloads, and Likes remain digest-time values."
)
_SAVED_WITH_DIGEST_SNIPPET_CAVEAT = (
    "Snippet is from the model card saved with this digest."
)
_NOT_SAVED = "Not saved"
_MODEL_CARD_UNAVAILABLE_CAVEAT = (
    "Live Hub model card was unavailable; showing digest-time evidence only."
)


def format_huggingface_family_card(
    entry: DigestEntry,
    news_item: NewsItem | None,
    *,
    rank: int,
    model_card_unavailable: bool = False,
    targeted: bool = False,
    saved_with_digest: bool = False,
    related_display_ranks: list[int] | None = None,
) -> str:
    """Render an English family card from persisted digest evidence."""
    lines = [
        _field_line(f"Rank {rank}", entry.title),
        _field_line("Link", entry.source_url),
    ]
    if news_item is None:
        lines.append(_MISSING_EVIDENCE_CAVEAT)
        return "\n".join(lines).rstrip()
    evidence = news_item.source_evidence
    if not _has_hub_stats_or_snippet(news_item, evidence):
        also = _also_column(evidence)
        if also:
            lines.append(_field_line("Also", also))
        lines.append(_MISSING_EVIDENCE_CAVEAT)
        return "\n".join(lines).rstrip()
    trending = evidence.get("trending_score")
    downloads_30d = evidence.get("downloads_30d")
    likes = evidence.get("likes")
    pipeline_tag = evidence.get("pipeline_tag")
    if targeted:
        lines.append(
            _field_line("Trending", trending if trending else _NOT_SAVED)
        )
        lines.append(
            _field_line(
                "Downloads (30d)",
                downloads_30d if downloads_30d else _NOT_SAVED,
            )
        )
        lines.append(_field_line("Likes", likes if likes else _NOT_SAVED))
        lines.append(
            _field_line("Pipeline", pipeline_tag if pipeline_tag else _NOT_SAVED)
        )
    else:
        if trending:
            lines.append(_field_line("Trending", trending))
        if downloads_30d:
            lines.append(_field_line("Downloads (30d)", downloads_30d))
        if likes:
            lines.append(_field_line("Likes", likes))
        if pipeline_tag:
            lines.append(_field_line("Pipeline", pipeline_tag))
    also = _also_column(evidence)
    if also:
        lines.append(_field_line("Also", also))
    if news_item.author:
        lines.append(_field_line("Publisher", news_item.author))
    snippet = _display_snippet(news_item.raw_snippet or "", entry.source_url)
    if snippet:
        lines.extend(("", f"Snippet{_FIELD_SEP}", "", snippet))
    if targeted and related_display_ranks:
        ranks = ", ".join(f"#{r}" for r in related_display_ranks)
        lines.append(_field_line("Related", ranks))
    caveats: list[str] = []
    if saved_with_digest and snippet:
        caveats.append(_SAVED_WITH_DIGEST_SNIPPET_CAVEAT)
    elif evidence.get("model_card_live_fetched") and snippet:
        caveats.append(_LIVE_SNIPPET_CAVEAT)
    if model_card_unavailable:
        caveats.append(_MODEL_CARD_UNAVAILABLE_CAVEAT)
    if _has_hub_stats_or_snippet(news_item, evidence):
        caveats.append(_POPULARITY_CAVEAT)
    if caveats:
        lines.extend(("", *caveats))
    return "\n".join(lines).rstrip()


def _field_line(label: str, value: object) -> str:
    return f"{label}{_FIELD_SEP}{_escape_markdown_inline(str(value))}"


def _display_snippet(raw: str, source_url: str) -> str:
    """Return snippet text safe for chat markdown."""
    if not raw.strip():
        return ""
    return normalize_model_card_snippet(raw, source_url=source_url)


def _also_column(evidence: dict[str, object]) -> str:
    variants = evidence.get("family_variants")
    if not isinstance(variants, list):
        return ""
    titles: list[str] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        title = str(variant.get("title", variant.get("source_id", ""))).strip()
        if title:
            titles.append(title)
    return ", ".join(titles)


def _has_hub_stats_or_snippet(news_item: NewsItem | None, evidence: dict[str, object]) -> bool:
    if news_item is not None and news_item.raw_snippet:
        return True
    for key in ("trending_score", "downloads_30d", "likes", "pipeline_tag"):
        if evidence.get(key):
            return True
    return False
