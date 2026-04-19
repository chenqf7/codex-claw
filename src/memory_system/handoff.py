from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from memory_system.repository import MemoryRepository


def _format_items(items: Iterable[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["_None_"]


def _memory_line(record) -> str:
    text = record.payload["text"]
    return f"[summary] {text}" if record.type == "summary" else text


def _memory_texts(records) -> list[str]:
    return [_memory_line(record) for record in records]


def _durable_context_records(repository: MemoryRepository, *, limit: int) -> list:
    durable_context = repository.list_memories(limit=limit)
    summarized_topic_keys = {
        record.topic_key for record in durable_context if record.type == "summary"
    }
    return [
        record
        for record in durable_context
        if record.type == "summary" or record.topic_key not in summarized_topic_keys
    ]


def _pending_texts(records) -> list[str]:
    return [record["payload"]["text"] for record in records]


def _staging_texts(records) -> list[str]:
    return [record["payload"]["text"] for record in records]


def _recent_change_lines(repository: MemoryRepository, *, limit: int) -> list[str]:
    recent_memories = repository.list_recent_memories(limit=limit)
    recent_pending_items = repository.list_recent_pending_items(limit=limit)

    recent_changes: list[tuple[str, str, str]] = []
    for record in recent_memories:
        recent_changes.append(
            (
                "memory:summary" if record.type == "summary" else "memory",
                record.updated_at,
                record.payload["text"],
            )
        )
    for record in recent_pending_items:
        recent_changes.append(("pending", record["updated_at"], record["payload"]["text"]))

    recent_changes.sort(key=lambda item: item[1], reverse=True)
    return [f"- [{kind}] {text}" for kind, _, text in recent_changes[:limit]] or ["_None_"]


def render_handoff(db_path: Path, output_path: Path) -> None:
    repository = MemoryRepository(db_path)
    current_focus_items = repository.list_pending(status="active", limit=1)
    active_pending_items = repository.list_pending(status="active", limit=5)
    durable_context = _durable_context_records(repository, limit=5)
    caution_pending_items = repository.list_caution_pending_items(limit=5)
    suspect_staging_items = repository.list_suspect_staging_records(limit=5)

    caution_lines = [
        *[f"- [pending] {text}" for text in _pending_texts(caution_pending_items)],
        *[f"- [staging:suspect] {text}" for text in _staging_texts(suspect_staging_items)],
    ] or ["_None_"]

    lines = [
        "# Current Memory Brief",
        "",
        "## Current Focus",
        *(_format_items(_pending_texts(current_focus_items)) if current_focus_items else ["_None_"]),
        "",
        "## Active Pending Items",
        *(_format_items(_pending_texts(active_pending_items)) if active_pending_items else ["_None_"]),
        "",
        "## Durable Context",
        *(_format_items(_memory_texts(durable_context)) if durable_context else ["_None_"]),
        "",
        "## Recent Changes",
        *_recent_change_lines(repository, limit=5),
        "",
        "## Caution Items",
        *caution_lines,
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines) + "\n"
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_path.parent,
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(output_path)
