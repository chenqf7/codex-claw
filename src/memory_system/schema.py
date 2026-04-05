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


def bootstrap_database(db_path: Path) -> None:
    with transaction(db_path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
