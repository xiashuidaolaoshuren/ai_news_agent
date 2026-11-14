"""Zhihu practitioner-insight card helpers for structured rank follow-up."""

from __future__ import annotations

from ai_news_agent.card_labels import legacy_card_lang, text
from ai_news_agent.models import DigestEntry, NewsItem

__all__ = [
    "format_zhihu_practitioner_insight_card",
]


def format_zhihu_practitioner_insight_card(
    entry: DigestEntry,
    news_item: NewsItem | None,
    *,
    rank: int,
) -> str:
    """Render a sectioned practitioner-insight card in the entry's language."""
    lang = legacy_card_lang(entry.language, entry.source_kind)
    heading = f"### {text(lang, 'story_heading', rank=rank, title=entry.title)}"
    if news_item is None:
        return "\n\n".join(
            [
                heading,
                _section(text(lang, "notes_heading"), [text(lang, "zhihu_thin_card")]),
                _section(text(lang, "original_link"), [_original_link(entry, lang)]),
            ]
        )
    evidence = news_item.source_evidence
    blocks: list[str] = []
    eyebrow = _eyebrow(news_item, lang)
    if eyebrow:
        blocks.append(eyebrow)
    blocks.append(heading)
    notes: list[str] = []
    if not _has_substantive_evidence(news_item, evidence):
        notes.append(text(lang, "zhihu_thin_card"))
    else:
        if entry.summary:
            blocks.append(f"> **{text(lang, 'summary_label')}** {entry.summary}")
        if entry.why_it_matters:
            blocks.append(f"**{text(lang, 'zhihu_why')}** {entry.why_it_matters}")
        if news_item.raw_snippet:
            blocks.append(
                _section(text(lang, "excerpt_heading"), [_quote(news_item.raw_snippet)])
            )
        relevance = evidence.get("relevance")
        if relevance:
            notes.append(text(lang, "relevance_line", value=relevance))
        notes.append(text(lang, "zhihu_freshness"))
    if notes:
        blocks.append(_section(text(lang, "notes_heading"), [f"- {note}" for note in notes]))
    blocks.append(_section(text(lang, "original_link"), [_original_link(entry, lang)]))
    return "\n\n".join(blocks)


def _eyebrow(news_item: NewsItem, lang: str) -> str:
    parts: list[str] = []
    lens = news_item.source_evidence.get("query_lens")
    if lens:
        parts.append(text(lang, "lens_line", value=lens))
    author_source = _author_source_line(news_item, lang)
    if author_source:
        parts.append(author_source)
    return " · ".join(parts)


def _author_source_line(news_item: NewsItem, lang: str) -> str:
    author = news_item.author
    source_label = news_item.source_evidence.get("source_label")
    if author and source_label:
        return text(lang, "author_source_both", author=author, source=source_label)
    if author:
        return text(lang, "author_source_one", value=author)
    if source_label:
        return text(lang, "author_source_one", value=source_label)
    return ""


def _original_link(entry: DigestEntry, lang: str) -> str:
    return f"- [{text(lang, 'zhihu_original')}]({entry.source_url})"


def _section(title: str, lines: list[str]) -> str:
    return f"#### {title}\n\n" + "\n".join(lines)


def _quote(body: str) -> str:
    return "\n".join(f"> {line}" if line.strip() else ">" for line in body.splitlines())


def _has_substantive_evidence(news_item: NewsItem, evidence: dict[str, object]) -> bool:
    if news_item.raw_snippet:
        return True
    if evidence.get("relevance"):
        return True
    return False
