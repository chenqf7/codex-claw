from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MemoryRecord:
    id: str
    type: str
    payload: dict[str, Any]
    importance: float
    confidence: float
    freshness: float
    status: str
    source: str
    topic_key: str
    supersedes: str | None
    created_at: str
    updated_at: str
    retrieval_count: int = 0
    last_retrieved_at: str | None = None
    use_count: int = 0
    last_used_at: str | None = None
    memory_kind: str = "handoff_note"
    project_name: str | None = None
