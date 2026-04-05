from pathlib import Path

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

    assert [record.id for record in repository.list_memories(limit=5)] == ["mem-3", "mem-1"]
    assert [item["id"] for item in repository.list_pending(status="active")] == [
        "pending-2",
        "pending-1",
    ]
