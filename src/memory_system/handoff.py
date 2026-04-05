from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from memory_system.repository import MemoryRepository


def render_handoff(db_path: Path, output_path: Path) -> None:
    repository = MemoryRepository(db_path)
    memories = repository.list_memories(limit=5)
    pending_items = repository.list_pending(status="active")
    lines = [
        "# Current Memory Brief",
        "",
        "## Durable Memory",
    ]
    lines.extend(f"- {record.payload['text']}" for record in memories)
    lines.extend(["", "## Active Pending Items"])
    lines.extend(f"- {item['payload']['text']}" for item in pending_items)
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
