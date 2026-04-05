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

    def expire_stale_pending_items(
        self,
        *,
        stale_before: str,
        max_priority: float,
    ) -> list[str]:
        pending_item_ids = self.repository.list_stale_low_signal_pending_item_ids(
            stale_before=stale_before,
            max_priority=max_priority,
        )
        if not pending_item_ids:
            return []

        expired_at = utc_now()
        for item_id in pending_item_ids:
            self.repository.transition_pending_item(
                item_id=item_id,
                new_status="expired",
                updated_at=expired_at,
            )
        return pending_item_ids

    def summarize_eligible_clusters(self, *, min_cluster_size: int) -> list[str]:
        summary_ids: list[str] = []
        for cluster in self.repository.list_summary_candidate_clusters(
            min_cluster_size=min_cluster_size
        ):
            source_records = []
            for memory_id in cluster["memory_ids"]:
                record = self.repository.get_memory(memory_id)
                if record is None:
                    raise ValueError(f"Missing source memory: {memory_id}")
                source_records.append(record)
            summary_text = " | ".join(record.payload["text"] for record in source_records)
            summary_id = self.repository.create_summary_and_supersede_sources(
                topic_key=cluster["topic_key"],
                source_type=cluster["type"],
                source_ids=cluster["memory_ids"],
                summary_text=summary_text,
                created_at=utc_now(),
            )
            summary_ids.append(summary_id)
        return summary_ids

    def archive_stale_superseded_memories(self, *, stale_before: str) -> list[str]:
        memory_ids = self.repository.list_stale_superseded_memory_ids(
            stale_before=stale_before
        )
        if not memory_ids:
            return []

        archived_at = utc_now()
        for memory_id in memory_ids:
            self.repository.archive_memory(memory_id=memory_id, updated_at=archived_at)
        return memory_ids
