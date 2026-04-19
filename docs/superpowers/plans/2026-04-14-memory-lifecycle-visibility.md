# Memory Lifecycle Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JSON-first CLI visibility for durable-memory lifecycle state and reasons, plus lightweight summary-state hints in the generated handoff brief.

**Architecture:** Keep persisted state unchanged and derive lifecycle explanations from existing `memories` rows plus linked summary records. Add narrow repository and helper support for filtered listing and explanation assembly, then expose that through new `list` and `inspect` CLI commands and finally surface only minimal summary markers in the handoff markdown.

**Tech Stack:** Python 3.11, sqlite3, argparse, json, pytest, dataclasses

---

## File Structure

Planned files and responsibilities:

- Create: `src/memory_system/lifecycle.py`
  Build JSON-safe lifecycle payloads and derived reason strings from stored durable-memory records.
- Modify: `src/memory_system/repository.py`
  Add filtered durable-memory listing and summary-target lookup helpers without moving formatting logic into SQL access.
- Modify: `src/memory_system/cli.py`
  Add `list` and `inspect` commands with JSON output.
- Modify: `src/memory_system/handoff.py`
  Add lightweight summary markers to durable-context and recent-change rendering.
- Modify: `tests/test_repository.py`
  Cover filtered durable-memory listing and linked summary lookup helpers.
- Modify: `tests/test_cli.py`
  Cover `list` and `inspect` JSON output, filters, and missing-record failures.
- Modify: `tests/test_handoff.py`
  Cover summary markers in handoff output without leaking archived detail.
- Modify: `skills/memory-system-operator/references/local-memory-system.md`
  Document the new visibility commands.
- Modify: `skills/memory-system-operator/SKILL.md`
  Mention JSON-first lifecycle inspection flow.

### Task 1: Add Durable-Memory Lifecycle Query Helpers

**Files:**
- Create: `src/memory_system/lifecycle.py`
- Modify: `src/memory_system/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write the failing repository test for filtered durable-memory listing**

```python
def test_repository_list_memories_supports_status_type_and_topic_filters(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="mem-1",
            type="fact",
            payload={"text": "Alpha committed"},
            importance=0.9,
            confidence=0.8,
            freshness=1.0,
            status="committed",
            source="cli",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T00:00:00Z",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-2",
            type="fact",
            payload={"text": "Alpha archived"},
            importance=0.5,
            confidence=0.8,
            freshness=0.5,
            status="archived",
            source="cli",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T00:00:00Z",
        )
    )

    rows = repository.list_memories(
        limit=5,
        status="committed",
        memory_type="fact",
        topic_key="alpha",
    )

    assert [row.id for row in rows] == ["mem-1"]
```

- [ ] **Step 2: Write the failing repository test for linked summary lookup**

```python
def test_repository_get_memory_returns_linked_summary_target(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="summary-1",
            type="summary",
            payload={
                "text": "Alpha summary",
                "source_ids": ["mem-1"],
                "source_type": "fact",
            },
            importance=1.0,
            confidence=1.0,
            freshness=1.0,
            status="committed",
            source="system",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T00:00:00Z",
        )
    )

    linked = repository.get_linked_summary("summary-1")

    assert linked is not None
    assert linked.id == "summary-1"
    assert linked.payload["source_ids"] == ["mem-1"]
```

- [ ] **Step 3: Run the targeted repository tests and verify they fail**

Run: `pytest tests/test_repository.py -k 'supports_status_type_and_topic_filters or linked_summary_target' -v`
Expected: FAIL because the repository does not yet support the new filter signature or linked summary helper.

- [ ] **Step 4: Add filtered listing and lifecycle helper assembly**

```python
def list_memories(
    self,
    *,
    limit: int,
    status: str | None = "committed",
    memory_type: str | None = None,
    topic_key: str | None = None,
) -> list[MemoryRecord]:
    ...

def get_linked_summary(self, summary_id: str) -> MemoryRecord | None:
    ...
```

And create a narrow lifecycle helper module:

```python
def lifecycle_reason_for_record(
    record: MemoryRecord,
    *,
    linked_summary: MemoryRecord | None,
) -> str:
    ...

def build_inspect_payload(
    record: MemoryRecord,
    *,
    linked_summary: MemoryRecord | None,
) -> dict[str, object]:
    ...
```

Constraint: the helper must not mutate repository state and must degrade cleanly when `supersedes` points to a missing record.

- [ ] **Step 5: Run the targeted repository tests and verify they pass**

Run: `pytest tests/test_repository.py -k 'supports_status_type_and_topic_filters or linked_summary_target' -v`
Expected: PASS

### Task 2: Add JSON-First `list` And `inspect` CLI Commands

**Files:**
- Modify: `src/memory_system/cli.py`
- Create: `src/memory_system/lifecycle.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI test for `list` JSON output and filters**

```python
def test_cli_list_outputs_filtered_json_rows(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="summary-1",
            type="summary",
            payload={
                "text": "Alpha summary",
                "source_ids": ["mem-1"],
                "source_type": "fact",
            },
            importance=1.0,
            confidence=1.0,
            freshness=1.0,
            status="committed",
            source="system",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T00:00:00Z",
        )
    )

    main(
        [
            "list",
            "--db",
            str(db_path),
            "--status",
            "committed",
            "--type",
            "summary",
            "--topic",
            "alpha",
            "--limit",
            "5",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["id"] == "summary-1"
    assert payload[0]["lifecycle_reason"] == "summary_memory"
```

- [ ] **Step 2: Write the failing CLI test for `inspect` lifecycle explanation**

```python
def test_cli_inspect_outputs_summary_linked_lifecycle_json(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="summary-1",
            type="summary",
            payload={
                "text": "Alpha summary",
                "source_ids": ["mem-1"],
                "source_type": "fact",
            },
            importance=1.0,
            confidence=1.0,
            freshness=1.0,
            status="committed",
            source="system",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T00:00:00Z",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-1",
            type="fact",
            payload={"text": "Alpha fact"},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="superseded",
            source="cli",
            topic_key="alpha",
            supersedes="summary-1",
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T01:00:00Z",
        )
    )

    main(["inspect", "--db", str(db_path), "--id", "mem-1"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "mem-1"
    assert payload["lifecycle"]["reason"] == "superseded_by_summary"
    assert payload["lifecycle"]["summary_id"] == "summary-1"
    assert payload["lifecycle"]["summary_topic_key"] == "alpha"
```

- [ ] **Step 3: Write the failing CLI test for missing-record failure**

```python
def test_cli_inspect_rejects_missing_memory_id(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    with pytest.raises(SystemExit):
        main(["inspect", "--db", str(db_path), "--id", "missing-id"])

    assert "Memory not found: missing-id" in capsys.readouterr().err
```

- [ ] **Step 4: Run the targeted CLI tests and verify they fail**

Run: `pytest tests/test_cli.py -k 'list_outputs_filtered_json_rows or inspect_outputs_summary_linked_lifecycle_json or inspect_rejects_missing_memory_id' -v`
Expected: FAIL because the CLI does not yet expose `list` or `inspect`.

- [ ] **Step 5: Implement CLI parsing and JSON emission**

```python
list_parser = subparsers.add_parser("list")
list_parser.add_argument("--db", required=True)
list_parser.add_argument("--status")
list_parser.add_argument("--type", dest="memory_type")
list_parser.add_argument("--topic", dest="topic_key")
list_parser.add_argument("--limit", type=positive_int, default=10)

inspect_parser = subparsers.add_parser("inspect")
inspect_parser.add_argument("--db", required=True)
inspect_parser.add_argument("--id", required=True)
```

And in `main()`:

```python
if args.command == "list":
    repository = MemoryRepository(Path(args.db))
    records = repository.list_memories(
        limit=args.limit,
        status=args.status,
        memory_type=args.memory_type,
        topic_key=args.topic_key,
    )
    print(json.dumps([...], indent=2, sort_keys=True))
    return 0

if args.command == "inspect":
    repository = MemoryRepository(Path(args.db))
    record = repository.get_memory(args.id)
    if record is None:
        parser.error(f"Memory not found: {args.id}")
    print(json.dumps(build_inspect_payload(...), indent=2, sort_keys=True))
    return 0
```

Constraint: JSON output must use stable key names from the design doc, and `list` must emit an array even when only one row matches.

- [ ] **Step 6: Run the targeted CLI tests and verify they pass**

Run: `pytest tests/test_cli.py -k 'list_outputs_filtered_json_rows or inspect_outputs_summary_linked_lifecycle_json or inspect_rejects_missing_memory_id' -v`
Expected: PASS

### Task 3: Add Lightweight Handoff Visibility And Refresh Docs

**Files:**
- Modify: `src/memory_system/handoff.py`
- Modify: `tests/test_handoff.py`
- Modify: `skills/memory-system-operator/SKILL.md`
- Modify: `skills/memory-system-operator/references/local-memory-system.md`

- [ ] **Step 1: Write the failing handoff test for summary markers**

```python
def test_handoff_marks_summary_records_in_durable_context_and_recent_changes(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="summary-1",
            type="summary",
            payload={
                "text": "Alpha summary",
                "source_ids": ["mem-1"],
                "source_type": "fact",
            },
            importance=1.0,
            confidence=1.0,
            freshness=1.0,
            status="committed",
            source="system",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T00:00:00Z",
        )
    )

    render_handoff(db_path, output_path)
    content = output_path.read_text()

    assert "- [summary] Alpha summary" in content
    assert "- [memory:summary] Alpha summary" in content
```

- [ ] **Step 2: Run the targeted handoff test and verify it fails**

Run: `pytest tests/test_handoff.py -k marks_summary_records_in_durable_context_and_recent_changes -v`
Expected: FAIL because handoff output does not yet mark summary lifecycle.

- [ ] **Step 3: Implement lightweight summary markers in handoff rendering**

```python
def _memory_line(record) -> str:
    text = record.payload["text"]
    return f"[summary] {text}" if record.type == "summary" else text

def _recent_change_lines(...):
    ...
    kind = "memory:summary" if record.type == "summary" else "memory"
```

Constraint: do not add archived records back into durable context and do not expand summary `source_ids` into the markdown brief.

- [ ] **Step 4: Update operator docs for the new JSON visibility commands**

```markdown
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli list \
  --db memory/memory.db \
  --status committed \
  --limit 10

PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli inspect \
  --db memory/memory.db \
  --id summary-123
```

Add these examples to both operator documents and state that output is JSON-first.

- [ ] **Step 5: Run the targeted handoff test and full visibility suite**

Run: `pytest tests/test_handoff.py -k marks_summary_records_in_durable_context_and_recent_changes -v`
Expected: PASS

Run: `pytest tests/test_repository.py tests/test_cli.py tests/test_handoff.py -v`
Expected: PASS with the new lifecycle visibility coverage included.

- [ ] **Step 6: Commit**

```bash
git add src/memory_system/lifecycle.py src/memory_system/repository.py src/memory_system/cli.py src/memory_system/handoff.py tests/test_repository.py tests/test_cli.py tests/test_handoff.py skills/memory-system-operator/SKILL.md skills/memory-system-operator/references/local-memory-system.md docs/superpowers/plans/2026-04-14-memory-lifecycle-visibility.md docs/superpowers/specs/2026-04-14-memory-lifecycle-visibility-design.md
git commit -m "feat: add memory lifecycle visibility"
```
