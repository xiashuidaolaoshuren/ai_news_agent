"""Link digest entries that confidently name the same model or product (B5)."""

from __future__ import annotations

import re

from ai_news_agent.models import DigestEntry, NewsItem

_VARIANT_TOKENS: frozenset[str] = frozenset(
    {
        "flash",
        "pro",
        "lite",
        "mini",
        "coder",
        "base",
        "plus",
        "max",
        "instruct",
        "chat",
    }
)
_VERSION_RE = re.compile(r"m\d+(?:\.\d+)?|v\d+(?:\.\d+)?|\d+\.\d+", re.IGNORECASE)
_SIZE_RE = re.compile(r"\d+b", re.IGNORECASE)


def related_display_ranks(
    entries: list[tuple[DigestEntry, NewsItem | None]],
) -> dict[int, list[int]]:
    """Map each 1-based display rank to other ranks with the same identity signature."""
    signatures: dict[int, tuple[str, ...]] = {}
    for index, (entry, news_item) in enumerate(entries, start=1):
        sig = _identity_signature(entry.title, news_item)
        if sig is not None:
            signatures[index] = sig

    related: dict[int, list[int]] = {}
    for rank in range(1, len(entries) + 1):
        sig = signatures.get(rank)
        if sig is None:
            related[rank] = []
            continue
        siblings = sorted(
            other
            for other, other_sig in signatures.items()
            if other != rank and other_sig == sig
        )
        related[rank] = siblings
    return related


def _identity_signature(title: str, news_item: NewsItem | None) -> tuple[str, ...] | None:
    text = (title or "").strip()
    if not text and news_item is not None:
        text = (news_item.title or "").strip()
    if not text:
        return None

    lower = text.lower()
    tokens: list[str] = []
    for match in _VERSION_RE.finditer(lower):
        tokens.append(match.group(0).lower())
    for match in _SIZE_RE.finditer(lower):
        tok = match.group(0).lower()
        if tok not in tokens:
            tokens.append(tok)
    for word in re.findall(r"[a-z]+", lower):
        if word in _VARIANT_TOKENS and word not in tokens:
            tokens.append(word)
    if not tokens:
        return None
    return tuple(tokens)


__all__ = ["related_display_ranks"]

