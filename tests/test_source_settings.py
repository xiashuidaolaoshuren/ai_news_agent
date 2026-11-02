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
