"""Shared topic matching for connectors that filter on request topics."""

from __future__ import annotations

import re

#: Common AI vocabulary bridged across English requests and Chinese bulletin text.
_TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "model": ("\u6a21\u578b",),
    "models": ("\u6a21\u578b",),
    "open": ("\u5f00\u6e90", "\u5f00\u653e"),
    "weight": ("\u6743\u91cd",),
    "weights": ("\u6743\u91cd",),
    "open-weight": ("\u5f00\u6e90", "\u5f00\u653e\u6743\u91cd"),
    "open-weights": ("\u5f00\u6e90", "\u5f00\u653e\u6743\u91cd"),
    "open-source": ("\u5f00\u6e90",),
    "agent": ("\u667a\u80fd\u4f53", "agent"),
    "agents": ("\u667a\u80fd\u4f53", "agent"),
    "tool": ("\u5de5\u5177",),
    "tooling": ("\u5de5\u5177",),
    "release": ("\u53d1\u5e03", "\u4e0a\u7ebf"),
    "released": ("\u53d1\u5e03", "\u4e0a\u7ebf"),
    "launch": ("\u53d1\u5e03", "\u4e0a\u7ebf"),
    "video": ("\u89c6\u9891",),
}
_TOPIC_STOPWORDS = frozenset({"the", "a", "an", "of", "for", "in", "on", "and", "to"})


def text_matches_topic(text: str, topic: str) -> bool:
    haystack = text.casefold()
    token_groups: list[tuple[str, ...]] = []
    for token in re.split(r"[\s\-]+", topic.casefold()):
        if not token or token in _TOPIC_STOPWORDS:
            continue
        aliases = _TOPIC_ALIASES.get(token) or _TOPIC_ALIASES.get(token.rstrip("s"))
        token_groups.append(aliases or (token,))
    if not token_groups:
        return False
    return all(any(alt.casefold() in haystack for alt in group) for group in token_groups)


__all__ = ["text_matches_topic"]
