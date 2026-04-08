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
            "memory_kind": "handoff_note",
            "project_name": None,
            "confidence": 0.8,
            "unfinished": True,
        }
    )

    snapshot = writer.debug_snapshot()
    assert snapshot["committed_memory_count"] == 1
    assert snapshot["pending_count"] == 1


def test_writer_persists_memory_kind_project_name_and_confidence(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    writer.observe(
        {
            "text": "Project-specific memory should preserve its metadata.",
            "type": "fact",
            "source": "user",
            "topic_key": "project-metadata",
            "durability": 0.95,
            "cost_of_forgetting": 0.95,
            "memory_kind": "project_memory",
            "project_name": "atlas",
            "confidence": 0.61,
            "unfinished": False,
        }
    )

    memory = writer.repository.list_memories(limit=1)[0]
    assert memory is not None
    assert memory.memory_kind == "project_memory"
    assert memory.project_name == "atlas"
    assert memory.confidence == 0.61


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
            "memory_kind": "handoff_note",
            "project_name": None,
            "confidence": 0.8,
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
            "memory_kind": "handoff_note",
            "project_name": None,
            "confidence": 0.8,
            "unfinished": True,
        }
    )

    snapshot = writer.debug_snapshot()
    assert snapshot["committed_memory_count"] == 0
    assert snapshot["pending_count"] == 1


def test_writer_rejects_invalid_memory_kind(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    with pytest.raises(ValueError, match="memory_kind"):
        writer.observe(
            {
                "text": "Unsupported memory kind should be rejected.",
                "type": "fact",
                "source": "user",
                "topic_key": "invalid-kind",
                "durability": 0.9,
                "cost_of_forgetting": 0.9,
                "memory_kind": "summary",
                "project_name": None,
                "confidence": 0.8,
                "unfinished": False,
            }
        )


def test_writer_rejects_missing_project_name_for_project_memory(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    with pytest.raises(ValueError, match="project_name"):
        writer.observe(
            {
                "text": "Project memory requires a project name.",
                "type": "fact",
                "source": "user",
                "topic_key": "missing-project",
                "durability": 0.9,
                "cost_of_forgetting": 0.9,
                "memory_kind": "project_memory",
                "confidence": 0.8,
                "unfinished": False,
            }
        )


@pytest.mark.parametrize("field_name", ["durability", "cost_of_forgetting", "confidence"])
def test_writer_rejects_boolean_scores(tmp_path: Path, field_name: str):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    observation = {
        "text": "Boolean score input should be rejected.",
        "type": "fact",
        "source": "user",
        "topic_key": "boolean-score",
        "durability": 0.9,
        "cost_of_forgetting": 0.9,
        "memory_kind": "handoff_note",
        "project_name": None,
        "confidence": 0.8,
        "unfinished": False,
    }
    observation[field_name] = True

    with pytest.raises(ValueError, match=field_name):
        writer.observe(observation)


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
                "memory_kind": "handoff_note",
                "project_name": None,
                "confidence": 0.8,
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


def test_writer_rejects_whitespace_project_name_for_non_project_memory(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    writer = MemoryWriter(db_path)

    with pytest.raises(ValueError, match="project_name"):
        writer.observe(
            {
                "text": "Whitespace project names should not be accepted.",
                "type": "fact",
                "source": "user",
                "topic_key": "whitespace-project-name",
                "durability": 0.9,
                "cost_of_forgetting": 0.9,
                "memory_kind": "handoff_note",
                "project_name": "   ",
                "confidence": 0.8,
                "unfinished": False,
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
                "memory_kind": "handoff_note",
                "project_name": None,
                "confidence": 0.8,
                "unfinished": "false",
            }
        )
