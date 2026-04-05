from pathlib import Path

import pytest

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


def test_writer_commits_only_when_durable_and_complete(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    writer.observe(
        {
            "text": "User wants durable memory but no pending follow-up.",
            "type": "fact",
            "source": "user",
            "topic_key": "durable-only",
            "durability": 0.95,
            "cost_of_forgetting": 0.95,
            "unfinished": False,
        }
    )

    snapshot = writer.debug_snapshot()
    assert snapshot["committed_memory_count"] == 1
    assert snapshot["pending_count"] == 0


def test_writer_tracks_pending_only_when_unfinished(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    writer.observe(
        {
            "text": "User wants a follow-up task but not durable storage.",
            "type": "fact",
            "source": "user",
            "topic_key": "pending-only",
            "durability": 0.2,
            "cost_of_forgetting": 0.95,
            "unfinished": True,
        }
    )

    snapshot = writer.debug_snapshot()
    assert snapshot["committed_memory_count"] == 0
    assert snapshot["pending_count"] == 1


def test_writer_rejects_invalid_scores(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    with pytest.raises(ValueError, match="durability"):
        writer.observe(
            {
                "text": "Invalid score input.",
                "type": "fact",
                "source": "user",
                "topic_key": "invalid-score",
                "durability": 1.5,
                "cost_of_forgetting": 0.9,
                "unfinished": False,
            }
        )


def test_writer_rejects_missing_required_keys(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    with pytest.raises(ValueError, match="missing required keys"):
        writer.observe(
            {
                "text": "Missing source and scores.",
                "type": "fact",
                "topic_key": "missing-fields",
            }
        )


def test_writer_rejects_non_boolean_unfinished_values(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    with pytest.raises(ValueError, match="unfinished must be a boolean"):
        writer.observe(
            {
                "text": "Invalid unfinished flag.",
                "type": "fact",
                "source": "user",
                "topic_key": "invalid-flag",
                "durability": 0.9,
                "cost_of_forgetting": 0.9,
                "unfinished": "false",
            }
        )
