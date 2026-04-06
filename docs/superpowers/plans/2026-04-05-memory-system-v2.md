# Memory System V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the memory system with a skill-friendly session workflow, richer handoff output, pending lifecycle states, and retrieval telemetry with lightweight usage feedback.

**Architecture:** Extend the existing SQLite-backed Python package in place. Add the smallest schema and repository changes needed to support lifecycle and telemetry, then layer retrieval logging and handoff ranking on top, and finally document the agent-facing workflow in the memory skill so new agents can use the system with one clear operating path.

**Tech Stack:** Python 3.11, sqlite3, pathlib, json, dataclasses, argparse, pytest, Codex skills markdown

---

## File Structure

Planned files and responsibilities:

- Modify: `src/memory_system/schema.py`
  Add V2 columns needed for pending lifecycle and retrieval telemetry.
- Modify: `src/memory_system/repository.py`
  Add state transitions, telemetry updates, recent-item queries, and richer retrieval log writes.
- Modify: `src/memory_system/retrieval.py`
  Persist retrieval events and expose optional usage feedback updates.
- Modify: `src/memory_system/handoff.py`
  Render structured sections using pending lifecycle and retrieval metadata.
- Modify: `src/memory_system/maintenance.py`
  Add conservative pending expiration helpers based on stale low-signal items.
- Modify: `src/memory_system/write_pipeline.py`
  Ensure new pending records fit the lifecycle model.
- Modify: `src/memory_system/cli.py`
  Add minimal lifecycle commands for resolving, cancelling, and reopening pending items if needed by the workflow.
- Modify: `tests/test_repository.py`
  Cover pending lifecycle transitions and telemetry updates.
- Modify: `tests/test_retrieval.py`
  Cover retrieval logging, counter increments, and usage feedback.
- Modify: `tests/test_handoff.py`
  Cover section generation and ordering behavior.
- Modify: `tests/test_maintenance.py`
  Cover conservative pending expiration.
- Modify: `skills/memory-system-operator/SKILL.md`
  Document the V2 startup, during-work, and session-end workflow for new agents.

### Task 1: Extend Schema For V2 Lifecycle And Telemetry

**Files:**
- Modify: `src/memory_system/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing schema test**

```python
from pathlib import Path

from memory_system.schema import bootstrap_database


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema.py::test_bootstrap_database_creates_v2_columns -v`
Expected: FAIL because the new columns are missing from the V1 schema.

- [ ] **Step 3: Write minimal schema implementation**

```python
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        payload TEXT NOT NULL,
        importance REAL NOT NULL CHECK (importance >= 0 AND importance <= 1),
        confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        freshness REAL NOT NULL CHECK (freshness >= 0 AND freshness <= 1),
        retrieval_count INTEGER NOT NULL DEFAULT 0,
        last_retrieved_at TEXT,
        use_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TEXT,
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
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schema.py::test_bootstrap_database_creates_v2_columns -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/schema.py tests/test_schema.py
git commit -m "feat: extend memory schema for v2 telemetry"
```

### Task 2: Add Pending Lifecycle Transitions To Repository

**Files:**
- Modify: `src/memory_system/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write the failing repository tests**

```python
from pathlib import Path

from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_pending_item_can_be_resolved(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repo = MemoryRepository(db_path)
    repo.upsert_pending(
        item_id="pending-1",
        payload={"text": "Finish handoff refresh"},
        status="active",
        priority=0.9,
        topic_key="handoff",
        created_at="2026-04-05T00:00:00+00:00",
        updated_at="2026-04-05T00:00:00+00:00",
    )

    repo.transition_pending_item(
        item_id="pending-1",
        new_status="resolved",
        updated_at="2026-04-05T01:00:00+00:00",
    )

    pending = repo.list_pending(status="resolved")
    assert pending[0]["status"] == "resolved"
    assert pending[0]["closed_at"] == "2026-04-05T01:00:00+00:00"


def test_pending_item_can_be_reopened_with_lineage(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repo = MemoryRepository(db_path)
    repo.upsert_pending(
        item_id="pending-1",
        payload={"text": "Resume memory cleanup"},
        status="resolved",
        priority=0.8,
        topic_key="maintenance",
        created_at="2026-04-05T00:00:00+00:00",
        updated_at="2026-04-05T00:00:00+00:00",
    )

    repo.reopen_pending_item(
        item_id="pending-2",
        previous_item_id="pending-1",
        payload={"text": "Resume memory cleanup"},
        priority=0.8,
        topic_key="maintenance",
        created_at="2026-04-05T02:00:00+00:00",
    )

    reopened = repo.list_pending(status="reopened")
    assert reopened[0]["reopened_from"] == "pending-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repository.py -k pending -v`
Expected: FAIL with missing repository methods or missing fields in returned pending items.

- [ ] **Step 3: Write minimal repository implementation**

```python
def transition_pending_item(self, *, item_id: str, new_status: str, updated_at: str) -> None:
    closed_at = updated_at if new_status in {"resolved", "cancelled", "expired"} else None
    with transaction(self.db_path) as conn:
        conn.execute(
            """
            UPDATE pending_items
            SET status = ?, closed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, closed_at, updated_at, item_id),
        )


def reopen_pending_item(
    self,
    *,
    item_id: str,
    previous_item_id: str,
    payload: dict,
    priority: float,
    topic_key: str,
    created_at: str,
) -> None:
    self.upsert_pending(
        item_id=item_id,
        payload=payload,
        status="reopened",
        priority=priority,
        topic_key=topic_key,
        created_at=created_at,
        updated_at=created_at,
        reopened_from=previous_item_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_repository.py -k pending -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/repository.py tests/test_repository.py
git commit -m "feat: add pending lifecycle transitions"
```

### Task 3: Record Retrieval Telemetry And Usage Counters

**Files:**
- Modify: `src/memory_system/repository.py`
- Modify: `src/memory_system/retrieval.py`
- Test: `tests/test_retrieval.py`

- [ ] **Step 1: Write the failing retrieval tests**

```python
from pathlib import Path

from memory_system.retrieval import MemoryRetriever
from memory_system.write_pipeline import MemoryWriter
from memory_system.schema import bootstrap_database


def test_retrieve_logs_selected_items_and_updates_counts(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Refresh the current brief after meaningful memory changes",
            "type": "fact",
            "source": "test",
            "topic_key": "handoff",
            "durability": 0.9,
            "cost_of_forgetting": 0.9,
            "unfinished": False,
        }
    )

    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("refresh handoff brief", persist=True)

    assert result.memory_ids
    assert retriever.repository.count_rows("retrieval_logs") == 1
    memory = retriever.repository.get_memory(result.memory_ids[0])
    assert memory.retrieval_count == 1
    assert memory.last_retrieved_at is not None


def test_mark_memory_used_updates_usage_counters(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Track durable user preferences",
            "type": "preference",
            "source": "test",
            "topic_key": "user",
            "durability": 0.95,
            "cost_of_forgetting": 0.9,
            "unfinished": False,
        }
    )

    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("user preferences", persist=True)
    retriever.mark_memory_used(result.memory_ids[0])

    memory = retriever.repository.get_memory(result.memory_ids[0])
    assert memory.use_count == 1
    assert memory.last_used_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval.py -v`
Expected: FAIL because `persist`, telemetry writes, and usage counter methods do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def retrieve(self, query_text: str, *, persist: bool = False) -> RetrievalResult:
    ...
    result = RetrievalResult(
        state=state,
        summary=" | ".join(summary_parts),
        memory_ids=[record.id for record in scoped_memories],
        pending_items=scoped_pending_items,
    )
    if persist:
        now = utc_now()
        self.repository.log_retrieval(
            state=state,
            query_text=query_text,
            memory_ids=result.memory_ids,
            pending_ids=[item["id"] for item in scoped_pending_items],
            created_at=now,
        )
        self.repository.mark_memories_retrieved(
            memory_ids=result.memory_ids,
            retrieved_at=now,
        )
        self.repository.mark_pending_retrieved(
            pending_ids=[item["id"] for item in scoped_pending_items],
            retrieved_at=now,
        )
    return result


def mark_memory_used(self, memory_id: str) -> None:
    self.repository.mark_memory_used(memory_id=memory_id, used_at=utc_now())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/repository.py src/memory_system/retrieval.py tests/test_retrieval.py
git commit -m "feat: add retrieval telemetry and usage counters"
```

### Task 4: Upgrade Handoff Structure And Ranking Inputs

**Files:**
- Modify: `src/memory_system/repository.py`
- Modify: `src/memory_system/handoff.py`
- Test: `tests/test_handoff.py`

- [ ] **Step 1: Write the failing handoff test**

```python
from pathlib import Path

from memory_system.handoff import render_handoff
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_handoff_renders_v2_sections(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)
    repo = MemoryRepository(db_path)
    repo.upsert_pending(
        item_id="pending-1",
        payload={"text": "Finish pending lifecycle implementation"},
        status="active",
        priority=0.95,
        topic_key="pending",
        created_at="2026-04-05T00:00:00+00:00",
        updated_at="2026-04-05T00:00:00+00:00",
    )

    render_handoff(db_path, output_path)
    content = output_path.read_text()

    assert "## Current Focus" in content
    assert "## Active Pending Items" in content
    assert "## Durable Context" in content
    assert "## Recent Changes" in content
    assert "## Caution Items" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handoff.py -v`
Expected: FAIL because the current handoff only renders two flat sections.

- [ ] **Step 3: Write minimal handoff implementation**

```python
def render_handoff(db_path: Path, output_path: Path) -> None:
    repository = MemoryRepository(db_path)
    focus_items = repository.list_pending_for_handoff(limit=3)
    durable_memories = repository.list_memories(limit=5)
    recent_memories = repository.list_recent_memories(limit=5)
    caution_items = repository.list_suspect_staging(limit=5)
    lines = [
        "# Current Memory Brief",
        "",
        "## Current Focus",
    ]
    lines.extend(f"- {item['payload']['text']}" for item in focus_items)
    lines.extend(["", "## Active Pending Items"])
    lines.extend(f"- {item['payload']['text']}" for item in focus_items)
    lines.extend(["", "## Durable Context"])
    lines.extend(f"- {record.payload['text']}" for record in durable_memories)
    lines.extend(["", "## Recent Changes"])
    lines.extend(f"- {record.payload['text']}" for record in recent_memories)
    lines.extend(["", "## Caution Items"])
    lines.extend(f"- {item['payload']['text']}" for item in caution_items)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handoff.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/repository.py src/memory_system/handoff.py tests/test_handoff.py
git commit -m "feat: upgrade handoff structure for v2"
```

### Task 5: Add Conservative Expiration For Low-Signal Pending Items

**Files:**
- Modify: `src/memory_system/maintenance.py`
- Modify: `src/memory_system/repository.py`
- Test: `tests/test_maintenance.py`

- [ ] **Step 1: Write the failing maintenance test**

```python
from pathlib import Path

from memory_system.maintenance import MemoryMaintenance
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_expire_stale_pending_items_only_when_low_signal(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repo = MemoryRepository(db_path)
    repo.upsert_pending(
        item_id="pending-stale",
        payload={"text": "Old low-signal task"},
        status="active",
        priority=0.2,
        topic_key="cleanup",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    maintenance = MemoryMaintenance(db_path)
    expired = maintenance.expire_stale_pending_items(
        stale_before="2026-03-01T00:00:00+00:00",
        max_priority=0.3,
    )

    assert expired == ["pending-stale"]
    assert repo.list_pending(status="expired")[0]["id"] == "pending-stale"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_maintenance.py -v`
Expected: FAIL because expiration helpers do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def expire_stale_pending_items(self, *, stale_before: str, max_priority: float) -> list[str]:
    item_ids = self.repository.list_expirable_pending_ids(
        stale_before=stale_before,
        max_priority=max_priority,
    )
    for item_id in item_ids:
        self.repository.transition_pending_item(
            item_id=item_id,
            new_status="expired",
            updated_at=utc_now(),
        )
    return item_ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_maintenance.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/maintenance.py src/memory_system/repository.py tests/test_maintenance.py
git commit -m "feat: add conservative pending expiration"
```

### Task 6: Refresh Agent-Facing Skill Workflow

**Files:**
- Modify: `skills/memory-system-operator/SKILL.md`

- [ ] **Step 1: Write the workflow update**

```md
## Recommended Agent Lifecycle

### Session start

1. Ensure the DB exists and initialize it if missing.
2. Recover unclean sessions if the previous run may have crashed.
3. Read `memory/current-brief.md` if present for fast orientation.
4. Retrieve scoped memory for the current task and persist retrieval telemetry.

### During work

1. Write durable facts, decisions, and preferences intentionally.
2. Write unfinished work into pending items.
3. When retrieved memory proves useful, mark it as used.
4. Resolve, cancel, or reopen pending items instead of leaving them permanently active.

### Session end

1. Update affected pending items.
2. Regenerate the handoff brief.
3. Leave SQLite as the source of truth.
```

- [ ] **Step 2: Review the skill text against the V2 spec**

Run: `sed -n '1,260p' skills/memory-system-operator/SKILL.md`
Expected: The skill clearly presents one startup flow, one during-work flow, and one session-end flow for a new agent.

- [ ] **Step 3: Commit**

```bash
git add skills/memory-system-operator/SKILL.md
git commit -m "docs: refresh memory skill workflow for v2"
```

### Task 7: Run V2 Verification Sweep

**Files:**
- Test: `tests/test_schema.py`
- Test: `tests/test_repository.py`
- Test: `tests/test_retrieval.py`
- Test: `tests/test_handoff.py`
- Test: `tests/test_maintenance.py`

- [ ] **Step 1: Run targeted V2 test suite**

Run: `pytest tests/test_schema.py tests/test_repository.py tests/test_retrieval.py tests/test_handoff.py tests/test_maintenance.py -v`
Expected: PASS

- [ ] **Step 2: Generate a sample handoff from a temporary DB**

Run: `pytest tests/test_handoff.py::test_handoff_renders_v2_sections -v`
Expected: PASS and confirms the structured handoff renders correctly.

- [ ] **Step 3: Review for spec coverage and cleanup**

Run: `rg -n "TODO|TBD|implement later|appropriate error handling|similar to Task" docs/superpowers/plans/2026-04-05-memory-system-v2.md`
Expected: No matches

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-05-memory-system-v2.md
git commit -m "docs: add memory system v2 implementation plan"
```
