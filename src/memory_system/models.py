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
