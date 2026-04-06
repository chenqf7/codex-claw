import json
from pathlib import Path

from memory_system.models import MemoryRecord
from memory_system.retrieval import MemoryRetriever
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database
from memory_system.store import connect
from memory_system.write_pipeline import MemoryWriter


def test_retrieval_falls_back_to_committed_memory_for_fresh_queries(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Durable memory summary for the retrieval path.",
            "type": "decision",
            "source": "user",
            "topic_key": "fresh-task",
            "durability": 0.9,
            "cost_of_forgetting": 0.95,
            "unfinished": False,
        }
    )
    writer.observe(
        {
            "text": "Pending notes should not drive fresh-task summaries.",
            "type": "decision",
            "source": "user",
            "topic_key": "fresh-task",
            "durability": 0.2,
            "cost_of_forgetting": 0.2,
            "unfinished": True,
        }
    )

    repository = MemoryRepository(db_path)
    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("a fresh task that needs prior context")

    committed_ids = [record.id for record in repository.list_memories(limit=5)]

    assert result.state == "fresh_task"
    assert result.summary == "Durable memory summary for the retrieval path."
    assert result.memory_ids == committed_ids
    assert result.pending_items
    assert "Pending notes should not drive fresh-task summaries." not in result.summary


def test_retrieval_prioritizes_pending_work_for_continuation_queries(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Durable recovery note that should stay in memory_ids.",
            "type": "decision",
            "source": "user",
            "topic_key": "recovery",
            "durability": 0.9,
            "cost_of_forgetting": 0.95,
            "unfinished": False,
        }
    )
    writer.observe(
        {
            "text": "Pending crash recovery markers should drive continuation.",
            "type": "decision",
            "source": "user",
            "topic_key": "recovery",
            "durability": 0.2,
            "cost_of_forgetting": 0.8,
            "unfinished": True,
        }
    )

    repository = MemoryRepository(db_path)
    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("continue the crash recovery work from last time")

    committed_ids = [record.id for record in repository.list_memories(limit=5)]

    assert result.state == "continuation"
    assert result.summary == "Pending crash recovery markers should drive continuation."
    assert result.memory_ids == committed_ids
    assert result.pending_items


def test_retrieval_filters_results_to_matching_topic(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Alpha project deployment decision.",
            "type": "decision",
            "source": "user",
            "topic_key": "alpha-deploy",
            "durability": 0.95,
            "cost_of_forgetting": 0.95,
            "unfinished": False,
        }
    )
    writer.observe(
        {
            "text": "Beta analytics migration note.",
            "type": "decision",
            "source": "user",
            "topic_key": "beta-analytics",
            "durability": 0.95,
            "cost_of_forgetting": 0.95,
            "unfinished": False,
        }
    )
    writer.observe(
        {
            "text": "Finish alpha deploy checklist.",
            "type": "task",
            "source": "user",
            "topic_key": "alpha-deploy",
            "durability": 0.2,
            "cost_of_forgetting": 0.9,
            "unfinished": True,
        }
    )
    writer.observe(
        {
            "text": "Finish beta analytics checklist.",
            "type": "task",
            "source": "user",
            "topic_key": "beta-analytics",
            "durability": 0.2,
            "cost_of_forgetting": 0.9,
            "unfinished": True,
        }
    )

    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("continue alpha deploy work from last time")

    assert result.state == "continuation"
    assert "alpha" in result.summary.lower()
    assert "beta" not in result.summary.lower()
    assert len(result.pending_items) == 1
    assert result.pending_items[0]["topic_key"] == "alpha-deploy"
    assert len(result.memory_ids) == 1


def test_retrieval_does_not_leak_unmatched_pending_items(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Alpha deployment decision.",
            "type": "decision",
            "source": "user",
            "topic_key": "alpha-deploy",
            "durability": 0.95,
            "cost_of_forgetting": 0.95,
            "unfinished": False,
        }
    )
    writer.observe(
        {
            "text": "Beta analytics checklist should stay isolated.",
            "type": "task",
            "source": "user",
            "topic_key": "beta-analytics",
            "durability": 0.2,
            "cost_of_forgetting": 0.9,
            "unfinished": True,
        }
    )

    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("continue alpha deploy work from last time")

    assert result.summary == "Alpha deployment decision."
    assert result.pending_items == []
    assert len(result.memory_ids) == 1


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
            id="mem-fact",
            type="fact",
            payload={"text": "Alpha facts from the current work"},
            importance=1.0,
            confidence=0.9,
            freshness=0.9,
            status="committed",
            source="test",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-05T01:00:00+00:00",
            updated_at="2026-04-05T01:00:00+00:00",
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

    assert result.memory_ids[0] == "mem-summary"
    assert "Summary of alpha facts" in result.summary


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
    writer.observe(
        {
            "text": "Refresh the current brief and related pending work",
            "type": "task",
            "source": "test",
            "topic_key": "handoff",
            "durability": 0.2,
            "cost_of_forgetting": 0.8,
            "unfinished": True,
        }
    )

    repository = MemoryRepository(db_path)
    retriever = MemoryRetriever(db_path)
    result = retriever.retrieve("refresh handoff brief", persist=True)
    retriever.retrieve("refresh handoff brief", persist=True)

    assert result.memory_ids
    assert result.pending_items
    assert repository.count_rows("retrieval_logs") == 2

    memory = repository.get_memory(result.memory_ids[0])
    assert memory.retrieval_count == 2
    assert memory.last_retrieved_at is not None
    assert memory.use_count == 0

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT state, query_text, selected_ids, created_at FROM retrieval_logs ORDER BY rowid"
        ).fetchall()

    assert len(rows) == 2
    expected_ids = set(result.memory_ids + [item["id"] for item in result.pending_items])
    for row in rows:
        assert row["state"] == "fresh_task"
        assert row["query_text"] == "refresh handoff brief"
        assert set(json.loads(row["selected_ids"])) == expected_ids
        assert row["created_at"] is not None


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
    retriever.mark_memory_used(result.memory_ids[0])

    memory = retriever.repository.get_memory(result.memory_ids[0])
    assert memory.use_count == 2
    assert memory.last_used_at is not None
    assert retriever.repository.list_memories(limit=5)[0].use_count == 2


def test_adaptive_weighting_prefers_more_used_memory_when_text_scores_tie(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    now = "2026-04-07T00:00:00+00:00"

    repository.upsert_memory(
        MemoryRecord(
            id="mem-low-use",
            type="fact",
            payload={"text": "Adaptive weighting for retrieval ranking"},
            importance=0.8,
            confidence=0.8,
            freshness=1.0,
            status="committed",
            source="test",
            topic_key="ranking",
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-high-use",
            type="fact",
            payload={"text": "Adaptive weighting for retrieval ranking"},
            importance=0.8,
            confidence=0.8,
            freshness=1.0,
            status="committed",
            source="test",
            topic_key="ranking",
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
    )
    repository.record_retrieval(
        state="fresh_task",
        query_text="adaptive weighting retrieval ranking",
        selected_ids=["mem-high-use"],
        memory_ids=["mem-high-use"],
        pending_item_ids=[],
        created_at=now,
    )
    repository.mark_memory_used("mem-high-use", used_at=now)

    result = MemoryRetriever(db_path).retrieve("adaptive weighting retrieval ranking")

    assert result.memory_ids[0] == "mem-high-use"


def test_adaptive_weighting_keeps_direct_match_ahead_of_high_telemetry_irrelevant_memory(
    tmp_path: Path,
):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repository = MemoryRepository(db_path)
    now = "2026-04-07T00:00:00+00:00"

    repository.upsert_memory(
        MemoryRecord(
            id="mem-direct-match",
            type="fact",
            payload={"text": "Adaptive weighting retrieval ranking details"},
            importance=0.8,
            confidence=0.8,
            freshness=1.0,
            status="committed",
            source="test",
            topic_key="ranking",
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-high-telemetry",
            type="fact",
            payload={"text": "Adaptive weighting history"},
            importance=0.8,
            confidence=0.8,
            freshness=1.0,
            status="committed",
            source="test",
            topic_key="ranking",
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
    )

    for _ in range(5):
        repository.record_retrieval(
            state="fresh_task",
            query_text="adaptive weighting history",
            selected_ids=["mem-high-telemetry"],
            memory_ids=["mem-high-telemetry"],
            pending_item_ids=[],
            created_at=now,
        )
        repository.mark_memory_used("mem-high-telemetry", used_at=now)

    result = MemoryRetriever(db_path).retrieve("adaptive weighting retrieval ranking details")

    assert result.memory_ids[0] == "mem-direct-match"
