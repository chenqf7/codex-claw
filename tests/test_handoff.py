from pathlib import Path

from memory_system.handoff import render_handoff
from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_handoff_renders_v2_sections(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)
    repo = MemoryRepository(db_path)
    repo.upsert_pending(
        item_id="pending-1",
        payload={"text": "Finish pending lifecycle implementation"},
        status="active",
        priority=0.95,
        topic_key="pending",
        created_at="2026-04-05T00:00:00+00:00",
        updated_at="2026-04-05T00:00:00+00:00",
    )
    repo.upsert_pending(
        item_id="pending-2",
        payload={"text": "This is the lower priority active item."},
        status="active",
        priority=0.2,
        topic_key="pending",
        created_at="2026-04-05T00:00:01+00:00",
        updated_at="2026-04-05T00:00:01+00:00",
    )
    repo.upsert_memory(
        MemoryRecord(
            id="mem-1",
            type="fact",
            payload={"text": "Recent durable context."},
            importance=0.9,
            confidence=0.8,
            freshness=0.7,
            status="committed",
            source="user",
            topic_key="pending",
            supersedes=None,
            created_at="2026-04-05T00:00:00+00:00",
            updated_at="2026-04-05T00:00:02+00:00",
        )
    )

    render_handoff(db_path, output_path)
    content = output_path.read_text()

    assert "## Current Focus" in content
    assert "## Active Pending Items" in content
    assert "## Durable Context" in content
    assert "## Recent Changes" in content
    assert "## Caution Items" in content
    assert "- Finish pending lifecycle implementation" in content
    assert content.index("Finish pending lifecycle implementation") < content.index(
        "This is the lower priority active item."
    )
    assert "- [memory] Recent durable context." in content
    assert "- [pending] Finish pending lifecycle implementation" in content


def test_render_handoff_replaces_existing_brief(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)
    output_path.write_text("stale brief\n", encoding="utf-8")

    repo = MemoryRepository(db_path)
    repo.upsert_pending(
        item_id="pending-1",
        payload={"text": "Replacement pending item."},
        status="active",
        priority=0.9,
        topic_key="handoff-replace",
        created_at="2026-04-05T00:00:00+00:00",
        updated_at="2026-04-05T00:00:00+00:00",
    )
    repo.upsert_pending(
        item_id="pending-2",
        payload={"text": "Recent active item."},
        status="active",
        priority=0.8,
        topic_key="handoff-replace",
        created_at="2026-04-05T00:05:00+00:00",
        updated_at="2026-04-05T00:05:00+00:00",
    )
    repo.upsert_memory(
        MemoryRecord(
            id="mem-1",
            type="fact",
            payload={"text": "Recent durable context."},
            importance=0.9,
            confidence=0.8,
            freshness=0.7,
            status="committed",
            source="user",
            topic_key="handoff-replace",
            supersedes=None,
            created_at="2026-04-05T00:00:00+00:00",
            updated_at="2026-04-05T00:10:00+00:00",
        )
    )

    render_handoff(db_path, output_path)
    content = output_path.read_text(encoding="utf-8")

    assert "stale brief" not in content
    assert "## Current Focus" in content
    assert "## Active Pending Items" in content
    assert "- [pending] Recent active item." in content
    assert "- [memory] Recent durable context." in content


def test_handoff_durable_context_prefers_summary_over_detail_for_same_topic(tmp_path: Path):
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
            status="committed",
            source="test",
            topic_key="alpha",
            supersedes="mem-summary",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )

    render_handoff(db_path, output_path)
    content = output_path.read_text()
    durable_context_section = content.split("## Durable Context\n", maxsplit=1)[1].split(
        "\n## ", maxsplit=1
    )[0]

    assert "Summary of alpha facts" in durable_context_section
    assert "Archived alpha fact" not in durable_context_section


def test_handoff_marks_summary_records_in_durable_context_and_recent_changes(
    tmp_path: Path,
):
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


def test_handoff_includes_suspect_staging_in_caution_items(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    output_path = tmp_path / "current-brief.md"
    bootstrap_database(db_path)
    repo = MemoryRepository(db_path)
    repo.insert_staging_record(
        memory_id="stage-1",
        session_id="session-1",
        payload={"text": "Suspect staging note."},
        status="suspect",
        created_at="2026-04-05T00:00:00+00:00",
    )

    render_handoff(db_path, output_path)
    content = output_path.read_text(encoding="utf-8")

    assert "Suspect staging note." in content
    assert "[staging:suspect]" in content
