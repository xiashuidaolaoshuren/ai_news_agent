"""Decode model output into validated digest fields.

Models occasionally wrap the JSON object in prose, a code fence, or reasoning
markers, and a truncated response must never surface as user-visible summary
text. This module is the single place that turns raw model text into the four
digest fields, so the live path and saved-digest projection agree.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

DIGEST_FIELD_KEYS = (
    "summary",
    "why_it_matters",
    "background_knowledge",
    "follow_up_action",
)

#: Reasoning markers some providers emit before the answer.
_REASONING_MARKERS = (
    "<｜end▁of▁thinking｜>",
    "<|end_of_thinking|>",
    "</thinking>",
)

_EMPTY_FIELDS: dict[str, str] = {
    "summary": "",
    "why_it_matters": "",
    "background_knowledge": "",
    "follow_up_action": "",
}


def empty_digest_fields() -> dict[str, str]:
    """Fields that let the caller fall back to safe metadata-only text."""
    return dict(_EMPTY_FIELDS)


def extract_digest_fields(raw: str | None) -> dict[str, str]:
    """Return validated digest fields, or empty fields when nothing is usable.

    Never returns the raw response text. A complete object is recovered from a
    fenced block or from surrounding commentary; truncated or wrongly typed
    output is discarded so the caller can use its own fallback.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return empty_digest_fields()
    for payload in _json_objects(_strip_reasoning(text)):
        fields = _validated_fields(payload)
        if fields is not None:
            return fields
    return empty_digest_fields()


def extract_json_object(raw: str | None) -> dict[str, Any]:
    """Return the first complete JSON object in model output, else ``{}``."""
    text = "" if raw is None else str(raw).strip()
    if not text:
        return {}
    for payload in _json_objects(_strip_reasoning(text)):
        return payload
    return {}


def _strip_reasoning(text: str) -> str:
    cut = -1
    matched = ""
    for marker in _REASONING_MARKERS:
        index = text.rfind(marker)
        if index > cut:
            cut = index
            matched = marker
    if cut == -1:
        return text
    return text[cut + len(matched) :]


def _json_objects(text: str) -> Iterator[dict[str, Any]]:
    """Yield every decodable JSON object, ignoring surrounding prose."""
    decoder = json.JSONDecoder()
    index = text.find("{")
    while index != -1:
        try:
            decoded, end = decoder.raw_decode(text, index)
        except ValueError:
            index = text.find("{", index + 1)
            continue
        if isinstance(decoded, dict):
            yield decoded
        index = text.find("{", end)


def _validated_fields(payload: dict[str, Any]) -> dict[str, str] | None:
    fields: dict[str, str] = {}
    for key in DIGEST_FIELD_KEYS:
        value = payload.get(key, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            return None
        fields[key] = value.strip()
    if not fields["summary"]:
        return None
    return fields
