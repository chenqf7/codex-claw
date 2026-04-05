from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from memory_system.repository import MemoryRepository


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryMaintenance:
    def __init__(self, db_path: Path) -> None:
        self.repository = MemoryRepository(db_path)
        self.current_session_id: str | None = None

    def record_session_start(self, session_id: str) -> None:
        self.current_session_id = session_id
        self.repository.upsert_session(
            session_id=session_id,
            state="active",
            started_at=utc_now(),
        )

    def record_staged_memory(self, *, memory_id: str, payload: dict) -> None:
        self.repository.insert_staging_record(
            memory_id=memory_id,
            session_id=self.current_session_id,
            payload=payload,
            status="staged",
            created_at=utc_now(),
        )

    def recover_unclean_sessions(self) -> None:
        active_session_ids = self.repository.list_active_session_ids()
        if self.current_session_id is not None:
            target_session_ids = [
                session_id
                for session_id in active_session_ids
                if session_id == self.current_session_id
            ]
        elif len(active_session_ids) == 1:
            target_session_ids = active_session_ids
        else:
            target_session_ids = []

        if target_session_ids:
            self.repository.mark_staging_as_suspect_for_sessions(session_ids=target_session_ids)
            self.repository.complete_sessions(
                session_ids=target_session_ids,
                completed_at=utc_now(),
            )
            if self.current_session_id in target_session_ids:
                self.current_session_id = None

    def count_suspect_staging_records(self) -> int:
        return self.repository.count_staging(status="suspect")
