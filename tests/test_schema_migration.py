"""Schema v2 migration and backup tests (Milestone 8A.1 T2)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_news_agent.storage import SCHEMA_VERSION, DigestStore


class _BrokenMigrationStore(DigestStore):
    migration_hook_ran = False

    def _apply_v2_ddl(self, conn: sqlite3.Connection) -> None:
        type(self).migration_hook_ran = True
        super()._apply_v2_ddl(conn)
        raise RuntimeError("migration failed")


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


def _backup_path(db_path: Path) -> Path:
    return db_path.with_name(f"{db_path.name}.v1.bak")


def _seed_v1_database(db_path: Path) -> int:
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            CREATE TABLE schema_meta (
              key TEXT PRIMARY KEY NOT NULL,
              value TEXT NOT NULL
            );

            CREATE TABLE runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              requested_at TEXT NOT NULL,
              timeframe TEXT,
              request_topics_json TEXT NOT NULL,
              connector_names_json TEXT NOT NULL
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

            INSERT INTO schema_meta (key, value) VALUES ('schema_version', '1');
            """
        )
        cur = con.execute(
            """
            INSERT INTO runs (requested_at, timeframe, request_topics_json, connector_names_json)
            VALUES ('2026-01-01T00:00:00+00:00', 'today', '["RAG"]', '["github"]')
            """
        )
        run_id = int(cur.lastrowid)
        con.commit()
        return run_id
    finally:
        con.close()


def _seed_v2_database(db_path: Path) -> None:
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
              started_at TEXT NOT NULL,
              completed_at TEXT,
              PRIMARY KEY (session_id, id)
            );
            INSERT INTO schema_meta (key, value) VALUES ('schema_version', '2');
            INSERT INTO sessions (id, created_at, updated_at)
              VALUES ('kept-session', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
            INSERT INTO session_messages (session_id, sequence, role, content, created_at)
              VALUES ('kept-session', 0, 'user', 'hello', '2026-01-01T00:00:00+00:00');
            INSERT INTO session_requests (
              id, session_id, status, user_message_id, correlation_id, started_at
            ) VALUES ('kept-request', 'kept-session', 'active', 1, 'corr', '2026-01-01T00:00:00+00:00');
            """
        )
    finally:
        con.close()


def test_fresh_init_schema_is_v3_with_request_interpretation(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    store = DigestStore(db_path)
    store.init_schema()

    assert SCHEMA_VERSION == "3"
    assert _stored_schema_version(db_path) == "3"
    assert "interpretation_json" in _column_names(db_path, "session_requests")


def test_v2_database_gains_interpretation_column_and_keeps_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "v2.db"
    _seed_v2_database(db_path)

    store = DigestStore(db_path)
    store.init_schema()

    assert _stored_schema_version(db_path) == "3"
    assert "interpretation_json" in _column_names(db_path, "session_requests")

    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT id, interpretation_json FROM session_requests"
        ).fetchone()
        assert row is not None
        assert row[0] == "kept-request"
        assert row[1] is None
    finally:
        con.close()

    store.init_schema()
    assert _stored_schema_version(db_path) == "3"


def test_fresh_init_schema_is_v2_with_session_tables_and_no_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    store = DigestStore(db_path)
    store.init_schema()

    assert SCHEMA_VERSION == "3"
    assert _stored_schema_version(db_path) == "3"

    names = _table_names(db_path)
    assert "sessions" in names
    assert "session_messages" in names
    assert "session_requests" in names
    assert "session_id" in _column_names(db_path, "runs")
    assert not _backup_path(db_path).exists()


def test_v1_database_migrates_in_place_preserving_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "v1.db"
    run_id = _seed_v1_database(db_path)

    store = DigestStore(db_path)
    store.init_schema()

    assert _stored_schema_version(db_path) == "3"
    names = _table_names(db_path)
    assert "sessions" in names
    assert "session_messages" in names
    assert "session_requests" in names
    assert "session_id" in _column_names(db_path, "runs")

    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT id, session_id FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        assert row is not None
        assert row[1] is None
    finally:
        con.close()

    store.init_schema()
    assert _stored_schema_version(db_path) == "3"


def test_v1_upgrade_creates_sibling_backup_once(tmp_path: Path) -> None:
    db_path = tmp_path / "v1.db"
    _seed_v1_database(db_path)
    backup = _backup_path(db_path)

    store = DigestStore(db_path)
    store.init_schema()

    assert backup.exists()
    assert _stored_schema_version(backup) == "1"
    assert "sessions" not in _table_names(backup)
    assert _stored_schema_version(db_path) == "3"

    store.init_schema()
    assert backup.exists()
    assert _stored_schema_version(backup) == "1"


def test_failed_migration_leaves_original_at_v1(tmp_path: Path) -> None:
    db_path = tmp_path / "v1.db"
    _seed_v1_database(db_path)
    backup = _backup_path(db_path)

    _BrokenMigrationStore.migration_hook_ran = False
    store = _BrokenMigrationStore(db_path)

    with pytest.raises(RuntimeError, match="migration failed"):
        store.init_schema()

    assert _BrokenMigrationStore.migration_hook_ran
    assert _stored_schema_version(db_path) == "1"
    assert "sessions" not in _table_names(db_path)
    assert backup.exists()
    assert _stored_schema_version(backup) == "1"
