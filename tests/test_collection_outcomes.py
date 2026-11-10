from __future__ import annotations

import pytest

from ai_news_agent.collection_outcomes import (
    SOURCE_FAILURE_CODES,
    collection_outcome,
)
from ai_news_agent.models import ConnectorWarning

FATAL_CODES = [
    "juya_rss_unavailable",
    "search_failed",
    "invalid_search_response",
    "no_input",
    "request_failed",
    "rate_limited",
    "auth_missing",
    "anti_bot_blocked",
    "proxy_connection_failed",
    "auth_required_missing",
    "auth_required_rejected",
]

BENIGN_CODES = [
    "juya_no_recent_issues",
    "juya_no_topic_matches",
    "juya_feed_window_limited",
    "unsupported_timeframe",
    "metadata_limited",
    "keyword_search_fallback",
    "repo_fetch_failed",
    "owner_repos_failed",
    "keyword_search_failed",
    "space_search_failed",
    "user_search_failed",
    "view_fetch_failed",
    "skipped_malformed_entry",
    "enrichment_partial",
    "subtitle_unavailable",
    "subtitle_fetch_failed",
    "incomplete_results",
    "preview_unavailable",
    "model_card_unavailable",
]


def _warning(code: str) -> ConnectorWarning:
    return ConnectorWarning(connector="juya", code=code, message=f"{code} happened")


@pytest.mark.parametrize("code", FATAL_CODES)
def test_fatal_codes_are_classified_as_source_failures(code: str) -> None:
    assert code in SOURCE_FAILURE_CODES


@pytest.mark.parametrize("code", BENIGN_CODES)
def test_degraded_codes_are_not_source_failures(code: str) -> None:
    assert code not in SOURCE_FAILURE_CODES


def test_unknown_code_is_not_a_source_failure() -> None:
    assert "some_future_warning" not in SOURCE_FAILURE_CODES


def test_entries_without_warnings_are_results() -> None:
    assert collection_outcome(entry_count=3, warnings=[]) == "results"


def test_entries_with_benign_warning_are_results() -> None:
    assert (
        collection_outcome(
            entry_count=2, warnings=[_warning("juya_feed_window_limited")]
        )
        == "results"
    )


def test_empty_without_warnings_is_no_eligible() -> None:
    assert collection_outcome(entry_count=0, warnings=[]) == "no_eligible"


def test_empty_with_benign_warning_is_no_eligible() -> None:
    assert (
        collection_outcome(entry_count=0, warnings=[_warning("juya_no_topic_matches")])
        == "no_eligible"
    )


def test_empty_with_fatal_warning_is_failed() -> None:
    assert (
        collection_outcome(entry_count=0, warnings=[_warning("juya_rss_unavailable")])
        == "failed"
    )


def test_openrouter_request_failed_with_zero_entries_is_failed() -> None:
    warning = ConnectorWarning(
        connector="openrouter", code="request_failed", message="failed"
    )
    assert collection_outcome(entry_count=0, warnings=[warning]) == "failed"


def test_openrouter_empty_success_is_no_eligible() -> None:
    assert collection_outcome(entry_count=0, warnings=[]) == "no_eligible"


def test_entries_with_fatal_warning_are_partial() -> None:
    assert (
        collection_outcome(
            entry_count=1,
            warnings=[
                _warning("juya_no_topic_matches"),
                _warning("request_failed"),
            ],
        )
        == "partial"
    )
