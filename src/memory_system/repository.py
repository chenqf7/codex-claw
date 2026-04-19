from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from memory_system.models import MemoryRecord
from memory_system.schema import bootstrap_database
from memory_system.store import connect, transaction


class MemoryRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        bootstrap_database(self.db_path)

    @staticmethod
    def _pending_item_from_row(row) -> dict:
        return {
            "id": row["id"],
            "payload": json.loads(row["payload"]),
            "status": row["status"],
            "priority": row["priority"],
            "topic_key": row["topic_key"],
            "closed_at": row["closed_at"],
            "supersedes": row["supersedes"],
            "reopened_from": row["reopened_from"],
            "retrieval_count": row["retrieval_count"],
            "last_retrieved_at": row["last_retrieved_at"],
            "use_count": row["use_count"],
            "last_used_at": row["last_used_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _memory_from_row(row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            type=row["type"],
            payload=json.loads(row["payload"]),
            importance=row["importance"],
            confidence=row["confidence"],
            freshness=row["freshness"],
            status=row["status"],
            source=row["source"],
            topic_key=row["topic_key"],
            supersedes=row["supersedes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            retrieval_count=row["retrieval_count"],
            last_retrieved_at=row["last_retrieved_at"],
            use_count=row["use_count"],
            last_used_at=row["last_used_at"],
            memory_kind=row["memory_kind"],
            project_name=row["project_name"],
        )

    def upsert_memory(self, record: MemoryRecord) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, type, payload, memory_kind, project_name,
                    importance, confidence, freshness,
                    status, source, topic_key, supersedes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type = excluded.type,
                    payload = excluded.payload,
                    memory_kind = excluded.memory_kind,
                    project_name = excluded.project_name,
                    importance = excluded.importance,
                    confidence = excluded.confidence,
                    freshness = excluded.freshness,
                    status = excluded.status,
                    source = excluded.source,
                    topic_key = excluded.topic_key,
                    supersedes = excluded.supersedes,
                    updated_at = excluded.updated_at
                """,
                (
                    record.id,
                    record.type,
                    json.dumps(record.payload, sort_keys=True),
                    record.memory_kind,
                    record.project_name,
                    record.importance,
                    record.confidence,
                    record.freshness,
                    record.status,
                    record.source,
                    record.topic_key,
                    record.supersedes,
                    record.created_at,
                    record.updated_at,
                ),
            )

    def create_summary_memory(
        self,
        *,
        topic_key: str,
        source_type: str,
        source_ids: list[str],
        summary_text: str,
        created_at: str,
    ) -> str:
        summary_id = f"summary-{uuid4().hex}"
        record = MemoryRecord(
            id=summary_id,
            type="summary",
            payload={
                "text": summary_text,
                "source_ids": list(source_ids),
                "source_type": source_type,
            },
            importance=1.0,
            confidence=1.0,
            freshness=1.0,
            status="committed",
            source="system",
            topic_key=topic_key,
            supersedes=None,
            created_at=created_at,
            updated_at=created_at,
        )
        self.upsert_memory(record)
        return summary_id

    def create_summary_and_supersede_sources(
        self,
        *,
        topic_key: str,
        source_type: str,
        source_ids: list[str],
        summary_text: str,
        created_at: str,
    ) -> str:
        summary_id = f"summary-{uuid4().hex}"
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, type, payload, memory_kind, project_name,
                    importance, confidence, freshness,
                    status, source, topic_key, supersedes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_id,
                    "summary",
                    json.dumps(
                        {
                            "text": summary_text,
                            "source_ids": list(source_ids),
                            "source_type": source_type,
                        },
                        sort_keys=True,
                    ),
                    "handoff_note",
                    None,
                    1.0,
                    1.0,
                    1.0,
                    "committed",
                    "system",
                    topic_key,
                    None,
                    created_at,
                    created_at,
                ),
            )
            for memory_id in source_ids:
                conn.execute(
                    """
                    UPDATE memories
                    SET status = 'superseded',
                        supersedes = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (summary_id, created_at, memory_id),
                )
        return summary_id

    def archive_memory(
        self,
        *,
        memory_id: str,
        updated_at: str,
    ) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                UPDATE memories
                SET status = 'archived',
                    updated_at = ?
                WHERE id = ?
                """,
                (updated_at, memory_id),
            )

    def mark_memories_superseded(
        self,
        *,
        memory_ids: list[str],
        summary_id: str,
        updated_at: str,
    ) -> None:
        if not memory_ids:
            return
        with transaction(self.db_path) as conn:
            for memory_id in memory_ids:
                conn.execute(
                    """
                    UPDATE memories
                    SET status = 'superseded',
                        supersedes = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (summary_id, updated_at, memory_id),
                )

    def get_memory(self, record_id: str) -> MemoryRecord | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return self._memory_from_row(row)

    def upsert_pending(
        self,
        *,
        item_id: str,
        payload: dict,
        status: str,
        priority: float,
        topic_key: str,
        created_at: str,
        updated_at: str,
        closed_at: str | None = None,
        supersedes: str | None = None,
        reopened_from: str | None = None,
    ) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pending_items (
                    id, payload, status, priority, topic_key, closed_at, supersedes,
                    reopened_from, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    status = excluded.status,
                    priority = excluded.priority,
                    topic_key = excluded.topic_key,
                    closed_at = excluded.closed_at,
                    supersedes = excluded.supersedes,
                    reopened_from = excluded.reopened_from,
                    updated_at = excluded.updated_at
                """,
                (
                    item_id,
                    json.dumps(payload, sort_keys=True),
                    status,
                    priority,
                    topic_key,
                    closed_at,
                    supersedes,
                    reopened_from,
                    created_at,
                    updated_at,
                ),
            )

    def transition_pending_item(
        self,
        *,
        item_id: str,
        new_status: str,
        updated_at: str,
    ) -> None:
        closed_at = updated_at if new_status in {"resolved", "cancelled", "expired"} else None
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                UPDATE pending_items
                SET status = ?,
                    closed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (new_status, closed_at, updated_at, item_id),
            )

    def reopen_pending_item(
        self,
        *,
        item_id: str,
        previous_item_id: str,
        payload: dict,
        priority: float,
        topic_key: str,
        created_at: str,
    ) -> None:
        self.upsert_pending(
            item_id=item_id,
            payload=payload,
            status="reopened",
            priority=priority,
            topic_key=topic_key,
            created_at=created_at,
            updated_at=created_at,
            closed_at=None,
            supersedes=previous_item_id,
            reopened_from=previous_item_id,
        )

    def count_rows(self, table_name: str) -> int:
        if table_name not in {
            "memories",
            "pending_items",
            "staging_memories",
            "episodes",
            "sessions",
            "integrity_events",
            "retrieval_logs",
            "policy_state",
        }:
            raise ValueError(f"Unsupported table: {table_name}")
        with connect(self.db_path) as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"])

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_retrieval(
        self,
        *,
        state: str,
        query_text: str,
        selected_ids: list[str],
        memory_ids: list[str],
        pending_item_ids: list[str],
        created_at: str | None = None,
    ) -> None:
        occurred_at = created_at or self._utc_now()
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO retrieval_logs (id, state, query_text, selected_ids, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    state,
                    query_text,
                    json.dumps(selected_ids),
                    occurred_at,
                ),
            )
            for table_name, record_ids in (
                ("memories", memory_ids),
                ("pending_items", pending_item_ids),
            ):
                for record_id in record_ids:
                    conn.execute(
                        f"""
                        UPDATE {table_name}
                        SET retrieval_count = retrieval_count + 1,
                            last_retrieved_at = ?
                        WHERE id = ?
                        """,
                        (occurred_at, record_id),
                    )

    def mark_memory_used(self, memory_id: str, *, used_at: str | None = None) -> None:
        occurred_at = used_at or self._utc_now()
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                UPDATE memories
                SET use_count = use_count + 1,
                    last_used_at = ?
                WHERE id = ?
                """,
                (occurred_at, memory_id),
            )

    def count_memories(self, *, status: str | None = None) -> int:
        with connect(self.db_path) as conn:
            if status is None:
                row = conn.execute("SELECT COUNT(*) AS count FROM memories").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS count FROM memories WHERE status = ?",
                    (status,),
                ).fetchone()
        return int(row["count"])

    def list_memories(
        self,
        *,
        limit: int,
        status: str | None = "committed",
        memory_type: str | None = None,
        topic_key: str | None = None,
    ) -> list[MemoryRecord]:
        conditions: list[str] = []
        params: list[object] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if memory_type is not None:
            conditions.append("type = ?")
            params.append(memory_type)
        if topic_key is not None:
            conditions.append("topic_key = ?")
            params.append(topic_key)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with connect(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM memories
                {where_clause}
                ORDER BY
                    CASE WHEN type = 'summary' THEN 0 ELSE 1 END,
                    importance DESC,
                    updated_at DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def get_linked_summary(self, summary_id: str) -> MemoryRecord | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT *
                FROM memories
                WHERE id = ?
                  AND type = 'summary'
                """,
                (summary_id,),
            ).fetchone()
        if row is None:
            return None
        return self._memory_from_row(row)

    def list_summary_candidate_clusters(self, *, min_cluster_size: int) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, type, topic_key, created_at
                FROM memories
                WHERE status = 'committed'
                ORDER BY topic_key ASC, type ASC, created_at ASC, id ASC
                """
            ).fetchall()

        clusters: list[dict] = []
        current_topic_key: str | None = None
        current_type: str | None = None
        current_memory_ids: list[str] = []

        def append_current_cluster() -> None:
            if current_topic_key is None or current_type is None:
                return
            if len(current_memory_ids) < min_cluster_size:
                return
            clusters.append(
                {
                    "topic_key": current_topic_key,
                    "type": current_type,
                    "memory_ids": list(current_memory_ids),
                }
            )

        for row in rows:
            topic_key = row["topic_key"]
            memory_type = row["type"]
            if (topic_key, memory_type) != (current_topic_key, current_type):
                append_current_cluster()
                current_topic_key = topic_key
                current_type = memory_type
                current_memory_ids = []
            current_memory_ids.append(str(row["id"]))

        append_current_cluster()
        return clusters

    def list_stale_superseded_memory_ids(self, *, stale_before: str) -> list[str]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM memories
                WHERE status = 'superseded'
                  AND updated_at < ?
                ORDER BY updated_at ASC, id ASC
                """,
                (stale_before,),
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def list_recent_memories(self, *, limit: int) -> list[MemoryRecord]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'committed' ORDER BY updated_at DESC, importance DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def list_pending(self, *, status: str, limit: int | None = None) -> list[dict]:
        query = "SELECT * FROM pending_items WHERE status = ? ORDER BY priority DESC, updated_at DESC"
        params: tuple[object, ...]
        if limit is None:
            params = (status,)
        else:
            query += " LIMIT ?"
            params = (status, limit)
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._pending_item_from_row(row) for row in rows]

    def list_stale_low_signal_pending_item_ids(
        self,
        *,
        stale_before: str,
        max_priority: float,
    ) -> list[str]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM pending_items
                WHERE status = 'active'
                  AND priority <= ?
                  AND updated_at < ?
                ORDER BY priority ASC, updated_at ASC, id ASC
                """,
                (max_priority, stale_before),
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def list_recent_pending_items(self, *, limit: int) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM pending_items
                ORDER BY updated_at DESC, priority DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._pending_item_from_row(row) for row in rows]

    def list_caution_pending_items(self, *, limit: int) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM pending_items
                WHERE status IN ('reopened', 'resolved', 'cancelled', 'expired')
                ORDER BY updated_at DESC, priority DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._pending_item_from_row(row) for row in rows]

    def list_suspect_staging_records(self, *, limit: int) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM staging_memories
                WHERE status = 'suspect'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "payload": json.loads(row["payload"]),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def upsert_session(self, *, session_id: str, state: str, started_at: str) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, state, started_at, heartbeat_at, completed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET state = excluded.state
                """,
                (session_id, state, started_at, started_at, None),
            )

    def has_active_session(self) -> bool:
        return bool(self.list_active_session_ids())

    def list_active_session_ids(self) -> list[str]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id FROM sessions WHERE state = 'active' ORDER BY started_at ASC"
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def complete_active_sessions(self, *, completed_at: str) -> None:
        active_session_ids = self.list_active_session_ids()
        if not active_session_ids:
            return
        self.complete_sessions(session_ids=active_session_ids, completed_at=completed_at)

    def complete_sessions(self, *, session_ids: list[str], completed_at: str) -> None:
        if not session_ids:
            return
        placeholders = ", ".join("?" for _ in session_ids)
        with transaction(self.db_path) as conn:
            conn.execute(
                f"""
                UPDATE sessions
                SET state = 'recovered',
                    completed_at = ?
                WHERE id IN ({placeholders})
                """,
                (completed_at, *session_ids),
            )

    def insert_staging_record(
        self,
        *,
        memory_id: str,
        session_id: str | None,
        payload: dict,
        status: str,
        created_at: str,
    ) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO staging_memories (id, session_id, payload, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    session_id,
                    json.dumps(payload, sort_keys=True),
                    status,
                    created_at,
                ),
            )

    def mark_all_staging_as_suspect(self) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("UPDATE staging_memories SET status = 'suspect' WHERE status = 'staged'")

    def mark_staging_as_suspect_for_sessions(self, *, session_ids: list[str]) -> None:
        if not session_ids:
            return
        placeholders = ", ".join("?" for _ in session_ids)
        with transaction(self.db_path) as conn:
            conn.execute(
                f"""
                UPDATE staging_memories
                SET status = 'suspect'
                WHERE status = 'staged' AND session_id IN ({placeholders})
                """,
                session_ids,
            )

    def count_staging(self, *, status: str) -> int:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM staging_memories WHERE status = ?",
                (status,),
            ).fetchone()
        return int(row["count"])
