from pathlib import Path

from memory_system.handoff import render_handoff
from memory_system.schema import bootstrap_database
from memory_system.write_pipeline import MemoryWriter


def test_render_handoff_creates_orientation_markdown(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)

    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Top durable fact for orientation.",
            "type": "fact",
            "source": "user",
            "topic_key": "handoff",
            "durability": 0.95,
            "cost_of_forgetting": 0.9,
            "unfinished": True,
        }
    )

    render_handoff(db_path, output_path)
    text = output_path.read_text()

    assert "# Current Memory Brief" in text
    assert "Top durable fact for orientation." in text
    assert "Active Pending Items" in text


def test_render_handoff_replaces_existing_brief(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)
    output_path.write_text("stale brief\n", encoding="utf-8")

    writer = MemoryWriter(db_path)
    writer.observe(
        {
            "text": "Replacement durable fact.",
            "type": "fact",
            "source": "user",
            "topic_key": "handoff-replace",
            "durability": 0.95,
            "cost_of_forgetting": 0.9,
            "unfinished": False,
        }
    )

    render_handoff(db_path, output_path)
    text = output_path.read_text(encoding="utf-8")

    assert "stale brief" not in text
    assert "# Current Memory Brief" in text
    assert "Replacement durable fact." in text
