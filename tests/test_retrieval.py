from pathlib import Path

from memory_system.retrieval import MemoryRetriever
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database
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
