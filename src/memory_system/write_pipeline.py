from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


REQUIRED_OBSERVATION_KEYS = {
    "text",
    "type",
    "source",
    "topic_key",
    "durability",
    "cost_of_forgetting",
}


def _require_score(name: str, value: object) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number between 0 and 1")
    score = float(value)
    if not math.isfinite(score) or score < 0 or score > 1:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return score


def validate_observation(observation: dict) -> dict:
    missing_keys = REQUIRED_OBSERVATION_KEYS.difference(observation)
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"Observation is missing required keys: {missing}")

    if not isinstance(observation["text"], str) or not observation["text"].strip():
        raise ValueError("text must be a non-empty string")
    if not isinstance(observation["type"], str) or not observation["type"].strip():
        raise ValueError("type must be a non-empty string")
    if not isinstance(observation["source"], str) or not observation["source"].strip():
        raise ValueError("source must be a non-empty string")
    if not isinstance(observation["topic_key"], str) or not observation["topic_key"].strip():
        raise ValueError("topic_key must be a non-empty string")

    validated = dict(observation)
    validated["durability"] = _require_score("durability", observation["durability"])
    validated["cost_of_forgetting"] = _require_score(
        "cost_of_forgetting",
        observation["cost_of_forgetting"],
    )
    unfinished = observation.get("unfinished", False)
    if not isinstance(unfinished, bool):
        raise ValueError("unfinished must be a boolean value")
    validated["unfinished"] = unfinished
    return validated


class MemoryWriter:
    def __init__(self, db_path: Path) -> None:
        self.repository = MemoryRepository(db_path)

    def observe(self, observation: dict) -> None:
        observation = validate_observation(observation)
        now = utc_now()
        if observation["durability"] >= 0.7 and observation["cost_of_forgetting"] >= 0.7:
            record = MemoryRecord(
                id=f"mem-{uuid4()}",
                type=observation["type"],
                payload={"text": observation["text"]},
                importance=observation["cost_of_forgetting"],
                confidence=0.8,
                freshness=1.0,
                status="committed",
                source=observation["source"],
                topic_key=observation["topic_key"],
                supersedes=None,
                created_at=now,
                updated_at=now,
            )
            self.repository.upsert_memory(record)

        if observation.get("unfinished"):
            self.repository.upsert_pending(
                item_id=f"pending-{uuid4()}",
                payload={"text": observation["text"]},
                status="active",
                priority=observation["cost_of_forgetting"],
                topic_key=observation["topic_key"],
                created_at=now,
                updated_at=now,
            )

    def debug_snapshot(self) -> dict[str, int]:
        return {
            "committed_memory_count": self.repository.count_memories(status="committed"),
            "pending_count": self.repository.count_rows("pending_items"),
        }
