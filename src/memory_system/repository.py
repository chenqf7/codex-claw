from __future__ import annotations

import json
from pathlib import Path

from memory_system.models import MemoryRecord
from memory_system.store import connect, transaction


class MemoryRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def upsert_memory(self, record: MemoryRecord) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, type, payload, importance, confidence, freshness,
                    status, source, topic_key, supersedes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type = excluded.type,
                    payload = excluded.payload,
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

    def get_memory(self, record_id: str) -> MemoryRecord | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
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
        )

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
    ) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pending_items (id, payload, status, priority, topic_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    status = excluded.status,
                    priority = excluded.priority,
                    topic_key = excluded.topic_key,
                    updated_at = excluded.updated_at
                """,
                (
                    item_id,
                    json.dumps(payload, sort_keys=True),
                    status,
                    priority,
                    topic_key,
                    created_at,
                    updated_at,
                ),
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

    def list_memories(self, *, limit: int) -> list[MemoryRecord]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'committed' ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            MemoryRecord(
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
            )
            for row in rows
        ]

    def list_pending(self, *, status: str) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM pending_items WHERE status = ? ORDER BY priority DESC, updated_at DESC",
                (status,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "payload": json.loads(row["payload"]),
                "status": row["status"],
                "priority": row["priority"],
                "topic_key": row["topic_key"],
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
