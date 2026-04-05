from pathlib import Path

from memory_system.maintenance import MemoryMaintenance
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
