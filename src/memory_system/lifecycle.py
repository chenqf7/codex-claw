from __future__ import annotations

from typing import Any

from memory_system.models import MemoryRecord


def memory_record_to_dict(record: MemoryRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "type": record.type,
        "status": record.status,
        "topic_key": record.topic_key,
        "memory_kind": record.memory_kind,
        "project_name": record.project_name,
        "payload": record.payload,
        "source": record.source,
        "supersedes": record.supersedes,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "retrieval_count": record.retrieval_count,
        "last_retrieved_at": record.last_retrieved_at,
        "use_count": record.use_count,
        "last_used_at": record.last_used_at,
    }


def lifecycle_reason_for_record(
    record: MemoryRecord,
    *,
    linked_summary: MemoryRecord | None,
) -> str:
    if record.status == "committed":
        return "summary_memory" if record.type == "summary" else "active_memory"
    if record.status == "superseded":
        return "superseded_by_summary" if linked_summary is not None else "superseded"
    if record.status == "archived":
        return (
            "archived_from_superseded" if linked_summary is not None else "archived"
        )
    return record.status


def build_inspect_payload(
    record: MemoryRecord,
    *,
    linked_summary: MemoryRecord | None,
) -> dict[str, Any]:
    payload = memory_record_to_dict(record)
    lifecycle: dict[str, Any] = {
        "reason": lifecycle_reason_for_record(
            record,
            linked_summary=linked_summary,
        ),
        "summary_id": linked_summary.id if linked_summary is not None else None,
        "summary_topic_key": (
            linked_summary.topic_key if linked_summary is not None else None
        ),
        "source_ids": None,
    }

    if record.type == "summary":
        source_ids = record.payload.get("source_ids")
        lifecycle["source_ids"] = list(source_ids) if isinstance(source_ids, list) else None

    payload["lifecycle"] = lifecycle
    return payload


def build_list_payload(
    record: MemoryRecord,
    *,
    linked_summary: MemoryRecord | None,
) -> dict[str, Any]:
    payload = memory_record_to_dict(record)
    payload["lifecycle_reason"] = lifecycle_reason_for_record(
        record,
        linked_summary=linked_summary,
    )
    return payload
