"""Link digest entries that confidently name the same model or product (B5).

The identity signature is the product name plus its version, parameter size, and
product variant tokens; entries link only when the whole signature matches. Titles
with extra descriptive words ("Introducing Qwen3.8-27B") therefore do not link to
the plain name: uncertain overlap produces no link, by design.
"""

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
# A standalone short number: the start of a version ("Gemini 4"). Glued to letters
# ("qwen2", "8b") or a dotted number it is not one.
_BARE_VERSION_RE = re.compile(r"(?<![\w.])\d{1,3}(?![\w.])")
_SIZE_RE = re.compile(r"\d+b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")


def related_display_ranks(
    entries: list[tuple[DigestEntry, NewsItem | None]],
) -> dict[int, list[int]]:
    """Map each 1-based display rank to other ranks with the same identity signature."""
    signatures: dict[int, tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {}
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


def _identity_signature(
    title: str, news_item: NewsItem | None
) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    text = (title or "").strip()
    if not text and news_item is not None:
        text = (news_item.title or "").strip()
    if not text:
        return None

    lower = text.lower()
    words = _WORD_RE.findall(lower)
    versions = tuple(sorted({match.group(0) for match in _VERSION_RE.finditer(lower)}))
    # A start of a version number ("Gemini 4"). Other numbers are not versions: a
    # year or a count would link unrelated titles.
    bare_versions = tuple(sorted({word for word in _BARE_VERSION_RE.findall(lower)}))
    if bare_versions:
        versions = tuple(sorted({*versions, *bare_versions}))
    sizes = tuple(sorted({match.group(0) for match in _SIZE_RE.finditer(lower)}))
    variants = tuple(sorted({word for word in words if word in _VARIANT_TOKENS}))
    if not versions and not sizes and not variants:
        return None

    residue = _SIZE_RE.sub(" ", _VERSION_RE.sub(" ", lower))
    product = " ".join(
        sorted(
            {word for word in _WORD_RE.findall(residue) if word not in _VARIANT_TOKENS}
        )
    )
    return (product, versions, sizes, variants)


__all__ = ["related_display_ranks"]

