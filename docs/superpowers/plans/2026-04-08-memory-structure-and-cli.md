# Memory Structure And CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit `memory_kind`, `project_name`, and input-driven `confidence` to durable memories, then expose those fields through the CLI and writer validation.

**Architecture:** Extend the existing durable-memory schema in place with additive migration-safe columns, then thread the new fields through the data model, repository, validation layer, and CLI. Preserve the current `type` field semantics while introducing `memory_kind` as a higher-level business classification, with conditional `project_name` requirements for project-scoped memories.

**Tech Stack:** Python 3.11, sqlite3, argparse, pytest, dataclasses

---

## File Structure

Planned files and responsibilities:

- Modify: `src/memory_system/schema.py`
  Add migration-safe `memory_kind` and `project_name` columns for durable memory.
- Modify: `src/memory_system/models.py`
  Extend `MemoryRecord` with `memory_kind` and `project_name`.
- Modify: `src/memory_system/repository.py`
  Round-trip the new durable-memory fields through reads and writes.
- Modify: `src/memory_system/write_pipeline.py`
  Validate `memory_kind`, `project_name`, and explicit `confidence` for observations.
- Modify: `src/memory_system/cli.py`
  Require `--kind` and `--confidence`, plus conditional `--project-name`.
- Modify: `tests/test_schema.py`
  Cover new schema columns and migration defaults.
- Modify: `tests/test_repository.py`
  Cover repository round-trip of new durable-memory fields.
- Modify: `tests/test_write_pipeline.py`
  Cover writer validation and storage behavior.
- Modify: `tests/test_cli.py`
  Cover CLI validation and successful writes with the new flags.

### Task 1: Extend Durable-Memory Schema With Migration Defaults

**Files:**
- Modify: `src/memory_system/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing schema test for the new durable-memory columns**

```python
def test_bootstrap_database_creates_memory_kind_and_project_name_columns(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        memory_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()
        }

    assert {"memory_kind", "project_name"}.issubset(memory_columns)
```

- [ ] **Step 2: Write the failing migration test for legacy durable-memory rows**

```python
def test_bootstrap_database_backfills_legacy_memory_kind(tmp_path: Path):
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
                retrieval_count INTEGER NOT NULL DEFAULT 0,
                last_retrieved_at TEXT,
                use_count INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO memories (
                id, type, payload, importance, confidence, freshness,
                status, source, topic_key, supersedes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "mem-1",
                "fact",
                '{"text": "legacy row"}',
                0.9,
                0.8,
                1.0,
                "committed",
                "test",
                "legacy",
                None,
                "2026-04-08T00:00:00Z",
                "2026-04-08T00:00:00Z",
            ),
        )
        conn.commit()

    bootstrap_database(db_path)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT memory_kind, project_name FROM memories WHERE id = ?",
            ("mem-1",),
        ).fetchone()

    assert row[0] == "handoff_note"
    assert row[1] is None
```

- [ ] **Step 3: Run the targeted schema tests and verify they fail**

Run: `pytest tests/test_schema.py -k 'memory_kind or backfills_legacy_memory_kind' -v`
Expected: FAIL because the schema does not yet define or backfill the new columns.

- [ ] **Step 4: Implement additive schema migration for `memory_kind` and `project_name`**

```python
MIGRATABLE_COLUMNS = {
    "memories": [
        ("memory_kind", "TEXT NOT NULL DEFAULT 'handoff_note'"),
        ("project_name", "TEXT"),
        ...
    ],
}
```

Constraint: the migration must preserve old rows and give existing durable memories `memory_kind='handoff_note'`.

- [ ] **Step 5: Run the targeted schema tests and verify they pass**

Run: `pytest tests/test_schema.py -k 'memory_kind or backfills_legacy_memory_kind' -v`
Expected: PASS

### Task 2: Thread `memory_kind` And `project_name` Through The Model And Repository

**Files:**
- Modify: `src/memory_system/models.py`
- Modify: `src/memory_system/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write the failing repository round-trip test**

```python
def test_repository_round_trips_memory_kind_and_project_name(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    record = MemoryRecord(
        id="mem-1",
        type="fact",
        payload={"text": "Project preference"},
        importance=0.9,
        confidence=0.85,
        freshness=1.0,
        status="committed",
        source="user",
        topic_key="skills",
        memory_kind="project_memory",
        project_name="codex-claw",
        supersedes=None,
        created_at="2026-04-08T00:00:00Z",
        updated_at="2026-04-08T00:00:00Z",
    )

    repository.upsert_memory(record)
    fetched = repository.get_memory("mem-1")

    assert fetched is not None
    assert fetched.memory_kind == "project_memory"
    assert fetched.project_name == "codex-claw"
    assert repository.list_memories(limit=5)[0].memory_kind == "project_memory"
```

- [ ] **Step 2: Run the targeted repository test and verify it fails**

Run: `pytest tests/test_repository.py -k round_trips_memory_kind_and_project_name -v`
Expected: FAIL because `MemoryRecord` and repository persistence do not yet handle the new fields.

- [ ] **Step 3: Extend `MemoryRecord` and repository reads/writes**

```python
@dataclass(slots=True)
class MemoryRecord:
    ...
    memory_kind: str = "handoff_note"
    project_name: str | None = None
```

Also update memory inserts, upserts, and row-to-model conversion to read and write both fields.

- [ ] **Step 4: Run the targeted repository test and verify it passes**

Run: `pytest tests/test_repository.py -k round_trips_memory_kind_and_project_name -v`
Expected: PASS

### Task 3: Validate The New Memory Inputs In The Write Pipeline

**Files:**
- Modify: `src/memory_system/write_pipeline.py`
- Test: `tests/test_write_pipeline.py`

- [ ] **Step 1: Write the failing writer test for explicit confidence and project metadata**

```python
def test_writer_persists_memory_kind_project_name_and_confidence(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    writer.observe(
        {
            "text": "The project uses repository-local skills.",
            "type": "fact",
            "memory_kind": "project_memory",
            "project_name": "codex-claw",
            "source": "user",
            "topic_key": "skills",
            "durability": 0.95,
            "confidence": 0.88,
            "cost_of_forgetting": 0.95,
            "unfinished": False,
        }
    )

    memory = writer.repository.list_memories(limit=1)[0]
    assert memory.memory_kind == "project_memory"
    assert memory.project_name == "codex-claw"
    assert memory.confidence == 0.88
```

- [ ] **Step 2: Write failing validation tests for invalid combinations**

```python
def test_writer_rejects_unknown_memory_kind(tmp_path: Path):
    ...
    with pytest.raises(ValueError, match="memory_kind"):
        writer.observe({...})


def test_writer_requires_project_name_for_project_memory(tmp_path: Path):
    ...
    with pytest.raises(ValueError, match="project_name"):
        writer.observe({...})
```

- [ ] **Step 3: Run the targeted writer tests and verify they fail**

Run: `pytest tests/test_write_pipeline.py -k 'memory_kind or project_name or confidence' -v`
Expected: FAIL because the writer still assumes hard-coded confidence and does not validate the new fields.

- [ ] **Step 4: Implement observation validation and storage changes**

```python
ALLOWED_MEMORY_KINDS = {
    "user_preference",
    "project_memory",
    "handoff_note",
    "learned_practice",
}

validated["confidence"] = _require_score("confidence", observation["confidence"])
```

Also enforce conditional `project_name` requirements and pass the explicit confidence into `MemoryRecord`.

- [ ] **Step 5: Run the full writer test file and verify it passes**

Run: `pytest tests/test_write_pipeline.py -v`
Expected: PASS

### Task 4: Update CLI Inputs And Validation

**Files:**
- Modify: `src/memory_system/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI test for the new remember flags**

```python
def test_cli_remember_accepts_kind_confidence_and_project_name(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    exit_code = main(
        [
            "remember",
            "--db",
            str(db_path),
            "--text",
            "Repository-local skills are preferred.",
            "--type",
            "fact",
            "--kind",
            "project_memory",
            "--project-name",
            "codex-claw",
            "--topic",
            "skills",
            "--durability",
            "0.9",
            "--confidence",
            "0.85",
            "--cost",
            "0.9",
        ]
    )

    assert exit_code == 0
```

- [ ] **Step 2: Write failing CLI validation tests for missing required inputs**

```python
def test_cli_remember_requires_kind(tmp_path: Path):
    ...
    with pytest.raises(SystemExit):
        main([...])


def test_cli_remember_requires_project_name_for_project_memory(tmp_path: Path):
    ...
    with pytest.raises(SystemExit):
        main([...])
```

- [ ] **Step 3: Run the targeted CLI tests and verify they fail**

Run: `pytest tests/test_cli.py -k 'kind or project_name or confidence' -v`
Expected: FAIL because the parser does not yet expose or validate the new remember arguments.

- [ ] **Step 4: Implement parser and command wiring for the new flags**

```python
remember_parser.add_argument("--kind", required=True)
remember_parser.add_argument("--confidence", required=True, type=bounded_float)
remember_parser.add_argument("--project-name")
```

Also pass those fields into `writer.observe(...)`.

- [ ] **Step 5: Run the full CLI test file and verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS

### Task 5: Full Verification

**Files:**
- Verify: repository working tree

- [ ] **Step 1: Run the full relevant test suite**

Run: `pytest tests/test_schema.py tests/test_repository.py tests/test_write_pipeline.py tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 2: Run the complete project test suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 3: Review the final diff**

```bash
git status --short
git diff --stat
```
