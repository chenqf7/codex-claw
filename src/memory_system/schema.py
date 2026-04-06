from __future__ import annotations

from pathlib import Path

from memory_system.store import transaction


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        payload TEXT NOT NULL,
        importance REAL NOT NULL CHECK (importance >= 0 AND importance <= 1),
        confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        freshness REAL NOT NULL CHECK (freshness >= 0 AND freshness <= 1),
        status TEXT NOT NULL,
        source TEXT NOT NULL,
        topic_key TEXT NOT NULL,
        supersedes TEXT,
        retrieval_count INTEGER NOT NULL DEFAULT 0,
        last_retrieved_at TEXT,
        use_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pending_items (
        id TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        status TEXT NOT NULL,
        priority REAL NOT NULL CHECK (priority >= 0 AND priority <= 1),
        topic_key TEXT NOT NULL,
        closed_at TEXT,
        supersedes TEXT,
        reopened_from TEXT,
        retrieval_count INTEGER NOT NULL DEFAULT 0,
        last_retrieved_at TEXT,
        use_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS staging_memories (
        id TEXT PRIMARY KEY,
        session_id TEXT,
        payload TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE TABLE IF NOT EXISTS episodes (id TEXT PRIMARY KEY, summary TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT NOT NULL, started_at TEXT NOT NULL, heartbeat_at TEXT, completed_at TEXT)",
    "CREATE TABLE IF NOT EXISTS integrity_events (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS retrieval_logs (id TEXT PRIMARY KEY, state TEXT NOT NULL, query_text TEXT NOT NULL, selected_ids TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS policy_state (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)",
]

MIGRATABLE_COLUMNS = {
    "memories": [
        ("retrieval_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_retrieved_at", "TEXT"),
        ("use_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_used_at", "TEXT"),
    ],
    "pending_items": [
        ("closed_at", "TEXT"),
        ("supersedes", "TEXT"),
        ("reopened_from", "TEXT"),
        ("retrieval_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_retrieved_at", "TEXT"),
        ("use_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_used_at", "TEXT"),
    ],
}


def _table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _add_missing_columns(conn) -> None:
    for table_name, columns in MIGRATABLE_COLUMNS.items():
        existing_columns = _table_columns(conn, table_name)
        for column_name, column_definition in columns:
            if column_name in existing_columns:
                continue
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )


def bootstrap_database(db_path: Path) -> None:
    with transaction(db_path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        _add_missing_columns(conn)
