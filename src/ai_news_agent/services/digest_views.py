"""Map saved digests to DigestView payloads (Milestone 8A.1 T11)."""

from __future__ import annotations

import re
from typing import Any

from ai_news_agent.digest_content import extract_digest_fields
from ai_news_agent.huggingface_families import family_key
from ai_news_agent.juya_content import clean_lead_title, is_image_url, split_linked_title
from ai_news_agent.models import Digest, DigestEntry, NewsItem, SourceKind

_RECOVERY_CAVEAT = "原摘要无法恢复，仅显示标题。"
_STRUCTURED_SUMMARY_RE = re.compile(r'"summary"\s*:', re.IGNORECASE)


def build_digest_view_payload(
    digest: Digest,
    *,
    news_items: list[NewsItem] | None = None,
) -> dict[str, Any]:
    """Map a saved digest and optional news evidence to a DigestView-shaped dict."""
    lookup = _news_items_by_key(news_items)
    related_by_rank = _huggingface_related_ranks_by_display_rank(
        digest,
        news_items=lookup,
    )
    entries = [
        _build_entry_payload(
            entry,
            display_rank=index,
            news_items=lookup,
            related_display_ranks=related_by_rank.get(index, []),
        )
        for index, entry in enumerate(digest.entries, start=1)
    ]
    return {
        "generated_at": digest.generated_at,
        "timeframe": digest.timeframe,
        "topics": list(digest.topics),
        "entries": entries,
    }


def _news_items_by_key(
    news_items: list[NewsItem] | None,
) -> dict[tuple[SourceKind, str], NewsItem]:
    if not news_items:
        return {}
    return {(item.source, item.source_id): item for item in news_items}


def huggingface_related_display_ranks(
    digest: Digest,
    *,
    news_items: list[NewsItem] | None,
    display_rank: int,
) -> list[int]:
    """Other HF entries in the same digest that share saved model identity."""
    lookup = _news_items_by_key(news_items)
    return _huggingface_related_ranks_by_display_rank(digest, news_items=lookup).get(
        display_rank,
        [],
    )


def _huggingface_related_ranks_by_display_rank(
    digest: Digest,
    *,
    news_items: dict[tuple[SourceKind, str], NewsItem],
) -> dict[int, list[int]]:
    keys_by_rank: dict[int, str] = {}
    for index, entry in enumerate(digest.entries, start=1):
        if entry.source_kind is not SourceKind.HUGGINGFACE:
            continue
        news_item = news_items.get((entry.source_kind, entry.source_id))
        if news_item is None:
            continue
        keys_by_rank[index] = family_key(news_item)

    related: dict[int, list[int]] = {}
    for rank, key in keys_by_rank.items():
        siblings = sorted(r for r, other in keys_by_rank.items() if other == key and r != rank)
        related[rank] = siblings
    return related


def _build_entry_payload(
    entry: DigestEntry,
    *,
    display_rank: int,
    news_items: dict[tuple[SourceKind, str], NewsItem],
    related_display_ranks: list[int] | None = None,
) -> dict[str, Any]:
    payload = _entry_common_fields(entry, display_rank=display_rank)
    news_item = news_items.get((entry.source_kind, entry.source_id))
    evidence = news_item.source_evidence if news_item is not None else {}

    if entry.source_kind is SourceKind.GITHUB:
        payload.update(extract_github_evidence(evidence, news_item))
    elif entry.source_kind is SourceKind.HUGGINGFACE:
        payload.update(extract_huggingface_evidence(evidence))
        payload.update(extract_owner_evidence(evidence))
        payload["related_display_ranks"] = list(related_display_ranks or [])
    elif entry.source_kind is SourceKind.JUYA:
        text_fields, title_url = _juya_text_fields(entry)
        payload.update(text_fields)
        payload.update(extract_juya_evidence(evidence, title_url=title_url))
    elif entry.source_kind is SourceKind.OPENROUTER:
        payload.update(extract_openrouter_evidence(evidence))
    return payload


def _juya_text_fields(
    entry: DigestEntry,
) -> tuple[dict[str, Any], str | None]:
    """Plain Juya text and any article URL carried by a linked headline."""
    title, title_url = split_linked_title(entry.title)
    summary = entry.summary or ""
    why_it_matters = entry.why_it_matters or ""
    background = entry.background_knowledge or ""
    caveat = entry.confidence_caveat

    if _looks_like_model_json(summary):
        fields = extract_digest_fields(summary)
        if fields["summary"]:
            summary = fields["summary"]
            why_it_matters = fields["why_it_matters"] or why_it_matters
            background = fields["background_knowledge"] or background
        else:
            # The headline already carries the title, so only the caveat remains.
            summary = ""
            caveat = _append_caveat(caveat, _RECOVERY_CAVEAT)

    return (
        {
            "title": title,
            "summary": summary,
            "why_it_matters": why_it_matters,
            "background_knowledge": background,
            "confidence_caveat": caveat,
        },
        title_url,
    )


def _looks_like_model_json(text: str) -> bool:
    stripped = text.lstrip()
    return (
        _STRUCTURED_SUMMARY_RE.search(text) is not None
        or stripped.startswith(("{", "```"))
    )


def _append_caveat(existing: str | None, phrase: str) -> str:
    if existing:
        return f"{existing} {phrase}"
    return phrase


def _entry_common_fields(entry: DigestEntry, *, display_rank: int) -> dict[str, Any]:
    return {
        "source_kind": entry.source_kind,
        "source_id": entry.source_id,
        "title": entry.title,
        "source_name": entry.source_name,
        "source_url": entry.source_url,
        "summary": entry.summary,
        "why_it_matters": entry.why_it_matters,
        "background_knowledge": entry.background_knowledge,
        "follow_up_action": entry.follow_up_action,
        "confidence_caveat": entry.confidence_caveat,
        "display_rank": display_rank,
        "output_language": entry.language,
    }


def extract_owner_evidence(source_evidence: dict[str, Any]) -> dict[str, Any]:
    owner_name = _optional_str(source_evidence.get("owner_name"))
    if not owner_name:
        return {"owner": None}
    owner_type = source_evidence.get("owner_type")
    normalized_type = owner_type if owner_type in ("organisation", "person") else None
    return {
        "owner": {
            "name": owner_name,
            "profile_url": _safe_http_url(source_evidence.get("owner_profile_url")),
            "avatar_url": _safe_http_url(source_evidence.get("owner_avatar_url")),
            "type": normalized_type,
        }
    }


def extract_github_evidence(
    source_evidence: dict[str, Any],
    news_item: NewsItem | None,
) -> dict[str, Any]:
    payload = extract_owner_evidence(source_evidence)
    payload["preview_image_url"] = _safe_http_url(
        source_evidence.get("preview_image_url")
    )
    payload["stars_today"] = _optional_int(source_evidence.get("stars_today"))
    stars = news_item.stars_or_views if news_item is not None else None
    payload["stars"] = _optional_int(stars)
    language = news_item.language if news_item is not None else None
    payload["language"] = _optional_str(language)
    return payload


def extract_juya_evidence(
    source_evidence: dict[str, Any],
    *,
    title_url: str | None = None,
) -> dict[str, Any]:
    item_type = source_evidence.get("juya_item_type")
    normalized_type = item_type if item_type in ("issue", "story") else None
    issue_block = {
        "id": _optional_str(source_evidence.get("issue_id")),
        "date": _optional_str(source_evidence.get("issue_date")),
        "url": _safe_http_url(source_evidence.get("issue_url")),
        "cover_url": _safe_http_url(source_evidence.get("issue_cover_url")),
        "lead_title": clean_lead_title(source_evidence.get("issue_lead_title")),
    }
    has_issue = any(value is not None for value in issue_block.values())
    story_block = {
        "number": _optional_int(source_evidence.get("story_number")),
        "section": _optional_str(source_evidence.get("story_section")),
        "original_url": _article_url(
            title_url or source_evidence.get("story_original_url")
        ),
    }
    has_story = any(value is not None for value in story_block.values())
    return {
        "item_type": normalized_type,
        "issue": issue_block if has_issue else None,
        "story": story_block if has_story and normalized_type == "story" else None,
    }


def _article_url(value: Any) -> str | None:
    """A valid http(s) article URL; image assets are rejected."""
    url = _safe_http_url(value)
    if url is None or is_image_url(url):
        return None
    return url


def extract_huggingface_evidence(source_evidence: dict[str, Any]) -> dict[str, Any]:
    """Return whitelisted Hugging Face metrics and summary-only family variants."""
    variants_raw = source_evidence.get("family_variants")
    family_variants: list[dict[str, Any]] = []
    if isinstance(variants_raw, list):
        for variant in variants_raw:
            if not isinstance(variant, dict):
                continue
            source_id = str(
                variant.get("source_id", variant.get("id", ""))
            ).strip()
            title = str(variant.get("title", source_id)).strip()
            if not source_id and not title:
                continue
            url = variant.get("url")
            family_variants.append(
                {
                    "source_id": source_id or title,
                    "title": title or source_id,
                    "url": str(url).strip() if url else None,
                    "downloads_30d": _optional_int(variant.get("downloads_30d")),
                    "likes": _optional_int(variant.get("likes")),
                }
            )

    return {
        "base_model": _optional_str(source_evidence.get("base_model")),
        "trending_score": source_evidence.get("trending_score"),
        "downloads_30d": _optional_int(source_evidence.get("downloads_30d")),
        "likes": _optional_int(source_evidence.get("likes")),
        "pipeline_tag": _optional_str(source_evidence.get("pipeline_tag")),
        "family_variants": family_variants,
    }


def extract_openrouter_evidence(source_evidence: dict[str, Any]) -> dict[str, Any]:
    """Return whitelisted OpenRouter model listing fields for digest views."""
    prompt = _optional_str(source_evidence.get("prompt_price_per_million"))
    completion = _optional_str(source_evidence.get("completion_price_per_million"))
    modalities_raw = source_evidence.get("input_modalities")
    modalities: list[str] = []
    if isinstance(modalities_raw, list):
        modalities = [str(m) for m in modalities_raw if m is not None]
    free_token_pricing = False
    if prompt is not None and completion is not None:
        try:
            free_token_pricing = float(prompt) == 0.0 and float(completion) == 0.0
        except ValueError:
            free_token_pricing = False
    return {
        "context_length": _optional_int(source_evidence.get("context_length")),
        "prompt_price_per_million": prompt,
        "completion_price_per_million": completion,
        "free_token_pricing": free_token_pricing,
        "input_modalities": modalities,
        "provider": _optional_str(source_evidence.get("provider")),
    }


def _safe_http_url(value: Any) -> str | None:
    text = _optional_str(value)
    if text is None:
        return None
    if text.startswith("https://") or text.startswith("http://"):
        return text
    return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
