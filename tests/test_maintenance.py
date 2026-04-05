from pathlib import Path

from memory_system.maintenance import MemoryMaintenance
from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository
from memory_system.schema import bootstrap_database


def test_recovery_marks_unclean_session_records_as_suspect(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    maintenance = MemoryMaintenance(db_path)

    maintenance.record_session_start("session-1")
    maintenance.record_staged_memory(
        memory_id="stage-1",
        payload={"text": "Half-written recovery update"},
    )
    maintenance.recover_unclean_sessions()

    suspect_count = maintenance.count_suspect_staging_records()
    assert suspect_count == 1


def test_recovery_without_active_session_leaves_staged_records_unchanged(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    maintenance = MemoryMaintenance(db_path)

    maintenance.record_staged_memory(
        memory_id="stage-1",
        payload={"text": "Healthy staged update"},
    )

    maintenance.recover_unclean_sessions()

    assert maintenance.repository.count_staging(status="staged") == 1
    assert maintenance.count_suspect_staging_records() == 0


def test_recovery_is_one_shot_after_clearing_active_sessions(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    maintenance = MemoryMaintenance(db_path)

    maintenance.record_session_start("session-1")
    maintenance.record_staged_memory(
        memory_id="stage-1",
        payload={"text": "Interrupted recovery update"},
    )
    maintenance.recover_unclean_sessions()

    maintenance.record_staged_memory(
        memory_id="stage-2",
        payload={"text": "Later healthy staged update"},
    )
    maintenance.recover_unclean_sessions()

    assert maintenance.count_suspect_staging_records() == 1
    assert maintenance.repository.count_staging(status="staged") == 1


def test_recovery_marks_only_staging_records_from_active_sessions(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)

    crashed = MemoryMaintenance(db_path)
    crashed.record_session_start("session-crashed")
    crashed.record_staged_memory(
        memory_id="stage-crashed",
        payload={"text": "Interrupted staged update"},
    )

    healthy = MemoryMaintenance(db_path)
    healthy.record_staged_memory(
        memory_id="stage-healthy",
        payload={"text": "Healthy staged update"},
    )

    crashed.recover_unclean_sessions()

    assert crashed.count_suspect_staging_records() == 1
    assert crashed.repository.count_staging(status="staged") == 1


def test_recovery_only_completes_current_session_when_multiple_are_active(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)

    first = MemoryMaintenance(db_path)
    second = MemoryMaintenance(db_path)

    first.record_session_start("session-1")
    second.record_session_start("session-2")
    first.record_staged_memory(
        memory_id="stage-1",
        payload={"text": "First session staged update"},
    )
    second.record_staged_memory(
        memory_id="stage-2",
        payload={"text": "Second session staged update"},
    )

    first.recover_unclean_sessions()

    assert first.count_suspect_staging_records() == 1
    assert first.repository.count_staging(status="staged") == 1
    assert second.repository.list_active_session_ids() == ["session-2"]


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
    assert summary.payload["text"] == "Cluster fact 0 | Cluster fact 1 | Cluster fact 2"
    assert summary.payload["source_ids"] == ["mem-0", "mem-1", "mem-2"]
    assert summary.payload["source_type"] == "fact"
    assert all(
        repository.get_memory(f"mem-{index}").status == "superseded"
        for index in range(3)
    )


def test_expire_stale_pending_items_only_when_low_signal(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repo = MemoryRepository(db_path)
    repo.upsert_pending(
        item_id="pending-stale",
        payload={"text": "Old low-signal task"},
        status="active",
        priority=0.2,
        topic_key="cleanup",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    repo.upsert_pending(
        item_id="pending-high",
        payload={"text": "Old high-signal task"},
        status="active",
        priority=0.9,
        topic_key="cleanup",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    maintenance = MemoryMaintenance(db_path)
    expired = maintenance.expire_stale_pending_items(
        stale_before="2026-03-01T00:00:00+00:00",
        max_priority=0.3,
    )

    assert expired == ["pending-stale"]
    assert repo.list_pending(status="expired")[0]["id"] == "pending-stale"
    assert repo.list_pending(status="active")[0]["id"] == "pending-high"


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
