"""Settings schema and source profile tests (B5+)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_news_agent.models import Digest, DigestEntry, FollowUpAction, SourceKind
from ai_news_agent.repositories.session_store import SessionStore
from ai_news_agent.storage import SCHEMA_VERSION, DigestStore


class _BrokenV4MigrationStore(DigestStore):
    migration_hook_ran = False

    def _apply_v4_ddl(self, conn: sqlite3.Connection) -> None:
        type(self).migration_hook_ran = True
        super()._apply_v4_ddl(conn)
        raise RuntimeError("v4 migration failed")


class _BrokenV3BackupStore(DigestStore):
    def _ensure_backup(self, version: str) -> None:
        if version == "3":
            raise OSError("backup failed")
        super()._ensure_backup(version)


def _table_names(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return {row[0] for row in cur.fetchall()}
    finally:
        con.close()


def _column_names(db_path: Path, table: str) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cur.fetchall()}
    finally:
        con.close()


def _stored_schema_version(db_path: Path) -> str | None:
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _backup_path(db_path: Path, version: str) -> Path:
    return db_path.with_name(f"{db_path.name}.v{version}.bak")


def _assert_v4_settings_tables(db_path: Path) -> None:
    names = _table_names(db_path)
    assert "source_settings" in names
    assert "secrets" in names
    assert "app_settings" in names
    assert "credential_health" in names
    if "digest_entries" in names:
        assert "language" in _column_names(db_path, "digest_entries")


def _create_v3_schema(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            CREATE TABLE schema_meta (
              key TEXT PRIMARY KEY NOT NULL,
              value TEXT NOT NULL
            );

            CREATE TABLE sessions (
              id TEXT PRIMARY KEY NOT NULL,
              title TEXT,
              connector_names TEXT,
              items_per_source INTEGER,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              requested_at TEXT NOT NULL,
              timeframe TEXT,
              request_topics_json TEXT NOT NULL,
              connector_names_json TEXT NOT NULL,
              session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL
            );

            CREATE TABLE news_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
              source TEXT NOT NULL,
              source_id TEXT NOT NULL,
              url TEXT NOT NULL,
              title TEXT NOT NULL,
              published_at TEXT,
              collected_at TEXT NOT NULL,
              author TEXT,
              stars_or_views INTEGER,
              language TEXT,
              metadata_completeness REAL NOT NULL,
              raw_snippet TEXT,
              tags_json TEXT NOT NULL,
              topic_matches_json TEXT NOT NULL,
              content_confidence TEXT,
              raw_payload_json TEXT NOT NULL,
              UNIQUE (run_id, source, source_id)
            );

            CREATE TABLE ranked_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
              news_item_id INTEGER NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
              score_total REAL NOT NULL,
              selected INTEGER NOT NULL,
              selection_reason TEXT NOT NULL,
              score_breakdown_json TEXT NOT NULL
            );

            CREATE TABLE digests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
              generated_at TEXT NOT NULL,
              topics_json TEXT NOT NULL,
              timeframe TEXT
            );

            CREATE TABLE digest_entries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              digest_id INTEGER NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
              source_kind TEXT NOT NULL,
              source_id TEXT NOT NULL,
              title TEXT NOT NULL,
              source_name TEXT NOT NULL,
              source_url TEXT NOT NULL,
              summary TEXT NOT NULL,
              why_it_matters TEXT NOT NULL,
              background_knowledge TEXT NOT NULL,
              follow_up_action TEXT NOT NULL,
              confidence_caveat TEXT
            );

            CREATE TABLE connector_warnings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
              connector TEXT NOT NULL,
              code TEXT NOT NULL,
              message TEXT NOT NULL,
              detail TEXT
            );

            CREATE TABLE session_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              sequence INTEGER NOT NULL,
              role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
              content TEXT NOT NULL,
              run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
              created_at TEXT NOT NULL,
              UNIQUE (session_id, sequence)
            );

            CREATE TABLE session_requests (
              id TEXT NOT NULL,
              session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              status TEXT NOT NULL CHECK (
                status IN ('active', 'succeeded', 'failed', 'cancelled', 'interrupted')
              ),
              user_message_id INTEGER NOT NULL REFERENCES session_messages(id) ON DELETE RESTRICT,
              assistant_message_id INTEGER REFERENCES session_messages(id) ON DELETE RESTRICT,
              run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
              correlation_id TEXT NOT NULL,
              error_code TEXT,
              error_message TEXT,
              interpretation_json TEXT,
              started_at TEXT NOT NULL,
              completed_at TEXT,
              PRIMARY KEY (session_id, id)
            );

            INSERT INTO schema_meta (key, value) VALUES ('schema_version', '3');
            """
        )
        con.commit()
    finally:
        con.close()


def _seed_v3_database(db_path: Path) -> tuple[str, str]:
    _create_v3_schema(db_path)
    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    store = DigestStore(db_path)
    run_id = store.save_run(
        requested_at=ts,
        timeframe="today",
        topics=["RAG"],
        connector_names=["github"],
    )
    entry_title = "Kept digest entry"
    store.save_digest(
        run_id,
        Digest(
            generated_at=ts,
            entries=[
                DigestEntry(
                    source_kind=SourceKind.GITHUB,
                    source_id="repo-kept",
                    title=entry_title,
                    source_name="GitHub",
                    source_url="https://github.com/a/kept",
                    summary="S",
                    why_it_matters="W",
                    background_knowledge="B",
                    follow_up_action=FollowUpAction.READ,
                )
            ],
            topics=["RAG"],
            timeframe="today",
        ),
    )
    session_id = "sess-kept"
    session_store = SessionStore(db_path)
    session_store.create_session(session_id, title="Chat")
    user_message_id = session_store.insert_message(session_id, role="user", content="hello")
    session_store.insert_message(session_id, role="assistant", content="hi")
    session_store.create_request(
        session_id,
        "req-kept",
        user_message_id=user_message_id,
        correlation_id="corr-kept",
    )
    return entry_title, session_id


def test_fresh_schema_is_v4_with_settings_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    store = DigestStore(db_path)
    store.init_schema()

    assert SCHEMA_VERSION == "4"
    assert _stored_schema_version(db_path) == "4"

    names = _table_names(db_path)
    assert "source_settings" in names
    assert "secrets" in names
    assert "app_settings" in names
    assert "credential_health" in names
    assert "language" in _column_names(db_path, "digest_entries")
    assert not any(name.startswith("research") for name in names)

    store.init_schema()
    assert _stored_schema_version(db_path) == "4"
    assert not _backup_path(db_path, "3").exists()


def test_v3_schema_migrates_to_v4_keeps_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "v3.db"
    entry_title, session_id = _seed_v3_database(db_path)

    store = DigestStore(db_path)
    store.init_schema()

    assert _stored_schema_version(db_path) == "4"
    _assert_v4_settings_tables(db_path)

    ctx = store.get_latest_followup_context()
    assert ctx.digest is not None
    assert ctx.digest.entries[0].title == entry_title

    session_store = SessionStore(db_path)
    assert session_store.get_session(session_id) is not None
    messages = session_store.list_messages(session_id)
    assert len(messages) == 2
    assert session_store.get_request(session_id, "req-kept") is not None

    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT language FROM digest_entries LIMIT 1").fetchone()
        assert row is not None
        assert row[0] is None
    finally:
        con.close()


def test_failed_v4_migration_leaves_original_at_v3(tmp_path: Path) -> None:
    db_path = tmp_path / "v3-fail.db"
    entry_title, _ = _seed_v3_database(db_path)
    backup = _backup_path(db_path, "3")

    _BrokenV4MigrationStore.migration_hook_ran = False
    store = _BrokenV4MigrationStore(db_path)

    with pytest.raises(RuntimeError, match="v4 migration failed"):
        store.init_schema()

    assert _BrokenV4MigrationStore.migration_hook_ran
    assert _stored_schema_version(db_path) == "3"
    assert "source_settings" not in _table_names(db_path)
    assert backup.exists()

    plain = DigestStore(db_path)
    ctx = plain.get_latest_followup_context()
    assert ctx.digest is not None
    assert ctx.digest.entries[0].title == entry_title


def test_v3_schema_migration_creates_backup_once(tmp_path: Path) -> None:
    db_path = tmp_path / "v3-backup.db"
    _seed_v3_database(db_path)
    backup = _backup_path(db_path, "3")

    store = DigestStore(db_path)
    store.init_schema()

    assert backup.exists()
    assert _stored_schema_version(backup) == "3"
    assert "source_settings" not in _table_names(backup)
    assert _stored_schema_version(db_path) == "4"

    store.init_schema()
    assert backup.exists()
    assert _stored_schema_version(backup) == "3"


def test_v3_schema_backup_failure_aborts(tmp_path: Path) -> None:
    db_path = tmp_path / "v3-backup-fail.db"
    entry_title, _ = _seed_v3_database(db_path)

    store = _BrokenV3BackupStore(db_path)
    with pytest.raises(OSError, match="backup failed"):
        store.init_schema()

    assert _stored_schema_version(db_path) == "3"
    assert "source_settings" not in _table_names(db_path)

    plain = DigestStore(db_path)
    ctx = plain.get_latest_followup_context()
    assert ctx.digest is not None
    assert ctx.digest.entries[0].title == entry_title


def test_source_settings_schema_defaults_and_validation(tmp_path: Path) -> None:
    from ai_news_agent.source_settings import (
        SourceSettingsService,
        SourceSettingsValidationError,
        UnknownSourceError,
    )

    db_path = tmp_path / "profiles.db"
    DigestStore(db_path).init_schema()
    service = SourceSettingsService(db_path)

    profiles = service.list_profiles()
    names = [profile["name"] for profile in profiles]
    assert names == ["juya", "github", "huggingface", "openrouter", "zhihu", "bilibili"]
    juya = next(p for p in profiles if p["name"] == "juya")
    assert juya["item_count"] == 5
    assert juya["hidden"] is False
    bilibili = next(p for p in profiles if p["name"] == "bilibili")
    assert bilibili["hidden"] is True
    openrouter = next(p for p in profiles if p["name"] == "openrouter")
    assert openrouter["free_only"] is False

    service.save_profile("juya", {"item_count": "all"})
    assert service.get_profile("juya")["item_count"] == "all"

    with pytest.raises(SourceSettingsValidationError):
        service.save_profile("juya", {"item_count": 0})
    with pytest.raises(SourceSettingsValidationError):
        service.save_profile("juya", {"item_count": 51})
    with pytest.raises(SourceSettingsValidationError):
        service.save_profile("github", {"keywords": [f"k{i}" for i in range(11)]})
    with pytest.raises(SourceSettingsValidationError):
        service.save_profile("github", {"min_stars": -1})
    with pytest.raises(SourceSettingsValidationError):
        service.save_profile("bilibili", {"item_count": 5})
    with pytest.raises(UnknownSourceError):
        service.save_profile("nope", {"item_count": 5})


def test_apply_uses_profile_defaults_and_explicit_counts(tmp_path: Path) -> None:
    from ai_news_agent.request import DigestRequest
    from ai_news_agent.services.session_service import SessionService
    from ai_news_agent.repositories.session_store import SessionStore
    from ai_news_agent.source_settings import SourceSettingsService

    db_path = tmp_path / "apply.db"
    DigestStore(db_path).init_schema()
    service = SourceSettingsService(db_path)
    service.save_profile("github", {"item_count": 9})

    base = DigestRequest(connector_names=["juya", "github"])
    applied = service.apply(base)
    assert applied.source_item_counts == {"juya": 5, "github": 9}

    three_items = DigestRequest(connector_names=["juya", "github"], items_per_source=3)
    applied_three = service.apply(three_items)
    assert applied_three.source_item_counts == {"juya": 3, "github": 3}

    each = DigestRequest(connector_names=["juya", "github"], items_per_source=5)
    applied_each = service.apply(each)
    assert applied_each.source_item_counts["juya"] == 5
    assert applied_each.source_item_counts["github"] == 5

    scoped = DigestRequest(
        connector_names=["juya", "github"],
        source_count_overrides={"github": 3},
    )
    applied_scoped = service.apply(scoped)
    assert applied_scoped.source_item_counts == {"juya": 5, "github": 3}

    each_wins = DigestRequest(
        connector_names=["juya", "github"],
        items_per_source=5,
        source_count_overrides={"github": 3},
    )
    applied_wins = service.apply(each_wins)
    assert applied_wins.source_item_counts == {"juya": 5, "github": 5}


def test_apply_ignores_session_items_per_source(tmp_path: Path) -> None:
    from ai_news_agent.repositories.session_store import SessionStore
    from ai_news_agent.services.session_service import SessionService
    from ai_news_agent.source_settings import SourceSettingsService

    db_path = tmp_path / "session-ignore.db"
    DigestStore(db_path).init_schema()
    settings = SourceSettingsService(db_path)
    session_service = SessionService(SessionStore(db_path), source_settings_service=settings)
    created = session_service.create_session()
    session_service.update_preferences(created.id, connector_names=["github"], items_per_source=50)

    req = session_service.build_request(created.id, "Give me today's digest")
    assert req.items_per_source is None
    assert req.source_item_counts.get("github") == 5


def test_apply_sets_github_keywords_only_without_named_topic(tmp_path: Path) -> None:
    from ai_news_agent.request import DigestRequest
    from ai_news_agent.source_settings import SourceSettingsService
    from ai_news_agent.topics import DEFAULT_TOPICS

    db_path = tmp_path / "github-keywords.db"
    DigestStore(db_path).init_schema()
    service = SourceSettingsService(db_path)
    service.save_profile("github", {"item_count": 5, "keywords": ["agents", "rag"]})

    applied = service.apply(
        DigestRequest(connector_names=["github"], topics=list(DEFAULT_TOPICS))
    )
    assert applied.github_keywords == ["agents", "rag"]
    assert applied.topics_are_filters is False

    with_topic = service.apply(
        DigestRequest(
            connector_names=["github"],
            topics=["Qwen"],
            topics_are_filters=True,
        )
    )
    assert with_topic.github_keywords is None


def test_github_search_query_uses_keywords_and_profile_filters() -> None:
    from ai_news_agent.connectors.base import ConnectorRequest
    from ai_news_agent.connectors.github import _build_search_query

    query = _build_search_query(
        ConnectorRequest(
            topics=["AI agents"],
            github_keywords=["agents", "rag"],
            github_min_stars=100,
            github_language="Python",
        )
    )
    assert "agents" in query
    assert "stars:>=100" in query
    assert "language:Python" in query

    topic_query = _build_search_query(
        ConnectorRequest(topics=["Qwen"], timeframe="today")
    )
    assert "Qwen" in topic_query


def test_cli_and_session_service_share_saved_juya_profile(tmp_path: Path) -> None:
    import argparse

    from ai_news_agent.cli import build_digest_request
    from ai_news_agent.repositories.session_store import SessionStore
    from ai_news_agent.services.session_service import SessionService
    from ai_news_agent.source_settings import SourceSettingsService

    db_path = tmp_path / "shared-profile.db"
    DigestStore(db_path).init_schema()
    settings = SourceSettingsService(db_path)
    settings.save_profile("juya", {"item_count": 8})

    ns = argparse.Namespace(
        timeframe=None,
        topics=None,
        sources="juya",
        top_n=None,
        max_items=None,
        output_style=None,
        output_language=None,
        fake=False,
        db_path=db_path,
    )
    cli_req = build_digest_request(ns, source_settings_service=settings)
    assert cli_req.source_item_counts.get("juya") == 8

    session_service = SessionService(SessionStore(db_path), source_settings_service=settings)
    created = session_service.create_session()
    session_service.update_preferences(created.id, connector_names=["juya"], items_per_source=None)
    web_req = session_service.build_request(created.id, "Give me today's digest")
    assert web_req.source_item_counts.get("juya") == 8


def test_openrouter_profile_is_not_a_connector_name() -> None:
    from ai_news_agent.sources import ALLOWED_SOURCES

    assert "openrouter" not in ALLOWED_SOURCES


def test_finalize_public_counts_reports_shortfall() -> None:
    from ai_news_agent.request import DigestRequest
    from ai_news_agent.source_settings import build_public_counts, finalize_public_counts

    request = DigestRequest(
        connector_names=["github"],
        source_item_counts={"github": 5},
    )
    assert build_public_counts(request) == {"github": "5"}
    assert finalize_public_counts(request, entry_counts={"github": 3}) == {
        "github": "3 of 5"
    }
