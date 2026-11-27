"""Offline source-scope decisions for explicitly authorized research (R2).

This module never performs I/O. It decides whether one URL may be read for one
selected saved entry, using the entry's saved identity plus application-owned
approved documentation scopes. Network destination checks and redirects belong
to the fetcher (R4).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from ai_news_agent.models import SourceKind

Decision = Literal["allow", "deny", "unverified"]
Relationship = Literal["original_source", "original_developer", "variant_maintainer"]


@dataclass(frozen=True)
class ResearchScopeEntry:
    """The saved entry a research request is bound to, with its exact subject."""

    source_kind: SourceKind
    source_id: str
    source_url: str
    subject_id: str | None


@dataclass(frozen=True)
class ApprovedResearchScope:
    """Application-verified publisher documentation for one exact subject."""

    source_kind: SourceKind
    source_id: str
    subject_id: str
    publisher: str
    relationship: Relationship
    entry_point: str
    project_path: str


@dataclass(frozen=True)
class ResearchAuthorization:
    """One decision; fetch fields are populated only when the decision is allow."""

    decision: Decision
    reason: str
    url: str | None = None
    publisher: str | None = None
    relationship: Relationship | None = None
    scope: ApprovedResearchScope | None = None


def authorize_research_url(
    entry: ResearchScopeEntry,
    url: str,
    approved_scopes: list[ApprovedResearchScope],
) -> ResearchAuthorization:
    """Allow only the saved page or documentation approved for this exact subject."""
    candidate, refusal = _checked_url(url)
    if refusal is not None:
        return ResearchAuthorization(decision="deny", reason=refusal)
    original, saved_refusal = _checked_url(entry.source_url)
    if saved_refusal is not None:
        return ResearchAuthorization(decision="deny", reason=saved_refusal)
    if candidate == original:
        return ResearchAuthorization(
            decision="allow",
            reason="original_source",
            url=candidate,
            publisher=_origin_host(candidate),
            relationship="original_source",
        )
    allowed_by: list[ApprovedResearchScope] = []
    outside_project = False
    subject_mismatch = False
    candidate_origin, candidate_path, candidate_query = _split_canonical(candidate)
    for scope in approved_scopes:
        entry_point = _canonical_url(scope.entry_point)
        if entry_point is None:
            continue
        scope_origin, entry_path, _ = _split_canonical(entry_point)
        scope_path = _project_root(scope.project_path)
        if scope_path is None or not _within_project(entry_path, scope_path):
            continue
        if candidate_origin != scope_origin:
            continue
        if not _scope_bound_to(scope, entry):
            subject_mismatch = True
            continue
        if candidate == entry_point:
            allowed_by.append(scope)
        elif candidate_query == "" and _within_project(candidate_path, scope_path):
            allowed_by.append(scope)
        else:
            outside_project = True

    if len({(scope.publisher, scope.relationship) for scope in allowed_by}) > 1:
        return ResearchAuthorization(decision="deny", reason="conflicting_approval")
    if allowed_by:
        return _allowed(candidate, allowed_by[0], "approved_project")
    if outside_project:
        return ResearchAuthorization(decision="deny", reason="outside_project")
    if subject_mismatch:
        return ResearchAuthorization(decision="deny", reason="subject_mismatch")
    return ResearchAuthorization(decision="unverified", reason="publisher_unverified")


def _scope_bound_to(scope: ApprovedResearchScope, entry: ResearchScopeEntry) -> bool:
    if not entry.subject_id:
        return False
    return (
        scope.source_kind == entry.source_kind
        and scope.source_id == entry.source_id
        and scope.subject_id == entry.subject_id
    )


def _allowed(
    canonical: str,
    scope: ApprovedResearchScope,
    reason: str,
) -> ResearchAuthorization:
    return ResearchAuthorization(
        decision="allow",
        reason=reason,
        url=canonical,
        publisher=scope.publisher,
        relationship=scope.relationship,
        scope=scope,
    )


def _split_canonical(canonical: str) -> tuple[str, str, str]:
    parts = urlsplit(canonical)
    origin = f"{parts.scheme}://{parts.netloc}"
    return origin, parts.path or "/", parts.query


def _project_root(project_path: str) -> str | None:
    """Normalize a configured project path, refusing ambiguous or unsafe roots."""
    if not project_path.startswith("/") or _has_ambiguous_path(project_path):
        return None
    root = project_path.rstrip("/")
    return root or None


def _within_project(path: str, project_path: str) -> bool:
    root = project_path.rstrip("/")
    if not root:
        return False
    return path == root or path.startswith(f"{root}/")


def _has_ambiguous_path(path: str) -> bool:
    """True when a path form could be interpreted differently by a client."""
    if "\\" in path:
        return True
    if any(segment in (".", "..") for segment in path.split("/")):
        return True
    for escape in re.finditer(r"%([0-9a-fA-F]{2})", path):
        byte = int(escape.group(1), 16)
        if byte < 0x20 or chr(byte) in "./\\":
            return True
    return False


def _checked_url(url: str) -> tuple[str | None, str | None]:
    """Return a canonical URL or the refusal reason that forbids it."""
    canonical = _canonical_url(url)
    if canonical is None:
        return None, "invalid_url"
    if _is_unsafe_host(_origin_host(canonical)):
        return None, "unsafe_destination"
    return canonical, None


def _is_unsafe_host(host: str) -> bool:
    """Refuse local or non-public literal destinations without resolving DNS."""
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not address.is_global


def _canonical_url(url: str) -> str | None:
    """Canonical HTTPS identity of one URL, or ``None`` when it is unusable."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    host = parts.hostname.lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    display_host = f"[{host}]" if ":" in host else host
    authority = display_host if port in (None, 443) else f"{display_host}:{port}"
    path = parts.path or "/"
    if _has_ambiguous_path(path):
        return None
    query = f"?{parts.query}" if parts.query else ""
    return f"https://{authority}{path}{query}"


def _origin_host(canonical_url: str) -> str:
    try:
        return (urlsplit(canonical_url).hostname or "").lower()
    except ValueError:
        return ""


__all__ = [
    "ApprovedResearchScope",
    "ResearchAuthorization",
    "ResearchScopeEntry",
    "authorize_research_url",
]
