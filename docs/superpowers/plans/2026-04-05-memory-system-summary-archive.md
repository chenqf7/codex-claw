# Memory System Summary And Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conservative summary-and-archive lifecycle so committed memory can be compressed into summary records, shifted to superseded state, and later archived without losing lineage.

**Architecture:** Extend the existing SQLite-backed memory system in place. Add repository selectors and status transitions for summarize-able clusters and archive candidates, then implement maintenance helpers that create summary records, mark covered records as superseded, and archive stale superseded records under stricter rules. Keep the first version deterministic by grouping only on `topic_key + type` and storing source lineage in summary payloads.

**Tech Stack:** Python 3.11, sqlite3, pathlib, json, dataclasses, pytest

---

## File Structure

Planned files and responsibilities:

- Modify: `src/memory_system/repository.py`
  Add cluster selection, summary creation helpers, supersede/archive transitions, and status-aware retrieval helpers.
- Modify: `src/memory_system/maintenance.py`
  Add orchestrated summary-generation and archive-transition helpers.
- Modify: `src/memory_system/retrieval.py`
  Adjust default recall filtering to prefer `committed` and `summary` while de-prioritizing or excluding `superseded` and `archived` as needed.
- Modify: `src/memory_system/handoff.py`
  Keep durable handoff output compact by allowing summary records to represent summarized clusters.
- Modify: `tests/test_repository.py`
  Cover summarize-able cluster selection and status transitions.
- Modify: `tests/test_maintenance.py`
  Cover summary creation, superseding, and archive transitions.
- Modify: `tests/test_retrieval.py`
  Cover status-aware recall behavior after summarization and archiving.
- Modify: `tests/test_handoff.py`
  Cover summary visibility and archived-record exclusion in handoff.

### Task 1: Add Repository Support For Summary Candidate Selection

**Files:**
- Modify: `src/memory_system/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write the failing repository test**

```python
from pathlib import Path

from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_repository_groups_committed_memories_by_topic_and_type_for_summary(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    for index in range(3):
        repository.upsert_memory(
            MemoryRecord(
                id=f"mem-{index}",
                type="fact",
                payload={"text": f"Cluster fact {index}"},
                importance=0.8,
                confidence=0.8,
                freshness=0.8,
                status="committed",
                source="test",
                topic_key="alpha",
                supersedes=None,
                created_at=f"2026-04-05T00:00:0{index}+00:00",
                updated_at=f"2026-04-05T00:00:0{index}+00:00",
            )
        )

    repository.upsert_memory(
        MemoryRecord(
            id="mem-other",
            type="decision",
            payload={"text": "Different type should not join the cluster"},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="committed",
            source="test",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-05T00:01:00+00:00",
            updated_at="2026-04-05T00:01:00+00:00",
        )
    )

    clusters = repository.list_summary_candidate_clusters(min_cluster_size=3)

    assert len(clusters) == 1
    assert clusters[0]["topic_key"] == "alpha"
    assert clusters[0]["type"] == "fact"
    assert clusters[0]["memory_ids"] == ["mem-0", "mem-1", "mem-2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repository.py::test_repository_groups_committed_memories_by_topic_and_type_for_summary -v`
Expected: FAIL because the cluster selection helper does not exist yet.

- [ ] **Step 3: Write minimal repository implementation**

```python
def list_summary_candidate_clusters(self, *, min_cluster_size: int) -> list[dict]:
    with connect(self.db_path) as conn:
        rows = conn.execute(
            """
            SELECT topic_key, type
            FROM memories
            WHERE status = 'committed'
            GROUP BY topic_key, type
            HAVING COUNT(*) >= ?
            ORDER BY topic_key ASC, type ASC
            """,
            (min_cluster_size,),
        ).fetchall()

        clusters = []
        for row in rows:
            members = conn.execute(
                """
                SELECT id
                FROM memories
                WHERE status = 'committed' AND topic_key = ? AND type = ?
                ORDER BY created_at ASC, id ASC
                """,
                (row["topic_key"], row["type"]),
            ).fetchall()
            clusters.append(
                {
                    "topic_key": row["topic_key"],
                    "type": row["type"],
                    "memory_ids": [member["id"] for member in members],
                }
            )
    return clusters
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_repository.py::test_repository_groups_committed_memories_by_topic_and_type_for_summary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/repository.py tests/test_repository.py
git commit -m "feat: add summary candidate cluster selection"
```

### Task 2: Add Summary Creation And Supersede Transition Helpers

**Files:**
- Modify: `src/memory_system/repository.py`
- Modify: `tests/test_repository.py`

- [ ] **Step 1: Write the failing repository test**

```python
from pathlib import Path

from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_repository_can_create_summary_and_supersede_sources(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    repository.upsert_memory(
        MemoryRecord(
            id="mem-1",
            type="fact",
            payload={"text": "Cluster fact 1"},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="committed",
            source="test",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-05T00:00:00+00:00",
            updated_at="2026-04-05T00:00:00+00:00",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-2",
            type="fact",
            payload={"text": "Cluster fact 2"},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="committed",
            source="test",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-05T00:01:00+00:00",
            updated_at="2026-04-05T00:01:00+00:00",
        )
    )

    summary_id = repository.create_summary_memory(
        topic_key="alpha",
        source_type="fact",
        source_ids=["mem-1", "mem-2"],
        summary_text="Summary of alpha facts",
        created_at="2026-04-05T01:00:00+00:00",
    )
    repository.mark_memories_superseded(
        memory_ids=["mem-1", "mem-2"],
        summary_id=summary_id,
        updated_at="2026-04-05T01:00:00+00:00",
    )

    summary = repository.get_memory(summary_id)
    first = repository.get_memory("mem-1")
    second = repository.get_memory("mem-2")

    assert summary is not None
    assert summary.type == "summary"
    assert summary.payload["text"] == "Summary of alpha facts"
    assert summary.payload["source_ids"] == ["mem-1", "mem-2"]
    assert first is not None and first.status == "superseded"
    assert second is not None and second.status == "superseded"
    assert first.supersedes == summary_id
    assert second.supersedes == summary_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repository.py::test_repository_can_create_summary_and_supersede_sources -v`
Expected: FAIL because summary creation and supersede helpers do not exist yet.

- [ ] **Step 3: Write minimal repository implementation**

```python
def create_summary_memory(
    self,
    *,
    topic_key: str,
    source_type: str,
    source_ids: list[str],
    summary_text: str,
    created_at: str,
) -> str:
    summary_id = f"mem-summary-{uuid4()}"
    self.upsert_memory(
        MemoryRecord(
            id=summary_id,
            type="summary",
            payload={
                "text": summary_text,
                "source_type": source_type,
                "source_ids": source_ids,
            },
            importance=0.8,
            confidence=0.8,
            freshness=1.0,
            status="committed",
            source="maintenance",
            topic_key=topic_key,
            supersedes=None,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    return summary_id


def mark_memories_superseded(
    self,
    *,
    memory_ids: list[str],
    summary_id: str,
    updated_at: str,
) -> None:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_repository.py::test_repository_can_create_summary_and_supersede_sources -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/repository.py tests/test_repository.py
git commit -m "feat: add summary creation and supersede helpers"
```

### Task 3: Add Maintenance Helper To Summarize Eligible Clusters

**Files:**
- Modify: `src/memory_system/maintenance.py`
- Modify: `tests/test_maintenance.py`

- [ ] **Step 1: Write the failing maintenance test**

```python
from pathlib import Path

from memory_system.maintenance import MemoryMaintenance
from memory_system.repository import MemoryRepository
from memory_system.models import MemoryRecord
from memory_system.schema import bootstrap_database


def test_maintenance_summarizes_eligible_cluster_and_supersedes_sources(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    for index in range(3):
        repository.upsert_memory(
            MemoryRecord(
                id=f"mem-{index}",
                type="fact",
                payload={"text": f"Cluster fact {index}"},
                importance=0.8,
                confidence=0.8,
                freshness=0.8,
                status="committed",
                source="test",
                topic_key="alpha",
                supersedes=None,
                created_at=f"2026-04-05T00:00:0{index}+00:00",
                updated_at=f"2026-04-05T00:00:0{index}+00:00",
            )
        )

    maintenance = MemoryMaintenance(db_path)
    created_summary_ids = maintenance.summarize_eligible_clusters(min_cluster_size=3)

    assert len(created_summary_ids) == 1
    summary = repository.get_memory(created_summary_ids[0])
    assert summary is not None
    assert summary.type == "summary"
    assert summary.topic_key == "alpha"
    assert all(
        repository.get_memory(f"mem-{index}").status == "superseded"
        for index in range(3)
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_maintenance.py::test_maintenance_summarizes_eligible_cluster_and_supersedes_sources -v`
Expected: FAIL because the maintenance summarize helper does not exist yet.

- [ ] **Step 3: Write minimal maintenance implementation**

```python
def summarize_eligible_clusters(self, *, min_cluster_size: int) -> list[str]:
    created_summary_ids: list[str] = []
    now = utc_now()
    clusters = self.repository.list_summary_candidate_clusters(
        min_cluster_size=min_cluster_size,
    )
    for cluster in clusters:
        summary_id = self.repository.create_summary_memory(
            topic_key=cluster["topic_key"],
            source_type=cluster["type"],
            source_ids=cluster["memory_ids"],
            summary_text=f"Summary of {cluster['topic_key']} {cluster['type']} memory",
            created_at=now,
        )
        self.repository.mark_memories_superseded(
            memory_ids=cluster["memory_ids"],
            summary_id=summary_id,
            updated_at=now,
        )
        created_summary_ids.append(summary_id)
    return created_summary_ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_maintenance.py::test_maintenance_summarizes_eligible_cluster_and_supersedes_sources -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/maintenance.py tests/test_maintenance.py
git commit -m "feat: summarize eligible memory clusters"
```

### Task 4: Add Archive Candidate Selection And Archive Transition

**Files:**
- Modify: `src/memory_system/repository.py`
- Modify: `src/memory_system/maintenance.py`
- Modify: `tests/test_maintenance.py`

- [ ] **Step 1: Write the failing maintenance test**

```python
from pathlib import Path

from memory_system.maintenance import MemoryMaintenance
from memory_system.repository import MemoryRepository
from memory_system.models import MemoryRecord
from memory_system.schema import bootstrap_database


def test_maintenance_archives_only_stale_superseded_memory(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    repository.upsert_memory(
        MemoryRecord(
            id="mem-old",
            type="fact",
            payload={"text": "Old superseded memory"},
            importance=0.5,
            confidence=0.8,
            freshness=0.5,
            status="superseded",
            source="test",
            topic_key="alpha",
            supersedes="mem-summary-1",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            retrieval_count=0,
            last_retrieved_at=None,
            use_count=0,
            last_used_at=None,
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-recent",
            type="fact",
            payload={"text": "Recent superseded memory"},
            importance=0.5,
            confidence=0.8,
            freshness=0.5,
            status="superseded",
            source="test",
            topic_key="alpha",
            supersedes="mem-summary-1",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-04-01T00:00:00+00:00",
            retrieval_count=1,
            last_retrieved_at="2026-04-01T00:00:00+00:00",
            use_count=0,
            last_used_at=None,
        )
    )

    maintenance = MemoryMaintenance(db_path)
    archived_ids = maintenance.archive_stale_superseded_memories(
        stale_before="2026-03-01T00:00:00+00:00",
    )

    assert archived_ids == ["mem-old"]
    assert repository.get_memory("mem-old").status == "archived"
    assert repository.get_memory("mem-recent").status == "superseded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_maintenance.py::test_maintenance_archives_only_stale_superseded_memory -v`
Expected: FAIL because archive candidate selection and archive transition do not exist yet.

- [ ] **Step 3: Write minimal archive implementation**

```python
def list_archive_candidate_ids(self, *, stale_before: str) -> list[str]:
    ...


def mark_memories_archived(self, *, memory_ids: list[str], updated_at: str) -> None:
    ...


def archive_stale_superseded_memories(self, *, stale_before: str) -> list[str]:
    memory_ids = self.repository.list_archive_candidate_ids(stale_before=stale_before)
    if not memory_ids:
        return []
    self.repository.mark_memories_archived(memory_ids=memory_ids, updated_at=utc_now())
    return memory_ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_maintenance.py::test_maintenance_archives_only_stale_superseded_memory -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/repository.py src/memory_system/maintenance.py tests/test_maintenance.py
git commit -m "feat: archive stale superseded memories"
```

### Task 5: Adjust Retrieval To Favor Summary And Exclude Archived Memory

**Files:**
- Modify: `src/memory_system/retrieval.py`
- Modify: `src/memory_system/repository.py`
- Modify: `tests/test_retrieval.py`

- [ ] **Step 1: Write the failing retrieval test**

```python
from pathlib import Path

from memory_system.models import MemoryRecord
from memory_system.retrieval import MemoryRetriever
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_retrieval_excludes_archived_memory_and_keeps_summary_visible(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    repository.upsert_memory(
        MemoryRecord(
            id="mem-summary",
            type="summary",
            payload={"text": "Summary of alpha facts", "source_ids": ["mem-old"]},
            importance=0.9,
            confidence=0.9,
            freshness=1.0,
            status="committed",
            source="maintenance",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-05T00:00:00+00:00",
            updated_at="2026-04-05T00:00:00+00:00",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-old",
            type="fact",
            payload={"text": "Archived alpha fact"},
            importance=0.9,
            confidence=0.9,
            freshness=0.5,
            status="archived",
            source="test",
            topic_key="alpha",
            supersedes="mem-summary",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )

    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("alpha facts")

    assert result.memory_ids == ["mem-summary"]
    assert "Summary of alpha facts" in result.summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval.py::test_retrieval_excludes_archived_memory_and_keeps_summary_visible -v`
Expected: FAIL because archived memory is not filtered appropriately yet.

- [ ] **Step 3: Write minimal retrieval implementation**

```python
def list_memories(self, *, limit: int) -> list[MemoryRecord]:
    with connect(self.db_path) as conn:
        rows = conn.execute(
            \"\"\"
            SELECT * FROM memories
            WHERE status IN ('committed', 'summary')
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
            \"\"\",
            (limit,),
        ).fetchall()
    return [self._memory_from_row(row) for row in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval.py::test_retrieval_excludes_archived_memory_and_keeps_summary_visible -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/repository.py src/memory_system/retrieval.py tests/test_retrieval.py
git commit -m "feat: favor summary memory in retrieval"
```

### Task 6: Keep Handoff Durable Context Compact After Summarization

**Files:**
- Modify: `src/memory_system/handoff.py`
- Modify: `tests/test_handoff.py`

- [ ] **Step 1: Write the failing handoff test**

```python
from pathlib import Path

from memory_system.handoff import render_handoff
from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_handoff_durable_context_prefers_summary_over_archived_details(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    repository.upsert_memory(
        MemoryRecord(
            id="mem-summary",
            type="summary",
            payload={"text": "Summary of alpha facts", "source_ids": ["mem-old"]},
            importance=0.9,
            confidence=0.9,
            freshness=1.0,
            status="committed",
            source="maintenance",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-05T00:00:00+00:00",
            updated_at="2026-04-05T00:00:00+00:00",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-old",
            type="fact",
            payload={"text": "Archived alpha fact"},
            importance=0.9,
            confidence=0.9,
            freshness=0.5,
            status="archived",
            source="test",
            topic_key="alpha",
            supersedes="mem-summary",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )

    render_handoff(db_path, output_path)
    content = output_path.read_text()

    assert "Summary of alpha facts" in content
    assert "Archived alpha fact" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handoff.py::test_handoff_durable_context_prefers_summary_over_archived_details -v`
Expected: FAIL if archived detail still leaks into durable context.

- [ ] **Step 3: Write minimal handoff adjustment**

```python
# Reuse the repository's status-aware list_memories() behavior for durable context.
# No extra durable-context inclusion path should pull archived records into the handoff.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handoff.py::test_handoff_durable_context_prefers_summary_over_archived_details -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_system/handoff.py tests/test_handoff.py
git commit -m "feat: keep archived memory out of handoff context"
```

### Task 7: Run Summary And Archive Verification Sweep

**Files:**
- Test: `tests/test_repository.py`
- Test: `tests/test_maintenance.py`
- Test: `tests/test_retrieval.py`
- Test: `tests/test_handoff.py`

- [ ] **Step 1: Run targeted summary/archive suite**

Run: `pytest tests/test_repository.py tests/test_maintenance.py tests/test_retrieval.py tests/test_handoff.py -v`
Expected: PASS

- [ ] **Step 2: Review for plan placeholders**

Run: `rg -n "TODO|TBD|implement later|appropriate error handling|similar to Task" docs/superpowers/plans/2026-04-05-memory-system-summary-archive.md`
Expected: No matches

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-04-05-memory-system-summary-archive.md
git commit -m "docs: add summary and archive implementation plan"
```
