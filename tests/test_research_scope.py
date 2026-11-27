"""Offline research source-scope decisions (research plan R2)."""

from __future__ import annotations

import socket

import pytest

from ai_news_agent.models import SourceKind
from ai_news_agent.research_scope import (
    ApprovedResearchScope,
    ResearchScopeEntry,
    authorize_research_url,
)


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scope decisions must not resolve DNS")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def _entry(
    *,
    source_kind: SourceKind = SourceKind.GITHUB,
    source_id: str = "acme/widget",
    source_url: str = "https://github.com/acme/widget",
    subject_id: str | None = "acme/widget",
) -> ResearchScopeEntry:
    return ResearchScopeEntry(
        source_kind=source_kind,
        source_id=source_id,
        source_url=source_url,
        subject_id=subject_id,
    )


def test_saved_original_page_is_allowed_and_other_pages_on_host_are_not() -> None:
    entry = _entry()

    auth = authorize_research_url(entry, "https://github.com/acme/widget#readme", [])

    assert auth.decision == "allow"
    assert auth.reason == "original_source"
    assert auth.url == "https://github.com/acme/widget"
    assert auth.publisher == "github.com"

    other = authorize_research_url(entry, "https://github.com/acme/other", [])
    assert other.decision != "allow"
    assert other.scope is None


def test_unsafe_or_malformed_destinations_are_denied_even_when_saved() -> None:
    cases = [
        ("http://github.com/acme/widget", "invalid_url"),
        ("https://user:secret@github.com/acme/widget", "invalid_url"),
        ("https://127.0.0.1/acme/widget", "unsafe_destination"),
        ("https://localhost/acme/widget", "unsafe_destination"),
        ("https://10.0.0.8/acme/widget", "unsafe_destination"),
        ("https://[::1]/acme/widget", "unsafe_destination"),
    ]
    for saved_url, reason in cases:
        auth = authorize_research_url(_entry(source_url=saved_url), saved_url, [])
        assert auth.decision == "deny", saved_url
        assert auth.reason == reason, saved_url
        assert auth.url is None, saved_url

    external = authorize_research_url(
        _entry(), "https://169.254.169.254/latest/meta-data", []
    )
    assert external.decision == "deny"
    assert external.reason == "unsafe_destination"
    assert external.url is None


def test_page_identity_ignores_fragment_but_not_query_or_path() -> None:
    saved = _entry(source_url="https://github.com/acme/widget?tab=readme")

    same = authorize_research_url(saved, "https://github.com/acme/widget?tab=readme#top", [])
    assert same.decision == "allow"
    assert same.url == "https://github.com/acme/widget?tab=readme"

    for changed in (
        "https://github.com/acme/widget?tab=other",
        "https://github.com/acme/widget",
        "https://github.com/acme/widget/readme",
    ):
        auth = authorize_research_url(saved, changed, [])
        assert auth.decision != "allow", changed


def _developer_scope(**overrides: object) -> ApprovedResearchScope:
    values: dict[str, object] = {
        "source_kind": SourceKind.GITHUB,
        "source_id": "acme/widget",
        "subject_id": "acme/widget",
        "publisher": "Acme developer docs",
        "relationship": "original_developer",
        "entry_point": "https://acme.example/docs/widget/install",
        "project_path": "/docs/widget",
    }
    values.update(overrides)
    return ApprovedResearchScope(**values)  # type: ignore[arg-type]


def test_approved_project_scope_allows_entry_point_and_descendants_only() -> None:
    scope = _developer_scope()
    entry = _entry()

    entry_point = authorize_research_url(entry, scope.entry_point, [scope])
    assert entry_point.decision == "allow"
    assert entry_point.reason == "approved_project"
    assert entry_point.publisher == "Acme developer docs"
    assert entry_point.relationship == "original_developer"
    assert entry_point.scope is scope

    descendant = authorize_research_url(
        entry, "https://acme.example/docs/widget/install/linux", [scope]
    )
    assert descendant.decision == "allow"
    assert descendant.scope is scope

    for outside in (
        "https://acme.example/docs/widgetish",
        "https://acme.example/docs/widget-v2",
        "https://acme.example/docs",
        "https://acme.example/other/widget",
        "https://acme.example/docs/widget?page=2",
    ):
        auth = authorize_research_url(entry, outside, [scope])
        assert auth.decision == "deny", outside
        assert auth.reason == "outside_project", outside
        assert auth.scope is None, outside

    other_origin = authorize_research_url(
        entry, "https://mirror.example/docs/widget", [scope]
    )
    assert other_origin.decision == "unverified"
    assert other_origin.reason == "publisher_unverified"


def test_scope_must_bind_the_exact_entry_and_subject() -> None:
    entry = _entry(subject_id="acme/widget-instruct")
    maintainer = _developer_scope(
        subject_id="acme/widget-instruct",
        publisher="Acme community maintainers",
        relationship="variant_maintainer",
        entry_point="https://acme.example/docs/widget/install",
    )

    allowed = authorize_research_url(entry, maintainer.entry_point, [maintainer])
    assert allowed.decision == "allow"
    assert allowed.relationship == "variant_maintainer"
    assert allowed.publisher == "Acme community maintainers"

    for mismatch in (
        _developer_scope(subject_id="acme/widget"),
        _developer_scope(source_id="acme/other-widget"),
        _developer_scope(source_kind=SourceKind.HUGGINGFACE),
    ):
        auth = authorize_research_url(entry, maintainer.entry_point, [mismatch])
        assert auth.decision == "deny"
        assert auth.reason == "subject_mismatch"
        assert auth.scope is None

    unbound = authorize_research_url(
        _entry(subject_id=None), maintainer.entry_point, [maintainer]
    )
    assert unbound.decision == "deny"
    assert unbound.reason == "subject_mismatch"

    conflict = authorize_research_url(
        entry, maintainer.entry_point, [maintainer, _developer_scope(
            subject_id="acme/widget-instruct",
            publisher="Someone else",
        )]
    )
    assert conflict.decision == "deny"
    assert conflict.reason == "conflicting_approval"
    assert conflict.url is None


def test_refusals_keep_boundary_and_unknown_publisher_distinct() -> None:
    scope = _developer_scope()
    entry = _entry()

    unknown = authorize_research_url(entry, "https://unrelated.example/post", [scope])
    assert unknown.decision == "unverified"
    assert unknown.reason == "publisher_unverified"

    for auth in (
        unknown,
        authorize_research_url(entry, "https://acme.example/docs/elsewhere", [scope]),
        authorize_research_url(entry, "http://acme.example/docs/widget", [scope]),
        authorize_research_url(
            entry, "https://acme.example/docs/widget",
            [_developer_scope(subject_id="acme/other")],
        ),
    ):
        assert auth.decision != "allow"
        assert auth.url is None
        assert auth.publisher is None
        assert auth.relationship is None
        assert auth.scope is None

    assert authorize_research_url(
        entry, "https://acme.example/docs/elsewhere", [scope]
    ).reason == "outside_project"
    assert authorize_research_url(
        entry, "http://acme.example/docs/widget", [scope]
    ).reason == "invalid_url"


def test_project_root_governs_navigation_and_entry_point_must_sit_inside_it() -> None:
    scope = _developer_scope()
    entry = _entry()

    sibling_page = authorize_research_url(
        entry, "https://acme.example/docs/widget/reference", [scope]
    )
    assert sibling_page.decision == "allow"
    assert sibling_page.scope is scope

    misplaced = _developer_scope(entry_point="https://acme.example/blog/widget")
    refused = authorize_research_url(entry, misplaced.entry_point, [misplaced])
    assert refused.decision == "unverified"
    assert refused.scope is None

    host_wide = _developer_scope(
        entry_point="https://acme.example/docs/widget",
        project_path="/",
    )
    whole_host = authorize_research_url(
        entry, "https://acme.example/anything", [host_wide]
    )
    assert whole_host.decision == "unverified"
    assert whole_host.scope is None


def test_ambiguous_path_forms_are_refused_inside_an_approved_scope() -> None:
    scope = _developer_scope()
    entry = _entry()

    for ambiguous in (
        "https://acme.example/docs/widget/../admin",
        "https://acme.example/docs/widget/%2e%2e/admin",
        "https://acme.example/docs/widget%2fadmin",
        "https://acme.example/docs/widget\\admin",
    ):
        auth = authorize_research_url(entry, ambiguous, [scope])
        assert auth.decision == "deny", ambiguous
        assert auth.reason == "invalid_url", ambiguous
        assert auth.url is None, ambiguous
