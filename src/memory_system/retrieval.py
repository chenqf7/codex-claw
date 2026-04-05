from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_system.repository import MemoryRepository

IGNORED_QUERY_TOKENS = {
    "based",
    "continue",
    "context",
    "depends",
    "fresh",
    "from",
    "last",
    "needs",
    "prior",
    "resume",
    "task",
    "time",
    "work",
}


@dataclass(slots=True)
class RetrievalResult:
    state: str
    summary: str
    memory_ids: list[str]
    pending_items: list[dict]


class MemoryRetriever:
    def __init__(self, db_path: Path) -> None:
        self.repository = MemoryRepository(db_path)

    def classify(self, query_text: str) -> str:
        lowered = query_text.lower()
        if "continue" in lowered or "resume" in lowered or "last time" in lowered:
            return "continuation"
        if "recover" in lowered or "crash" in lowered:
            return "recovery"
        if "based on" in lowered or "depends on" in lowered:
            return "dependency_recall"
        return "fresh_task"

    @staticmethod
    def _preview_texts(records: list[Any], *, limit: int) -> list[str]:
        texts: list[str] = []
        for record in records[:limit]:
            if isinstance(record, dict):
                texts.append(record["payload"]["text"])
            else:
                texts.append(record.payload["text"])
        return texts

    @staticmethod
    def _query_tokens(query_text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", query_text.lower())
            if len(token) >= 4 and token not in IGNORED_QUERY_TOKENS
        }

    @staticmethod
    def _record_search_text(record: Any) -> str:
        if isinstance(record, dict):
            payload_text = record["payload"]["text"]
            topic_key = record["topic_key"]
        else:
            payload_text = record.payload["text"]
            topic_key = record.topic_key
        return f"{topic_key} {payload_text}".lower()

    def _score_records(self, records: list[Any], query_text: str) -> list[tuple[int, Any]]:
        tokens = self._query_tokens(query_text)
        if not tokens:
            return []

        scored: list[tuple[int, Any]] = []
        for record in records:
            haystack = self._record_search_text(record)
            score = sum(token in haystack for token in tokens)
            if score:
                scored.append((score, record))

        if not scored:
            return []

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score = scored[0][0]
        return [item for item in scored if item[0] == best_score]

    def retrieve(self, query_text: str) -> RetrievalResult:
        state = self.classify(query_text)
        pending_items = self.repository.list_pending(status="active")
        memories = self.repository.list_memories(limit=5)
        pending_matches = self._score_records(pending_items, query_text)
        memory_matches = self._score_records(memories, query_text)

        pending_match_score = pending_matches[0][0] if pending_matches else 0
        memory_match_score = memory_matches[0][0] if memory_matches else 0
        matching_pending_items = [record for _, record in pending_matches]
        matching_memories = [record for _, record in memory_matches]

        if matching_pending_items or matching_memories:
            scoped_pending_items = matching_pending_items
            scoped_memories = matching_memories
        else:
            scoped_pending_items = pending_items
            scoped_memories = memories

        pending_summary_parts = self._preview_texts(scoped_pending_items, limit=3)
        memory_summary_parts = self._preview_texts(scoped_memories, limit=3)

        if state in {"continuation", "recovery"}:
            if pending_match_score >= memory_match_score:
                summary_parts = pending_summary_parts or memory_summary_parts
            else:
                summary_parts = memory_summary_parts or pending_summary_parts
        else:
            summary_parts = memory_summary_parts or pending_summary_parts
        return RetrievalResult(
            state=state,
            summary=" | ".join(summary_parts),
            memory_ids=[record.id for record in scoped_memories],
            pending_items=scoped_pending_items,
        )
