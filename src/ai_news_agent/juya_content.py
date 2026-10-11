"""Structured parsing for Juya daily issue markdown and bulletin stories."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_JUYA_COVER_RE = re.compile(
    r"!\[[^\]]*\]\((https://assets\.juya\.uk/cover/[^)\s]+)\)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_STORY_HEADING_RE = re.compile(
    r"^#{1,3}\s+(.+?)\s*(?:`#(\d+)`|#(\d+))\s*$",
)
_OVERVIEW_SECTIONS = frozenset({"概览", "overview"})
_STORY_EVIDENCE_MAX = 2000
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")


@dataclass(frozen=True)
class JuyaParsedStory:
    number: int
    title: str
    section: str | None
    summary: str | None
    evidence_text: str
    original_url: str | None


@dataclass(frozen=True)
class JuyaParsedIssue:
    date: str | None
    cover_url: str | None
    lead_title: str | None
    stories: list[JuyaParsedStory] = field(default_factory=list)


def parse_juya_issue_markdown(text: str) -> JuyaParsedIssue:
    """Parse raw Juya issue markdown before flattening/truncation."""
    lines = text.splitlines()
    cover_url = _extract_cover_url(text)
    date = _extract_issue_date(lines)
    lead_title = _extract_lead_title(lines)
    stories = _extract_stories(lines)
    return JuyaParsedIssue(
        date=date,
        cover_url=cover_url,
        lead_title=lead_title,
        stories=stories,
    )


def build_juya_issue_evidence(
    parsed: JuyaParsedIssue,
    *,
    issue_id: str,
    issue_url: str,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "juya_item_type": "issue",
        "issue_id": issue_id,
        "issue_url": issue_url,
    }
    if parsed.date:
        evidence["issue_date"] = parsed.date
    if parsed.cover_url:
        evidence["issue_cover_url"] = parsed.cover_url
    if parsed.lead_title:
        evidence["issue_lead_title"] = parsed.lead_title
    return evidence


def build_juya_story_evidence(
    parsed: JuyaParsedIssue,
    story: JuyaParsedStory,
    *,
    issue_id: str,
    issue_url: str,
) -> dict[str, Any]:
    evidence = build_juya_issue_evidence(parsed, issue_id=issue_id, issue_url=issue_url)
    evidence["juya_item_type"] = "story"
    evidence["story_number"] = story.number
    if story.section:
        evidence["story_section"] = story.section
    if story.original_url:
        evidence["story_original_url"] = story.original_url
    evidence["story_identity"] = f"{issue_id}:{story.number}"
    return evidence


def story_source_id(issue_id: str, story_number: int) -> str:
    return f"juya-story-{issue_id}-{story_number}"


def story_anchor(story_number: int) -> str:
    return f"story-{story_number}"


def _extract_cover_url(text: str) -> str | None:
    match = _JUYA_COVER_RE.search(text)
    if match is None:
        return None
    url = match.group(1).strip()
    if url.startswith("https://"):
        return url
    return None


def _extract_issue_date(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            match = _DATE_RE.search(stripped)
            if match:
                return match.group(0)
        match = _DATE_RE.search(stripped)
        if match:
            return match.group(0)
    return None


def _extract_lead_title(lines: list[str]) -> str | None:
    seen_heading = False
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if parts:
                break
            continue
        if stripped.startswith("#"):
            if seen_heading:
                if stripped.startswith("##"):
                    break
            seen_heading = True
            continue
        if stripped.startswith("!["):
            continue
        if stripped.startswith("##"):
            break
        parts.append(stripped)
    lead = " ".join(parts).strip()
    return lead or None


def _extract_stories(lines: list[str]) -> list[JuyaParsedStory]:
    current_section: str | None = None
    in_overview = False
    stories: list[JuyaParsedStory] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("## ") and not stripped.startswith("###"):
            section_name = stripped[3:].strip()
            in_overview = section_name.lower() in _OVERVIEW_SECTIONS or section_name in _OVERVIEW_SECTIONS
            current_section = None if in_overview else section_name
            index += 1
            continue

        if in_overview:
            index += 1
            continue

        heading_match = _STORY_HEADING_RE.match(stripped)
        if heading_match is None:
            index += 1
            continue

        title = heading_match.group(1).strip()
        number_raw = heading_match.group(2) or heading_match.group(3)
        if not number_raw:
            index += 1
            continue
        number = int(number_raw)

        body_lines: list[str] = []
        index += 1
        while index < len(lines):
            next_line = lines[index]
            next_stripped = next_line.strip()
            if _STORY_HEADING_RE.match(next_stripped):
                break
            if next_stripped.startswith("## ") and not next_stripped.startswith("###"):
                break
            body_lines.append(next_line)
            index += 1

        body_text = "\n".join(body_lines).strip()
        summary = _extract_blockquote_summary(body_text)
        original_url = _first_external_link(body_text)
        evidence_text = _bounded_story_evidence(body_text)
        stories.append(
            JuyaParsedStory(
                number=number,
                title=title,
                section=current_section,
                summary=summary,
                evidence_text=evidence_text,
                original_url=original_url,
            )
        )

    stories.sort(key=lambda story: story.number)
    return stories


def _extract_blockquote_summary(body_text: str) -> str | None:
    for line in body_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            summary = stripped.lstrip(">").strip()
            return summary or None
    return None


def _first_external_link(body_text: str) -> str | None:
    for match in _MARKDOWN_LINK_RE.finditer(body_text):
        url = match.group(2).strip()
        if url.startswith(("http://", "https://")):
            return url
    return None


def _bounded_story_evidence(body_text: str) -> str:
    parts: list[str] = []
    for line in body_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            stripped = stripped.lstrip(">").strip()
        stripped = _MARKDOWN_LINK_RE.sub(r"\1", stripped)
        parts.append(stripped)
    plain = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return plain[:_STORY_EVIDENCE_MAX]
