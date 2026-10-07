"""Map saved digests to DigestView payloads (Milestone 8A.1 T11)."""

from __future__ import annotations

from typing import Any

from ai_news_agent.models import Digest, DigestEntry, NewsItem, SourceKind


def build_digest_view_payload(
    digest: Digest,
    *,
    news_items: list[NewsItem] | None = None,
) -> dict[str, Any]:
    """Map a saved digest and optional news evidence to a DigestView-shaped dict."""
    lookup = _news_items_by_key(news_items)
    entries = [
        _build_entry_payload(entry, display_rank=index, news_items=lookup)
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


def _build_entry_payload(
    entry: DigestEntry,
    *,
    display_rank: int,
    news_items: dict[tuple[SourceKind, str], NewsItem],
) -> dict[str, Any]:
    payload = _entry_common_fields(entry, display_rank=display_rank)
    news_item = news_items.get((entry.source_kind, entry.source_id))
    evidence = news_item.source_evidence if news_item is not None else {}

    if entry.source_kind is SourceKind.GITHUB:
        payload.update(extract_github_evidence(evidence, news_item))
    elif entry.source_kind is SourceKind.HUGGINGFACE:
        payload.update(extract_huggingface_evidence(evidence))
        payload.update(extract_owner_evidence(evidence))
    elif entry.source_kind is SourceKind.JUYA:
        payload.update(extract_juya_evidence(evidence))
    return payload


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
    stars = news_item.stars_or_views if news_item is not None else None
    payload["stars"] = _optional_int(stars)
    language = news_item.language if news_item is not None else None
    payload["language"] = _optional_str(language)
    return payload


def extract_juya_evidence(source_evidence: dict[str, Any]) -> dict[str, Any]:
    item_type = source_evidence.get("juya_item_type")
    normalized_type = item_type if item_type in ("issue", "story") else None
    issue_block = {
        "id": _optional_str(source_evidence.get("issue_id")),
        "date": _optional_str(source_evidence.get("issue_date")),
        "url": _safe_http_url(source_evidence.get("issue_url")),
        "cover_url": _safe_http_url(source_evidence.get("issue_cover_url")),
        "lead_title": _optional_str(source_evidence.get("issue_lead_title")),
    }
    has_issue = any(value is not None for value in issue_block.values())
    story_block = {
        "number": _optional_int(source_evidence.get("story_number")),
        "section": _optional_str(source_evidence.get("story_section")),
        "original_url": _safe_http_url(source_evidence.get("story_original_url")),
    }
    has_story = any(value is not None for value in story_block.values())
    return {
        "item_type": normalized_type,
        "issue": issue_block if has_issue else None,
        "story": story_block if has_story and normalized_type == "story" else None,
    }


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
