from pathlib import Path
import tomllib

from memory_system import __version__
from memory_system.schema import bootstrap_database


def _read_project_version() -> str:
    project_root = Path(__file__).resolve().parents[1]
    pyproject = project_root / "pyproject.toml"

    with pyproject.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def test_package_imports():
    assert __version__ == _read_project_version()


def test_package_layout():
    project_root = Path(__file__).resolve().parents[1]
    assert (project_root / "src" / "memory_system" / "__init__.py").exists()


def test_bootstrap_database_creates_expected_tables(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

    table_names = {name for (name,) in rows}
    assert {
        "episodes",
        "integrity_events",
        "memories",
        "pending_items",
        "policy_state",
        "retrieval_logs",
        "sessions",
        "staging_memories",
    }.issubset(table_names)


def test_bootstrap_database_creates_v2_columns(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        memory_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()
        }
        pending_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(pending_items)").fetchall()
        }

    assert {
        "retrieval_count",
        "last_retrieved_at",
        "use_count",
        "last_used_at",
    }.issubset(memory_columns)
    assert {
        "closed_at",
        "supersedes",
        "reopened_from",
        "retrieval_count",
        "last_retrieved_at",
        "use_count",
        "last_used_at",
    }.issubset(pending_columns)


def test_bootstrap_database_migrates_v1_tables(tmp_path: Path):
    db_path = tmp_path / "memory.db"

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE memories (
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
            """
        )
        conn.execute(
            """
            CREATE TABLE pending_items (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                priority REAL NOT NULL CHECK (priority >= 0 AND priority <= 1),
                topic_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    bootstrap_database(db_path)

    with sqlite3.connect(db_path) as conn:
        memory_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()
        }
        pending_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(pending_items)").fetchall()
        }

    assert {
        "retrieval_count",
        "last_retrieved_at",
        "use_count",
        "last_used_at",
    }.issubset(memory_columns)
    assert {
        "closed_at",
        "supersedes",
        "reopened_from",
        "retrieval_count",
        "last_retrieved_at",
        "use_count",
        "last_used_at",
    }.issubset(pending_columns)
