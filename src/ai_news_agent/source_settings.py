"""Global per-source profiles stored in SQLite (B6)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

OutputLanguagePreference = Literal["source_default", "en", "zh-CN"]
_OUTPUT_LANGUAGE_KEY = "output_language"
_VALID_OUTPUT_LANGUAGES: frozenset[str] = frozenset({"source_default", "en", "zh-CN"})

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

import re

from ai_news_agent.models import NewsItem, SourceKind
from ai_news_agent.request import DigestRequest
from ai_news_agent.topics import DEFAULT_TOPICS

JUYA_ALL_CONFIRMATION_THRESHOLD = 20

_COUNT_SOURCE_NAMES: tuple[str, ...] = (
    "juya",
    "github",
    "huggingface",
    "zhihu",
    "bilibili",
)

_PER_EACH_SOURCE = re.compile(
    r"\b(\d{1,2})\s*(?:items?\s+)?(?:per|each\s+per|for\s+each)\s+source\b"
    r"|\u6bcf\u4e2a\u6765\u6e90\s*(\d{1,2})\s*[\u6761\u4e2a]?",
    re.I,
)
_N_ITEMS = re.compile(r"\b(\d{1,2})\s+items?\b", re.I)
_SOURCE_SCOPED_COUNT = re.compile(
    r"\b(\d{1,2})\s+(juya|github|huggingface|zhihu|bilibili)\b"
    r"|\b(juya|github|huggingface|zhihu|bilibili)\s+(\d{1,2})\b",
    re.I,
)


def _clamp_count(raw: str) -> int | None:
    value = int(raw)
    if 1 <= value <= 50:
        return value
    return None


def parse_message_item_counts(text: str) -> tuple[int | None, dict[str, int]]:
    """Parse explicit item-count phrases from a user message."""
    each_match = _PER_EACH_SOURCE.search(text)
    if each_match is not None:
        raw = each_match.group(1) or each_match.group(2)
        count = _clamp_count(raw)
        if count is not None:
            return count, {}

    overrides: dict[str, int] = {}
    for match in _SOURCE_SCOPED_COUNT.finditer(text):
        if match.group(1) and match.group(2):
            count = _clamp_count(match.group(1))
            source = match.group(2).lower()
        else:
            source = match.group(3).lower()
            count = _clamp_count(match.group(4))
        if count is not None:
            overrides[source] = count
    if overrides:
        return None, overrides

    items_match = _N_ITEMS.search(text)
    if items_match is not None:
        count = _clamp_count(items_match.group(1))
        if count is not None:
            return count, {}

    legacy = re.search(
        r"\b(\d{1,2})\s*(?:items?\s+)?(?:per|each\s+per|for\s+each)\s+source\b",
        text,
        re.I,
    )
    if legacy is not None:
        count = _clamp_count(legacy.group(1))
        if count is not None:
            return count, {}
    return None, {}


class SourceSettingsError(Exception):
    """Base error for source profile operations."""


class UnknownSourceError(SourceSettingsError):
    """Raised when a source name is not in the settings catalog."""


class SourceSettingsValidationError(SourceSettingsError):
    """Raised when profile payload fails validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


SOURCE_CATALOG_ORDER: tuple[str, ...] = (
    "juya",
    "github",
    "huggingface",
    "openrouter",
    "zhihu",
    "bilibili",
)

HIDDEN_SOURCES: frozenset[str] = frozenset({"bilibili"})

DEFAULT_ITEM_COUNT: int | Literal["all"] = 5


class JuyaProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_count: int | Literal["all"] = DEFAULT_ITEM_COUNT

    @field_validator("item_count")
    @classmethod
    def _validate_item_count(cls, value: int | str) -> int | Literal["all"]:
        if value == "all":
            return "all"
        if isinstance(value, int) and 1 <= value <= 50:
            return value
        raise ValueError("item_count must be 1-50 or 'all'")


class GitHubProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_count: int = DEFAULT_ITEM_COUNT
    keywords: list[str] = Field(default_factory=list)
    min_stars: int = 0
    language: str | None = None

    @field_validator("item_count")
    @classmethod
    def _validate_item_count(cls, value: int) -> int:
        if 1 <= value <= 50:
            return value
        raise ValueError("item_count must be 1-50")

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, value: list[str]) -> list[str]:
        if len(value) > 10:
            raise ValueError("keywords may contain at most 10 entries")
        return value

    @field_validator("min_stars")
    @classmethod
    def _validate_min_stars(cls, value: int) -> int:
        if value >= 0:
            return value
        raise ValueError("min_stars must be >= 0")


class HuggingFaceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_count: int = DEFAULT_ITEM_COUNT
    pipeline_tag: str | None = None

    @field_validator("item_count")
    @classmethod
    def _validate_item_count(cls, value: int) -> int:
        if 1 <= value <= 50:
            return value
        raise ValueError("item_count must be 1-50")


class OpenRouterProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_count: int = DEFAULT_ITEM_COUNT
    free_only: bool = False

    @field_validator("item_count")
    @classmethod
    def _validate_item_count(cls, value: int) -> int:
        if 1 <= value <= 50:
            return value
        raise ValueError("item_count must be 1-50")


class ZhihuProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_count: int = DEFAULT_ITEM_COUNT

    @field_validator("item_count")
    @classmethod
    def _validate_item_count(cls, value: int) -> int:
        if 1 <= value <= 50:
            return value
        raise ValueError("item_count must be 1-50")


class BilibiliProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")


_PROFILE_MODELS: dict[str, type[BaseModel]] = {
    "juya": JuyaProfile,
    "github": GitHubProfile,
    "huggingface": HuggingFaceProfile,
    "openrouter": OpenRouterProfile,
    "zhihu": ZhihuProfile,
    "bilibili": BilibiliProfile,
}


def _profile_to_dict(name: str, model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump()
    payload["name"] = name
    payload["hidden"] = name in HIDDEN_SOURCES
    return payload


def _default_profile(name: str) -> dict[str, Any]:
    model = _PROFILE_MODELS[name]()
    return _profile_to_dict(name, model)


def _validate_profile(name: str, payload: dict[str, Any]) -> BaseModel:
    if name not in _PROFILE_MODELS:
        raise UnknownSourceError(f"unknown source: {name}")
    model_cls = _PROFILE_MODELS[name]
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        message = str(first.get("msg", "invalid profile"))
        raise SourceSettingsValidationError(message) from exc


@dataclass
class SourceSettingsService:
    """Read and write global source profiles for one database."""

    db_path: Path

    def get_language(self) -> OutputLanguagePreference:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (_OUTPUT_LANGUAGE_KEY,),
            ).fetchone()
        if row is None:
            return "source_default"
        value = str(row[0]).strip()
        if value in _VALID_OUTPUT_LANGUAGES:
            return value  # type: ignore[return-value]
        return "source_default"

    def save_language(self, value: str) -> OutputLanguagePreference:
        normalized = value.strip()
        if normalized not in _VALID_OUTPUT_LANGUAGES:
            raise SourceSettingsValidationError(
                "language must be source_default, en, or zh-CN"
            )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (_OUTPUT_LANGUAGE_KEY, normalized),
            )
            conn.commit()
        return normalized  # type: ignore[return-value]

    def list_profiles(self) -> list[dict[str, Any]]:
        stored = self._load_all()
        return [_profile_to_dict(name, stored[name]) for name in SOURCE_CATALOG_ORDER]

    def get_profile(self, name: str) -> dict[str, Any]:
        if name not in _PROFILE_MODELS:
            raise UnknownSourceError(f"unknown source: {name}")
        return _profile_to_dict(name, self._load_all()[name])

    def save_profile(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        model = _validate_profile(name, payload)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO source_settings (source, settings_json)
                VALUES (?, ?)
                ON CONFLICT(source) DO UPDATE SET settings_json = excluded.settings_json
                """,
                (name, json.dumps(model.model_dump())),
            )
            conn.commit()
        return self.get_profile(name)

    def _load_all(self) -> dict[str, BaseModel]:
        rows: dict[str, dict[str, Any]] = {}
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT source, settings_json FROM source_settings")
            for source, settings_json in cur.fetchall():
                if source in _PROFILE_MODELS:
                    rows[source] = json.loads(settings_json)
        out: dict[str, BaseModel] = {}
        for name in SOURCE_CATALOG_ORDER:
            payload = rows.get(name, {})
            out[name] = _validate_profile(name, payload)
        return out

    def apply(self, request: DigestRequest) -> DigestRequest:
        """Merge saved profiles into a digest request (explicit fields win)."""
        from dataclasses import replace

        output_language = request.output_language
        if output_language is None:
            saved_language = self.get_language()
            if saved_language != "source_default":
                output_language = saved_language

        profiles = self._load_all()
        sources = list(request.connector_names or [])
        if not sources:
            if output_language is request.output_language:
                return request
            return replace(request, output_language=output_language)

        counts: dict[str, int] = {}
        juya_all = request.juya_item_count_all
        global_count = request.items_per_source
        overrides = dict(request.source_count_overrides)

        for source in sources:
            if global_count is not None:
                if source == "juya":
                    profile = profiles["juya"]
                    if (
                        isinstance(profile, JuyaProfile)
                        and profile.item_count == "all"
                        and global_count is None
                    ):
                        juya_all = True
                    else:
                        counts[source] = global_count
                else:
                    counts[source] = global_count
                continue
            if source in overrides:
                counts[source] = overrides[source]
                continue
            profile = profiles[source]
            if source == "juya" and isinstance(profile, JuyaProfile):
                if profile.item_count == "all":
                    juya_all = True
                else:
                    counts[source] = int(profile.item_count)
            elif hasattr(profile, "item_count"):
                item_count = getattr(profile, "item_count")
                if isinstance(item_count, int):
                    counts[source] = item_count

        max_cap = request.max_items_per_source
        if counts:
            max_cap = max(max_cap, max(counts.values()))

        github_keywords: list[str] | None = request.github_keywords
        github_min_stars: int | None = request.github_min_stars
        github_language: str | None = request.github_language
        hf_pipeline = request.huggingface_pipeline_tag

        if "github" in sources and isinstance(profiles["github"], GitHubProfile):
            gh = profiles["github"]
            if _message_has_no_topic(request):
                if github_keywords is None and gh.keywords:
                    github_keywords = list(gh.keywords)
            if github_min_stars is None and gh.min_stars > 0:
                github_min_stars = gh.min_stars
            if github_language is None and gh.language:
                github_language = gh.language

        if (
            "huggingface" in sources
            and isinstance(profiles["huggingface"], HuggingFaceProfile)
            and hf_pipeline is None
            and profiles["huggingface"].pipeline_tag
        ):
            hf_pipeline = profiles["huggingface"].pipeline_tag

        juya_item_mode = request.juya_item_mode
        if juya_all:
            juya_item_mode = "stories"

        return replace(
            request,
            source_item_counts=counts,
            juya_item_count_all=juya_all,
            juya_item_mode=juya_item_mode,
            max_items_per_source=max_cap,
            github_keywords=github_keywords,
            github_min_stars=github_min_stars,
            github_language=github_language,
            huggingface_pipeline_tag=hf_pipeline,
            output_language=output_language,
        )


def build_public_counts(request: DigestRequest) -> dict[str, str]:
    """Pre-run resolved count labels for public request metadata."""
    if request.source_item_counts:
        return {name: str(cap) for name, cap in request.source_item_counts.items()}
    if request.items_per_source is not None:
        sources = list(request.connector_names or [])
        return {name: str(request.items_per_source) for name in sources}
    return {}


def public_per_source(request: DigestRequest) -> int | None:
    """Single cap shown as ``per_source`` when every selected source shares it."""
    if request.items_per_source is not None:
        return request.items_per_source
    counts = request.source_item_counts
    if not counts:
        return None
    values = list(counts.values())
    if len(set(values)) == 1:
        return values[0]
    return None


def finalize_public_counts(
    request: DigestRequest,
    *,
    entry_counts: dict[str, int],
) -> dict[str, str]:
    """Post-run count labels such as ``3 of 5`` when fewer entries were eligible."""
    requested = request.source_item_counts
    if not requested:
        return build_public_counts(request)
    labels: dict[str, str] = {}
    for source, cap in requested.items():
        got = entry_counts.get(source, 0)
        if got < cap:
            labels[source] = f"{got} of {cap}"
        else:
            labels[source] = str(cap)
    return labels


def juya_all_confirmation(
    request: DigestRequest,
    items: list[NewsItem],
) -> dict[str, object] | None:
    """Return confirmation payload when Juya-all exceeds the story threshold."""
    if not request.juya_item_count_all or request.juya_all_confirmed:
        return None
    stories = [
        item
        for item in items
        if item.source is SourceKind.JUYA
        and (item.source_evidence or {}).get("story_number") is not None
    ]
    if len(stories) <= JUYA_ALL_CONFIRMATION_THRESHOLD:
        return None

    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in stories:
        evidence = item.source_evidence or {}
        issue_id = str(evidence.get("issue_id") or "")
        if not issue_id or issue_id in seen:
            continue
        seen.add(issue_id)
        title = str(
            evidence.get("issue_lead_title")
            or evidence.get("issue_date")
            or item.title
            or issue_id
        )
        issues.append({"issue": title, "issue_number": issue_id})

    if not issues:
        return None

    payload: dict[str, object] = {
        "story_count": len(stories),
        "issue": issues[0]["issue"],
        "issue_number": issues[0]["issue_number"],
    }
    if len(issues) > 1:
        payload["issues"] = issues
    return payload


def _message_has_no_topic(request: DigestRequest) -> bool:
    if request.topics_are_filters:
        return False
    topics = list(request.topics or [])
    if not topics:
        return True
    return topics == list(DEFAULT_TOPICS)


__all__ = [
    "DEFAULT_ITEM_COUNT",
    "HIDDEN_SOURCES",
    "OutputLanguagePreference",
    "SOURCE_CATALOG_ORDER",
    "SourceSettingsService",
    "SourceSettingsValidationError",
    "UnknownSourceError",
    "parse_message_item_counts",
    "JUYA_ALL_CONFIRMATION_THRESHOLD",
    "juya_all_confirmation",
    "build_public_counts",
    "finalize_public_counts",
    "public_per_source",
]
