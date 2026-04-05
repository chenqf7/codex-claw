# Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local AI-first memory system with SQLite-backed durable memory, separate pending-work tracking, crash-safe lifecycle markers, selective retrieval, and a generated markdown handoff summary for the next agent.

**Architecture:** Implement a small Python package that treats SQLite as the source of truth and exposes focused modules for schema management, typed record storage, retrieval/classification, maintenance/recovery, and handoff generation. Keep the first version deterministic and standard-library-first so the system is easy to test, recover, and evolve before adding embeddings or runtime-specific integrations.

**Tech Stack:** Python 3, `sqlite3`, `pathlib`, `json`, `dataclasses`, `argparse`, `pytest`

---

## File Structure

Planned files and responsibilities:

- Create: `pyproject.toml`
  Defines the package metadata, Python version, and pytest configuration.
- Create: `src/memory_system/__init__.py`
  Exposes the top-level package API.
- Create: `src/memory_system/schema.py`
  Owns database bootstrap and schema creation.
- Create: `src/memory_system/models.py`
  Defines typed dataclasses and shared constants for records, states, and classifier results.
- Create: `src/memory_system/store.py`
  Handles SQLite connection management and transactional helpers.
- Create: `src/memory_system/repository.py`
  Implements create/update/query behavior for memories, pending items, sessions, and integrity events.
- Create: `src/memory_system/write_pipeline.py`
  Normalizes candidate observations, stages them, and promotes/merges/drops them.
- Create: `src/memory_system/retrieval.py`
  Classifies task state, ranks candidate memories, and builds compact retrieval payloads.
- Create: `src/memory_system/maintenance.py`
  Performs dedupe, compression, expiration, suspect handling, and bounded policy tuning.
- Create: `src/memory_system/handoff.py`
  Generates `memory/current-brief.md` from committed database state.
- Create: `src/memory_system/cli.py`
  Provides minimal commands to initialize, remember, resume, recover, maintain, and render the handoff summary.
- Create: `tests/test_schema.py`
  Verifies schema creation and bootstrap behavior.
- Create: `tests/test_repository.py`
  Verifies typed storage, lifecycle updates, and session/integrity persistence.
- Create: `tests/test_write_pipeline.py`
  Verifies staging, promotion, pending capture, and suspect-state behavior.
- Create: `tests/test_retrieval.py`
  Verifies state classification, ranking, and selective recall.
- Create: `tests/test_maintenance.py`
  Verifies dedupe, compression, expiration, and recovery handling.
- Create: `tests/test_handoff.py`
  Verifies the generated markdown brief content and trust boundaries.
- Create: `tests/test_cli.py`
  Verifies the CLI entrypoints and end-to-end workflows.

## Assumptions

- The repo has no existing application stack, so V1 uses Python and the standard library for the main implementation.
- The SQLite database will live at `memory/memory.db`.
- The generated handoff file will live at `memory/current-brief.md`.
- `pytest` is available in the execution environment. If it is not, install it before implementation begins.

### Task 1: Scaffold the package and test harness

**Files:**
- Create: `pyproject.toml`
- Create: `src/memory_system/__init__.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing bootstrap test**

```python
from pathlib import Path

from memory_system import __version__


def test_package_imports():
    assert __version__ == "0.1.0"


def test_memory_directory_target(tmp_path: Path):
    memory_dir = tmp_path / "memory"
    assert memory_dir.name == "memory"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'memory_system'`

- [ ] **Step 3: Write minimal package scaffold**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "memory-system"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

```python
# src/memory_system/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/memory_system/__init__.py tests/test_schema.py
git commit -m "chore: scaffold memory system package"
```

### Task 2: Add schema bootstrap and transactional store

**Files:**
- Create: `src/memory_system/schema.py`
- Create: `src/memory_system/store.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write the failing schema test**

```python
from pathlib import Path

from memory_system.schema import bootstrap_database


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema.py::test_bootstrap_database_creates_expected_tables -v`
Expected: FAIL with `ImportError` for `memory_system.schema`

- [ ] **Step 3: Write minimal schema and store implementation**

```python
# src/memory_system/store.py
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

```python
# src/memory_system/schema.py
from __future__ import annotations

from pathlib import Path

from memory_system.store import transaction


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        payload TEXT NOT NULL,
        importance REAL NOT NULL,
        confidence REAL NOT NULL,
        freshness REAL NOT NULL,
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
        priority REAL NOT NULL,
        topic_key TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE TABLE IF NOT EXISTS staging_memories (id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)",
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/schema.py src/memory_system/store.py tests/test_schema.py
git commit -m "feat: add memory database bootstrap"
```

### Task 3: Add typed models and repository primitives

**Files:**
- Create: `src/memory_system/models.py`
- Create: `src/memory_system/repository.py`
- Create: `tests/test_repository.py`

- [ ] **Step 1: Write the failing repository test**

```python
from pathlib import Path

from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_repository_can_insert_and_fetch_memory(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    record = MemoryRecord(
        id="mem-1",
        type="fact",
        payload={"text": "User prefers adaptive memory policies."},
        importance=0.9,
        confidence=0.8,
        freshness=1.0,
        status="committed",
        source="user",
        topic_key="memory-policy",
        supersedes=None,
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T00:00:00Z",
    )

    repository.upsert_memory(record)
    fetched = repository.get_memory("mem-1")

    assert fetched is not None
    assert fetched.type == "fact"
    assert fetched.payload["text"] == "User prefers adaptive memory policies."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repository.py::test_repository_can_insert_and_fetch_memory -v`
Expected: FAIL with `ImportError` for `memory_system.repository`

- [ ] **Step 3: Write minimal models and repository**

```python
# src/memory_system/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MemoryRecord:
    id: str
    type: str
    payload: dict[str, Any]
    importance: float
    confidence: float
    freshness: float
    status: str
    source: str
    topic_key: str
    supersedes: str | None
    created_at: str
    updated_at: str
```

```python
# src/memory_system/repository.py
from __future__ import annotations

import json
from pathlib import Path

from memory_system.models import MemoryRecord
from memory_system.store import connect, transaction


class MemoryRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def upsert_memory(self, record: MemoryRecord) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, type, payload, importance, confidence, freshness,
                    status, source, topic_key, supersedes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    importance = excluded.importance,
                    confidence = excluded.confidence,
                    freshness = excluded.freshness,
                    status = excluded.status,
                    source = excluded.source,
                    topic_key = excluded.topic_key,
                    supersedes = excluded.supersedes,
                    updated_at = excluded.updated_at
                """,
                (
                    record.id,
                    record.type,
                    json.dumps(record.payload, sort_keys=True),
                    record.importance,
                    record.confidence,
                    record.freshness,
                    record.status,
                    record.source,
                    record.topic_key,
                    record.supersedes,
                    record.created_at,
                    record.updated_at,
                ),
            )

    def get_memory(self, record_id: str) -> MemoryRecord | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return MemoryRecord(
            id=row["id"],
            type=row["type"],
            payload=json.loads(row["payload"]),
            importance=row["importance"],
            confidence=row["confidence"],
            freshness=row["freshness"],
            status=row["status"],
            source=row["source"],
            topic_key=row["topic_key"],
            supersedes=row["supersedes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/models.py src/memory_system/repository.py tests/test_repository.py
git commit -m "feat: add typed memory repository"
```

### Task 4: Implement the write pipeline for durable and pending memory

**Files:**
- Create: `src/memory_system/write_pipeline.py`
- Create: `tests/test_write_pipeline.py`
- Modify: `src/memory_system/repository.py`
- Modify: `src/memory_system/models.py`

- [ ] **Step 1: Write the failing write-pipeline test**

```python
from pathlib import Path

from memory_system.schema import bootstrap_database
from memory_system.write_pipeline import MemoryWriter


def test_writer_promotes_durable_fact_and_tracks_pending_item(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    writer.observe(
        {
            "text": "User wants long-term memory first and unfinished task carryover.",
            "type": "fact",
            "source": "user",
            "topic_key": "memory-goal",
            "durability": 0.95,
            "cost_of_forgetting": 0.95,
            "unfinished": True,
        }
    )

    snapshot = writer.debug_snapshot()
    assert snapshot["committed_memory_count"] == 1
    assert snapshot["pending_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_write_pipeline.py::test_writer_promotes_durable_fact_and_tracks_pending_item -v`
Expected: FAIL with `ImportError` for `memory_system.write_pipeline`

- [ ] **Step 3: Write minimal write pipeline**

```python
# src/memory_system/write_pipeline.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryWriter:
    def __init__(self, db_path: Path) -> None:
        self.repository = MemoryRepository(db_path)

    def observe(self, observation: dict) -> None:
        now = utc_now()
        if observation["durability"] >= 0.7 and observation["cost_of_forgetting"] >= 0.7:
            record = MemoryRecord(
                id=f"mem-{uuid4()}",
                type=observation["type"],
                payload={"text": observation["text"]},
                importance=observation["cost_of_forgetting"],
                confidence=0.8,
                freshness=1.0,
                status="committed",
                source=observation["source"],
                topic_key=observation["topic_key"],
                supersedes=None,
                created_at=now,
                updated_at=now,
            )
            self.repository.upsert_memory(record)

        if observation.get("unfinished"):
            self.repository.upsert_pending(
                item_id=f"pending-{uuid4()}",
                payload={"text": observation["text"]},
                status="active",
                priority=observation["cost_of_forgetting"],
                topic_key=observation["topic_key"],
                created_at=now,
                updated_at=now,
            )

    def debug_snapshot(self) -> dict[str, int]:
        return {
            "committed_memory_count": self.repository.count_rows("memories"),
            "pending_count": self.repository.count_rows("pending_items"),
        }
```

```python
# add to src/memory_system/repository.py
    def upsert_pending(
        self,
        *,
        item_id: str,
        payload: dict,
        status: str,
        priority: float,
        topic_key: str,
        created_at: str,
        updated_at: str,
    ) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pending_items (id, payload, status, priority, topic_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, json.dumps(payload, sort_keys=True), status, priority, topic_key, created_at, updated_at),
            )

    def count_rows(self, table_name: str) -> int:
        if table_name not in {"memories", "pending_items", "staging_memories", "sessions", "integrity_events"}:
            raise ValueError(f"Unsupported table: {table_name}")
        with connect(self.db_path) as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_write_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/models.py src/memory_system/repository.py src/memory_system/write_pipeline.py tests/test_write_pipeline.py
git commit -m "feat: add memory write pipeline"
```

### Task 5: Implement state-driven retrieval and ranking

**Files:**
- Create: `src/memory_system/retrieval.py`
- Create: `tests/test_retrieval.py`
- Modify: `src/memory_system/repository.py`

- [ ] **Step 1: Write the failing retrieval test**

```python
from pathlib import Path

from memory_system.retrieval import MemoryRetriever
from memory_system.schema import bootstrap_database
from memory_system.write_pipeline import MemoryWriter


def test_retrieval_prioritizes_continuation_work(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Need to finish crash recovery markers.",
            "type": "decision",
            "source": "user",
            "topic_key": "recovery",
            "durability": 0.9,
            "cost_of_forgetting": 0.95,
            "unfinished": True,
        }
    )

    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("continue the crash recovery work from last time")

    assert result.state == "continuation"
    assert result.pending_items
    assert "crash recovery markers" in result.summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval.py::test_retrieval_prioritizes_continuation_work -v`
Expected: FAIL with `ImportError` for `memory_system.retrieval`

- [ ] **Step 3: Write minimal retrieval implementation**

```python
# src/memory_system/retrieval.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memory_system.repository import MemoryRepository


@dataclass(slots=True)
class RetrievalResult:
    state: str
    summary: str
    memory_ids: list[str]
    pending_items: list[dict]


class MemoryRetriever:
    def __init__(self, db_path: Path) -> None:
        self.repository = MemoryRepository(db_path)

    def classify(self, query_text: str) -> str:
        lowered = query_text.lower()
        if "continue" in lowered or "resume" in lowered or "last time" in lowered:
            return "continuation"
        if "recover" in lowered or "crash" in lowered:
            return "recovery"
        if "based on" in lowered or "depends on" in lowered:
            return "dependency_recall"
        return "fresh_task"

    def retrieve(self, query_text: str) -> RetrievalResult:
        state = self.classify(query_text)
        pending_items = self.repository.list_pending(status="active")
        memories = self.repository.list_memories(limit=5)
        summary_parts = [item["payload"]["text"] for item in pending_items[:3]]
        if not summary_parts:
            summary_parts = [record.payload["text"] for record in memories[:3]]
        return RetrievalResult(
            state=state,
            summary=" | ".join(summary_parts),
            memory_ids=[record.id for record in memories],
            pending_items=pending_items,
        )
```

```python
# add to src/memory_system/repository.py
    def list_memories(self, *, limit: int) -> list[MemoryRecord]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'committed' ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            MemoryRecord(
                id=row["id"],
                type=row["type"],
                payload=json.loads(row["payload"]),
                importance=row["importance"],
                confidence=row["confidence"],
                freshness=row["freshness"],
                status=row["status"],
                source=row["source"],
                topic_key=row["topic_key"],
                supersedes=row["supersedes"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def list_pending(self, *, status: str) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM pending_items WHERE status = ? ORDER BY priority DESC, updated_at DESC",
                (status,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "payload": json.loads(row["payload"]),
                "status": row["status"],
                "priority": row["priority"],
                "topic_key": row["topic_key"],
            }
            for row in rows
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/repository.py src/memory_system/retrieval.py tests/test_retrieval.py
git commit -m "feat: add selective memory retrieval"
```

### Task 6: Add crash recovery and maintenance routines

**Files:**
- Create: `src/memory_system/maintenance.py`
- Create: `tests/test_maintenance.py`
- Modify: `src/memory_system/repository.py`

- [ ] **Step 1: Write the failing recovery test**

```python
from pathlib import Path

from memory_system.maintenance import MemoryMaintenance
from memory_system.schema import bootstrap_database


def test_recovery_marks_unclean_session_records_as_suspect(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    maintenance = MemoryMaintenance(db_path)

    maintenance.record_session_start("session-1")
    maintenance.record_staged_memory(
        memory_id="stage-1",
        payload={"text": "Half-written recovery update"},
    )
    maintenance.recover_unclean_sessions()

    suspect_count = maintenance.count_suspect_staging_records()
    assert suspect_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_maintenance.py::test_recovery_marks_unclean_session_records_as_suspect -v`
Expected: FAIL with `ImportError` for `memory_system.maintenance`

- [ ] **Step 3: Write minimal maintenance implementation**

```python
# src/memory_system/maintenance.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from memory_system.repository import MemoryRepository


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryMaintenance:
    def __init__(self, db_path: Path) -> None:
        self.repository = MemoryRepository(db_path)

    def record_session_start(self, session_id: str) -> None:
        self.repository.upsert_session(session_id=session_id, state="active", started_at=utc_now())

    def record_staged_memory(self, *, memory_id: str, payload: dict) -> None:
        self.repository.insert_staging_record(
            memory_id=memory_id,
            payload=payload,
            status="staged",
            created_at=utc_now(),
        )

    def recover_unclean_sessions(self) -> None:
        if self.repository.has_active_session():
            self.repository.mark_all_staging_as_suspect()

    def count_suspect_staging_records(self) -> int:
        return self.repository.count_staging(status="suspect")
```

```python
# add to src/memory_system/repository.py
    def upsert_session(self, *, session_id: str, state: str, started_at: str) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, state, started_at, heartbeat_at, completed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET state = excluded.state
                """,
                (session_id, state, started_at, started_at, None),
            )

    def has_active_session(self) -> bool:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM sessions WHERE state = 'active'"
            ).fetchone()
        return int(row["count"]) > 0

    def insert_staging_record(self, *, memory_id: str, payload: dict, status: str, created_at: str) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                "INSERT INTO staging_memories (id, payload, status, created_at) VALUES (?, ?, ?, ?)",
                (memory_id, json.dumps(payload, sort_keys=True), status, created_at),
            )

    def mark_all_staging_as_suspect(self) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("UPDATE staging_memories SET status = 'suspect' WHERE status = 'staged'")

    def count_staging(self, *, status: str) -> int:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM staging_memories WHERE status = ?",
                (status,),
            ).fetchone()
        return int(row["count"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_maintenance.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/maintenance.py src/memory_system/repository.py tests/test_maintenance.py
git commit -m "feat: add recovery and maintenance primitives"
```

### Task 7: Generate the markdown handoff summary

**Files:**
- Create: `src/memory_system/handoff.py`
- Create: `tests/test_handoff.py`
- Modify: `src/memory_system/retrieval.py`

- [ ] **Step 1: Write the failing handoff test**

```python
from pathlib import Path

from memory_system.handoff import render_handoff
from memory_system.schema import bootstrap_database
from memory_system.write_pipeline import MemoryWriter


def test_render_handoff_creates_orientation_markdown(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)

    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Top durable fact for orientation.",
            "type": "fact",
            "source": "user",
            "topic_key": "handoff",
            "durability": 0.95,
            "cost_of_forgetting": 0.9,
            "unfinished": True,
        }
    )

    render_handoff(db_path, output_path)
    text = output_path.read_text()

    assert "# Current Memory Brief" in text
    assert "Top durable fact for orientation." in text
    assert "Active Pending Items" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handoff.py::test_render_handoff_creates_orientation_markdown -v`
Expected: FAIL with `ImportError` for `memory_system.handoff`

- [ ] **Step 3: Write minimal handoff generator**

```python
# src/memory_system/handoff.py
from __future__ import annotations

from pathlib import Path

from memory_system.repository import MemoryRepository


def render_handoff(db_path: Path, output_path: Path) -> None:
    repository = MemoryRepository(db_path)
    memories = repository.list_memories(limit=5)
    pending_items = repository.list_pending(status="active")
    lines = [
        "# Current Memory Brief",
        "",
        "## Durable Memory",
    ]
    lines.extend(f"- {record.payload['text']}" for record in memories)
    lines.extend(["", "## Active Pending Items"])
    lines.extend(f"- {item['payload']['text']}" for item in pending_items)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handoff.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/handoff.py tests/test_handoff.py
git commit -m "feat: add generated memory handoff summary"
```

### Task 8: Add CLI entrypoints and end-to-end tests

**Files:**
- Create: `src/memory_system/cli.py`
- Create: `tests/test_cli.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing CLI test**

```python
from pathlib import Path

from memory_system.cli import main


def test_cli_init_and_handoff_workflow(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    handoff_path = tmp_path / "memory" / "current-brief.md"

    main(["init", "--db", str(db_path)])
    main(
        [
            "remember",
            "--db",
            str(db_path),
            "--text",
            "Need to resume unfinished work.",
            "--type",
            "fact",
            "--topic",
            "workflow",
            "--durability",
            "0.9",
            "--cost",
            "0.9",
            "--unfinished",
        ]
    )
    main(["handoff", "--db", str(db_path), "--output", str(handoff_path)])

    assert handoff_path.exists()
    assert "Need to resume unfinished work." in handoff_path.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_cli_init_and_handoff_workflow -v`
Expected: FAIL with `ImportError` for `memory_system.cli`

- [ ] **Step 3: Write minimal CLI**

```python
# src/memory_system/cli.py
from __future__ import annotations

import argparse
from pathlib import Path

from memory_system.handoff import render_handoff
from memory_system.schema import bootstrap_database
from memory_system.write_pipeline import MemoryWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory-system")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--db", required=True)

    remember_parser = subparsers.add_parser("remember")
    remember_parser.add_argument("--db", required=True)
    remember_parser.add_argument("--text", required=True)
    remember_parser.add_argument("--type", required=True)
    remember_parser.add_argument("--topic", required=True)
    remember_parser.add_argument("--durability", required=True, type=float)
    remember_parser.add_argument("--cost", required=True, type=float)
    remember_parser.add_argument("--unfinished", action="store_true")

    handoff_parser = subparsers.add_parser("handoff")
    handoff_parser.add_argument("--db", required=True)
    handoff_parser.add_argument("--output", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        bootstrap_database(Path(args.db))
        return 0

    if args.command == "remember":
        writer = MemoryWriter(Path(args.db))
        writer.observe(
            {
                "text": args.text,
                "type": args.type,
                "source": "cli",
                "topic_key": args.topic,
                "durability": args.durability,
                "cost_of_forgetting": args.cost,
                "unfinished": args.unfinished,
            }
        )
        return 0

    if args.command == "handoff":
        render_handoff(Path(args.db), Path(args.output))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
```

```toml
# add to pyproject.toml
[project.scripts]
memory-system = "memory_system.cli:main"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Run the focused end-to-end test suite**

Run: `pytest tests/test_schema.py tests/test_repository.py tests/test_write_pipeline.py tests/test_retrieval.py tests/test_maintenance.py tests/test_handoff.py tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/memory_system/cli.py tests/test_cli.py
git commit -m "feat: add memory system cli workflow"
```

## Self-Review

Spec coverage:

- Long-term memory is covered by Tasks 3 and 4.
- Pending work is covered by Tasks 4 and 5.
- Selective retrieval is covered by Task 5.
- Crash recovery and suspect state are covered by Task 6.
- Generated handoff view is covered by Task 7.
- Usable execution surface is covered by Task 8.

Placeholder scan:

- No `TBD`, `TODO`, or “implement later” placeholders remain in the task steps.
- Each task includes concrete files, code snippets, commands, and expected outcomes.

Type consistency:

- `MemoryWriter.observe()` consistently uses `cost_of_forgetting`.
- Retrieval returns `RetrievalResult`.
- The handoff generator reads from repository methods defined earlier in the plan.

## Notes for the implementing agent

- Keep V1 deterministic. Do not add embeddings or vector search during implementation.
- Preserve the source-of-truth boundary: SQLite is authoritative, markdown is generated only.
- If you extend the schema during implementation, update the tests first and keep the migration path simple.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-05-memory-system.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
