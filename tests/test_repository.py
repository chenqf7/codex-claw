from pathlib import Path

import pytest

from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database
from memory_system.store import connect


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
    assert fetched.retrieval_count == 0
    assert fetched.use_count == 0


def test_repository_round_trips_memory_kind_and_project_name(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    initial = MemoryRecord(
        id="mem-1",
        type="fact",
        payload={"text": "User prefers adaptive memory policies."},
        importance=0.9,
        confidence=0.8,
        freshness=1.0,
        status="committed",
        source="user",
        topic_key="memory-policy",
        memory_kind="handoff_note",
        project_name="alpha",
        supersedes=None,
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T00:00:00Z",
    )
    updated = MemoryRecord(
        id="mem-1",
        type="fact",
        payload={"text": "User prefers memory kinds per project."},
        importance=0.95,
        confidence=0.85,
        freshness=0.9,
        status="committed",
        source="system",
        topic_key="memory-policy",
        memory_kind="summary",
        project_name="beta",
        supersedes=None,
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T01:00:00Z",
    )

    repository.upsert_memory(initial)
    repository.upsert_memory(updated)

    fetched = repository.get_memory("mem-1")
    listed = repository.list_memories(limit=5)

    assert fetched is not None
    assert fetched.memory_kind == "summary"
    assert fetched.project_name == "beta"
    assert fetched.payload == {"text": "User prefers memory kinds per project."}
    assert listed[0].memory_kind == "summary"
    assert listed[0].project_name == "beta"


def test_repository_list_memories_supports_status_type_and_topic_filters(
    tmp_path: Path,
):
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
    repository.upsert_memory(
        MemoryRecord(
            id="mem-3",
            type="summary",
            payload={"text": "Beta summary", "source_ids": ["mem-4"]},
            importance=1.0,
            confidence=1.0,
            freshness=1.0,
            status="committed",
            source="system",
            topic_key="beta",
            supersedes=None,
            created_at="2026-04-14T00:00:01Z",
            updated_at="2026-04-14T00:00:01Z",
        )
    )

    rows = repository.list_memories(
        limit=5,
        status="committed",
        memory_type="fact",
        topic_key="alpha",
    )

    assert [row.id for row in rows] == ["mem-1"]


def test_repository_get_linked_summary_target(tmp_path: Path):
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


def test_repository_migrates_v1_pending_schema_on_open(tmp_path: Path):
    db_path = tmp_path / "memory.db"

    import sqlite3

    with sqlite3.connect(db_path) as conn:
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
        conn.execute(
            """
            INSERT INTO pending_items (id, payload, status, priority, topic_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pending-1",
                '{"text": "Existing V1 pending item."}',
                "active",
                0.9,
                "workflow",
                "2026-04-05T00:00:00Z",
                "2026-04-05T00:00:00Z",
            ),
        )
        conn.commit()

    repository = MemoryRepository(db_path)

    pending_items = repository.list_pending(status="active")

    assert pending_items[0]["id"] == "pending-1"
    assert pending_items[0]["closed_at"] is None


def test_repository_upsert_overwrites_existing_memory_fields(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    initial = MemoryRecord(
        id="mem-1",
        type="fact",
        payload={"text": "Original value."},
        importance=0.1,
        confidence=0.2,
        freshness=0.3,
        status="draft",
        source="user",
        topic_key="original-topic",
        supersedes=None,
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T00:00:00Z",
    )
    updated = MemoryRecord(
        id="mem-1",
        type="note",
        payload={"text": "Updated value."},
        importance=0.9,
        confidence=0.8,
        freshness=0.7,
        status="committed",
        source="system",
        topic_key="updated-topic",
        supersedes="mem-0",
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T01:00:00Z",
    )

    repository.upsert_memory(initial)
    repository.upsert_memory(updated)
    fetched = repository.get_memory("mem-1")

    assert fetched is not None
    assert fetched.type == "note"
    assert fetched.payload == {"text": "Updated value."}
    assert fetched.importance == 0.9
    assert fetched.confidence == 0.8
    assert fetched.freshness == 0.7
    assert fetched.status == "committed"
    assert fetched.source == "system"
    assert fetched.topic_key == "updated-topic"
    assert fetched.supersedes == "mem-0"
    assert fetched.created_at == "2026-04-05T00:00:00Z"
    assert fetched.updated_at == "2026-04-05T01:00:00Z"


def test_repository_upsert_overwrites_existing_pending_fields(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    repository.upsert_pending(
        item_id="pending-1",
        payload={"text": "Original value."},
        status="active",
        priority=0.1,
        topic_key="original-topic",
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T00:00:00Z",
    )
    repository.upsert_pending(
        item_id="pending-1",
        payload={"text": "Updated value."},
        status="resolved",
        priority=0.9,
        topic_key="updated-topic",
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T01:00:00Z",
    )

    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM pending_items WHERE id = ?", ("pending-1",)).fetchone()

    assert row is not None
    assert row["payload"] == '{"text": "Updated value."}'
    assert row["status"] == "resolved"
    assert row["priority"] == 0.9
    assert row["topic_key"] == "updated-topic"
    assert row["created_at"] == "2026-04-05T00:00:00Z"
    assert row["updated_at"] == "2026-04-05T01:00:00Z"


def test_repository_upsert_overwrites_existing_pending_lifecycle_fields(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    repository.upsert_pending(
        item_id="pending-1",
        payload={"text": "Original value."},
        status="resolved",
        priority=0.1,
        topic_key="original-topic",
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T00:00:00Z",
        closed_at="2026-04-05T00:30:00Z",
        supersedes="pending-0",
        reopened_from="pending-0",
    )
    repository.upsert_pending(
        item_id="pending-1",
        payload={"text": "Updated value."},
        status="reopened",
        priority=0.9,
        topic_key="updated-topic",
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T01:00:00Z",
        closed_at=None,
        supersedes="pending-2",
        reopened_from="pending-2",
    )

    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM pending_items WHERE id = ?", ("pending-1",)).fetchone()

    assert row is not None
    assert row["payload"] == '{"text": "Updated value."}'
    assert row["status"] == "reopened"
    assert row["priority"] == 0.9
    assert row["topic_key"] == "updated-topic"
    assert row["closed_at"] is None
    assert row["supersedes"] == "pending-2"
    assert row["reopened_from"] == "pending-2"
    assert row["created_at"] == "2026-04-05T00:00:00Z"
    assert row["updated_at"] == "2026-04-05T01:00:00Z"


def test_repository_count_rows_supports_current_schema_tables(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    assert repository.count_rows("memories") == 0
    assert repository.count_rows("pending_items") == 0
    assert repository.count_rows("staging_memories") == 0
    assert repository.count_rows("episodes") == 0
    assert repository.count_rows("sessions") == 0
    assert repository.count_rows("integrity_events") == 0
    assert repository.count_rows("retrieval_logs") == 0
    assert repository.count_rows("policy_state") == 0


def test_repository_lists_committed_and_active_records_in_priority_order(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="mem-1",
            type="fact",
            payload={"text": "Lower-importance committed memory."},
            importance=0.4,
            confidence=0.8,
            freshness=0.9,
            status="committed",
            source="user",
            topic_key="topic-a",
            supersedes=None,
            created_at="2026-04-05T00:00:00Z",
            updated_at="2026-04-05T01:00:00Z",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-2",
            type="fact",
            payload={"text": "Draft memory should not be returned."},
            importance=0.9,
            confidence=0.8,
            freshness=0.9,
            status="draft",
            source="user",
            topic_key="topic-b",
            supersedes=None,
            created_at="2026-04-05T00:00:00Z",
            updated_at="2026-04-05T02:00:00Z",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-3",
            type="fact",
            payload={"text": "Higher-importance committed memory."},
            importance=0.9,
            confidence=0.8,
            freshness=0.9,
            status="committed",
            source="user",
            topic_key="topic-c",
            supersedes=None,
            created_at="2026-04-05T00:00:00Z",
            updated_at="2026-04-05T00:30:00Z",
        )
    )

    repository.upsert_pending(
        item_id="pending-1",
        payload={"text": "Lower-priority active pending item."},
        status="active",
        priority=0.5,
        topic_key="topic-a",
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T01:00:00Z",
    )
    repository.upsert_pending(
        item_id="pending-2",
        payload={"text": "Higher-priority active pending item."},
        status="active",
        priority=0.9,
        topic_key="topic-b",
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T00:30:00Z",
    )
    repository.upsert_pending(
        item_id="pending-3",
        payload={"text": "Resolved pending item should be filtered out."},
        status="resolved",
        priority=1.0,
        topic_key="topic-c",
        created_at="2026-04-05T00:00:00Z",
        updated_at="2026-04-05T00:45:00Z",
    )

    records = repository.list_memories(limit=5)

    assert [record.id for record in records] == ["mem-3", "mem-1"]
    assert [record.retrieval_count for record in records] == [0, 0]
    assert [record.use_count for record in records] == [0, 0]
    assert [item["id"] for item in repository.list_pending(status="active")] == [
        "pending-2",
        "pending-1",
    ]


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


def test_repository_excludes_non_committed_memories_from_summary_clusters(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="mem-committed",
            type="fact",
            payload={"text": "Committed memory should be eligible."},
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
            id="mem-draft",
            type="fact",
            payload={"text": "Draft memory should be excluded."},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="draft",
            source="test",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-05T00:00:01+00:00",
            updated_at="2026-04-05T00:00:01+00:00",
        )
    )

    clusters = repository.list_summary_candidate_clusters(min_cluster_size=1)

    assert clusters == [
        {
            "topic_key": "alpha",
            "type": "fact",
            "memory_ids": ["mem-committed"],
        }
    ]


def test_repository_orders_summary_candidate_clusters_deterministically(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="mem-beta-2",
            type="fact",
            payload={"text": "Beta cluster later row."},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="committed",
            source="test",
            topic_key="beta",
            supersedes=None,
            created_at="2026-04-05T00:00:02+00:00",
            updated_at="2026-04-05T00:00:02+00:00",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-alpha-1",
            type="fact",
            payload={"text": "Alpha cluster later row."},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="committed",
            source="test",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-05T00:00:03+00:00",
            updated_at="2026-04-05T00:00:03+00:00",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-beta-1",
            type="fact",
            payload={"text": "Beta cluster first row."},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="committed",
            source="test",
            topic_key="beta",
            supersedes=None,
            created_at="2026-04-05T00:00:01+00:00",
            updated_at="2026-04-05T00:00:01+00:00",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-alpha-0",
            type="fact",
            payload={"text": "Alpha cluster first row."},
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

    clusters = repository.list_summary_candidate_clusters(min_cluster_size=2)

    assert [cluster["topic_key"] for cluster in clusters] == ["alpha", "beta"]
    assert [cluster["memory_ids"] for cluster in clusters] == [
        ["mem-alpha-0", "mem-alpha-1"],
        ["mem-beta-1", "mem-beta-2"],
    ]


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

    summary_id = repository.create_summary_and_supersede_sources(
        topic_key="alpha",
        source_type="fact",
        source_ids=["mem-1", "mem-2"],
        summary_text="Summary of alpha facts",
        created_at="2026-04-05T01:00:00+00:00",
    )

    summary = repository.get_memory(summary_id)
    first = repository.get_memory("mem-1")
    second = repository.get_memory("mem-2")

    assert summary is not None
    assert summary.type == "summary"
    assert summary.status == "committed"
    assert summary.source == "system"
    assert summary.topic_key == "alpha"
    assert summary.supersedes is None
    assert summary.payload["text"] == "Summary of alpha facts"
    assert summary.payload["source_ids"] == ["mem-1", "mem-2"]
    assert summary.payload["source_type"] == "fact"
    assert first is not None and first.status == "superseded"
    assert second is not None and second.status == "superseded"
    assert first.supersedes == summary_id
    assert second.supersedes == summary_id


@pytest.mark.parametrize(
    ("new_status", "expected_closed_at"),
    [
        ("resolved", "2026-04-05T01:00:00+00:00"),
        ("cancelled", "2026-04-05T01:00:00+00:00"),
        ("expired", "2026-04-05T01:00:00+00:00"),
    ],
)
def test_terminal_pending_item_transitions_stamp_closed_at(
    tmp_path: Path,
    new_status: str,
    expected_closed_at: str,
):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    repository.upsert_pending(
        item_id="pending-1",
        payload={"text": "Finish handoff refresh"},
        status="active",
        priority=0.9,
        topic_key="handoff",
        created_at="2026-04-05T00:00:00+00:00",
        updated_at="2026-04-05T00:00:00+00:00",
    )

    repository.transition_pending_item(
        item_id="pending-1",
        new_status=new_status,
        updated_at="2026-04-05T01:00:00+00:00",
    )

    pending = repository.list_pending(status=new_status)
    assert pending[0]["status"] == new_status
    assert pending[0]["closed_at"] == expected_closed_at


def test_non_terminal_pending_item_transition_clears_closed_at(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    repository.upsert_pending(
        item_id="pending-1",
        payload={"text": "Finish handoff refresh"},
        status="resolved",
        priority=0.9,
        topic_key="handoff",
        created_at="2026-04-05T00:00:00+00:00",
        updated_at="2026-04-05T00:00:00+00:00",
        closed_at="2026-04-05T01:00:00+00:00",
    )

    repository.transition_pending_item(
        item_id="pending-1",
        new_status="in_progress",
        updated_at="2026-04-05T02:00:00+00:00",
    )

    pending = repository.list_pending(status="in_progress")
    assert pending[0]["status"] == "in_progress"
    assert pending[0]["closed_at"] is None


def test_pending_item_can_be_reopened_with_lineage(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    repository.upsert_pending(
        item_id="pending-1",
        payload={"text": "Resume memory cleanup"},
        status="resolved",
        priority=0.8,
        topic_key="maintenance",
        created_at="2026-04-05T00:00:00+00:00",
        updated_at="2026-04-05T00:00:00+00:00",
    )

    repository.reopen_pending_item(
        item_id="pending-2",
        previous_item_id="pending-1",
        payload={"text": "Resume memory cleanup"},
        priority=0.8,
        topic_key="maintenance",
        created_at="2026-04-05T02:00:00+00:00",
    )

    reopened = repository.list_pending(status="reopened")
    assert reopened[0]["reopened_from"] == "pending-1"
    assert reopened[0]["supersedes"] == "pending-1"
    assert reopened[0]["closed_at"] is None
