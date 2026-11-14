"""Hugging Face family-card helpers for structured rank follow-up."""

from __future__ import annotations

import re

from ai_news_agent.card_labels import legacy_card_lang, text
from ai_news_agent.huggingface_model_card import normalize_model_card_snippet
from ai_news_agent.models import DigestEntry, NewsItem
from ai_news_agent.rendering import _escape_markdown_inline

__all__ = [
    "format_huggingface_family_card",
]

_FIELD_SEP = " — "

_NOT_SAVED = "Not saved"


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
    """Render a family card from persisted digest evidence, in the entry's language."""
    lang = legacy_card_lang(entry.language, entry.source_kind)
    lines = [
        _eyebrow(entry, news_item, rank, lang),
        "",
        f"### {text(lang, 'family_heading', title=entry.title)}",
    ]
    if news_item is None:
        lines.append(text(lang, "missing_evidence"))
        lines.extend(_source_section(entry, lang))
        return "\n".join(lines).rstrip()
    evidence = news_item.source_evidence
    if not _has_hub_stats_or_snippet(news_item, evidence):
        also = _also_column(evidence)
        if also:
            lines.append(_also_line(also, lang))
        lines.append(text(lang, "missing_evidence"))
        lines.extend(_source_section(entry, lang))
        return "\n".join(lines).rstrip()
    trending = evidence.get("trending_score")
    downloads_30d = evidence.get("downloads_30d")
    likes = evidence.get("likes")
    pipeline_tag = evidence.get("pipeline_tag")
    columns = [
        (text(lang, "col_trending"), trending),
        (text(lang, "col_downloads"), downloads_30d),
        (text(lang, "col_likes"), likes),
        (text(lang, "col_pipeline"), pipeline_tag),
    ]
    if targeted:
        lines.extend(
            _stats_table(
                [(label, value if value else _NOT_SAVED) for label, value in columns],
                lang,
            )
        )
    else:
        present = [(label, value) for label, value in columns if value]
        if present:
            lines.extend(_stats_table(present, lang))
    also = _also_column(evidence)
    if also:
        lines.append(_also_line(also, lang))
    snippet = _display_snippet(news_item.raw_snippet or "", entry.source_url)
    if snippet:
        lines.extend(
            (
                "",
                f"#### {text(lang, 'from_model_card')}",
                _blockquote(_demote_headings(snippet)),
            )
        )
    caveats: list[str] = []
    if _has_hub_stats_or_snippet(news_item, evidence):
        caveats.append(text(lang, "hf_popularity"))
    if saved_with_digest and snippet:
        caveats.append(text(lang, "saved_snippet"))
    elif evidence.get("model_card_live_fetched") and snippet:
        caveats.append(text(lang, "live_snippet"))
    if model_card_unavailable:
        caveats.append(text(lang, "model_card_unavailable"))
    if caveats:
        lines.extend(
            (
                "",
                f"#### {text(lang, 'reading_numbers')}",
                *(f"- {c}" for c in caveats),
            )
        )
    if targeted and related_display_ranks:
        lines.extend(
            (
                "",
                f"#### {text(lang, 'related')}",
                " · ".join(f"#{r}" for r in related_display_ranks),
            )
        )
    lines.extend(_source_section(entry, lang))
    return "\n".join(lines).rstrip()


def _field_line(label: str, value: object) -> str:
    return f"{label}{_FIELD_SEP}{_escape_markdown_inline(str(value))}"


def _eyebrow(entry: DigestEntry, news_item: NewsItem | None, rank: int, lang: str) -> str:
    """Rank, publisher and pipeline on one line, as the prototype's eyebrow."""
    publisher = news_item.author if news_item is not None and news_item.author else None
    if publisher is None and "/" in entry.source_id:
        publisher = entry.source_id.split("/", 1)[0]
    parts = [text(lang, "rank", rank=rank)]
    if publisher:
        parts.append(_escape_markdown_inline(publisher))
    pipeline = (
        news_item.source_evidence.get("pipeline_tag")
        if news_item is not None
        else None
    )
    if pipeline:
        parts.append(_escape_markdown_inline(str(pipeline)))
    return " · ".join(parts)


def _stats_table(columns: list[tuple[str, object]], lang: str) -> list[str]:
    """One-row Hub stats table under its own heading."""
    header = " | ".join(label for label, _ in columns)
    divider = " | ".join("---" for _ in columns)
    row = " | ".join(_stat_cell(value, lang) for _, value in columns)
    return [
        "",
        f"#### {text(lang, 'hub_stats')}",
        f"| {header} |",
        f"| {divider} |",
        f"| {row} |",
    ]


def _stat_cell(value: object, lang: str) -> str:
    if value == _NOT_SAVED:
        return text(lang, "not_saved")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:g}"
    return f"`{_escape_markdown_inline(str(value))}`" if isinstance(value, str) else str(value)


_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")


def _demote_headings(text: str) -> str:
    """Turn README headings into bold lines so they do not outrank the card's own headings."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        match = None if in_fence else _HEADING_LINE.match(line)
        out.append(f"**{match.group(1)}**" if match and match.group(1) else line)
    return "\n".join(out)


def _blockquote(text: str) -> str:
    """Quote every line, including blank lines, so the block stays one quote."""
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.splitlines())


def _also_line(also: str, lang: str) -> str:
    return f"**{text(lang, 'also')}** {_escape_markdown_inline(also)}"


def _source_section(entry: DigestEntry, lang: str) -> list[str]:
    page = text(lang, "model_page", source_id=entry.source_id)
    return [
        "",
        f"#### {text(lang, 'source')}",
        f"- [hf.co]({entry.source_url}) · {page}",
    ]


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
    return " · ".join(titles)


def _has_hub_stats_or_snippet(news_item: NewsItem | None, evidence: dict[str, object]) -> bool:
    if news_item is not None and news_item.raw_snippet:
        return True
    for key in ("trending_score", "downloads_30d", "likes", "pipeline_tag"):
        if evidence.get(key):
            return True
    return False
