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
