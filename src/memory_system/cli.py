from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from memory_system.handoff import render_handoff
from memory_system.lifecycle import build_inspect_payload, build_list_payload
from memory_system.maintenance import MemoryMaintenance
from memory_system.repository import MemoryRepository
from memory_system.write_pipeline import ALLOWED_MEMORY_KINDS
from memory_system.schema import bootstrap_database
from memory_system.write_pipeline import MemoryWriter


def bounded_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory-system")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--db", required=True)

    remember_parser = subparsers.add_parser("remember")
    remember_parser.add_argument("--db", required=True)
    remember_parser.add_argument("--text", required=True)
    remember_parser.add_argument("--type", required=True)
    remember_parser.add_argument("--topic", required=True)
    remember_parser.add_argument("--durability", required=True, type=bounded_float)
    remember_parser.add_argument("--cost", required=True, type=bounded_float)
    remember_parser.add_argument(
        "--kind",
        required=True,
        dest="memory_kind",
        choices=sorted(ALLOWED_MEMORY_KINDS),
    )
    remember_parser.add_argument("--confidence", required=True, type=bounded_float)
    remember_parser.add_argument("--project-name")
    remember_parser.add_argument("--unfinished", action="store_true")

    handoff_parser = subparsers.add_parser("handoff")
    handoff_parser.add_argument("--db", required=True)
    handoff_parser.add_argument("--output", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--db", required=True)
    list_parser.add_argument("--status")
    list_parser.add_argument("--type", dest="memory_type")
    list_parser.add_argument("--topic", dest="topic_key")
    list_parser.add_argument("--limit", type=positive_int, default=10)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--db", required=True)
    inspect_parser.add_argument("--id", required=True)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--db", required=True)
    summarize_parser.add_argument(
        "--min-cluster-size",
        required=True,
        type=positive_int,
    )

    archive_parser = subparsers.add_parser("archive")
    archive_parser.add_argument("--db", required=True)
    archive_parser.add_argument("--stale-before", required=True)

    maintain_parser = subparsers.add_parser("maintain")
    maintain_parser.add_argument("--db", required=True)
    maintain_parser.add_argument(
        "--min-cluster-size",
        required=True,
        type=positive_int,
    )
    maintain_parser.add_argument("--stale-before", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        bootstrap_database(Path(args.db))
        return 0

    if args.command == "remember":
        if args.memory_kind == "project_memory" and not args.project_name:
            parser.error("--project-name is required when --kind is project_memory")
        writer = MemoryWriter(Path(args.db))
        writer.observe(
            {
                "text": args.text,
                "type": args.type,
                "source": "cli",
                "topic_key": args.topic,
                "durability": args.durability,
                "cost_of_forgetting": args.cost,
                "memory_kind": args.memory_kind,
                "confidence": args.confidence,
                "project_name": args.project_name,
                "unfinished": args.unfinished,
            }
        )
        return 0

    if args.command == "handoff":
        render_handoff(Path(args.db), Path(args.output))
        return 0

    if args.command == "list":
        repository = MemoryRepository(Path(args.db))
        records = repository.list_memories(
            limit=args.limit,
            status=args.status,
            memory_type=args.memory_type,
            topic_key=args.topic_key,
        )
        payload = [
            build_list_payload(
                record,
                linked_summary=(
                    repository.get_linked_summary(record.supersedes)
                    if record.supersedes
                    else None
                ),
            )
            for record in records
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "inspect":
        repository = MemoryRepository(Path(args.db))
        record = repository.get_memory(args.id)
        if record is None:
            parser.error(f"Memory not found: {args.id}")
        linked_summary = (
            repository.get_linked_summary(record.supersedes)
            if record.supersedes
            else None
        )
        print(
            json.dumps(
                build_inspect_payload(record, linked_summary=linked_summary),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "summarize":
        maintenance = MemoryMaintenance(Path(args.db))
        summary_ids = maintenance.summarize_eligible_clusters(
            min_cluster_size=args.min_cluster_size
        )
        print(f"summarized={len(summary_ids)}")
        return 0

    if args.command == "archive":
        maintenance = MemoryMaintenance(Path(args.db))
        archived_ids = maintenance.archive_stale_superseded_memories(
            stale_before=args.stale_before
        )
        print(f"archived={len(archived_ids)}")
        return 0

    if args.command == "maintain":
        maintenance = MemoryMaintenance(Path(args.db))
        summary_ids = maintenance.summarize_eligible_clusters(
            min_cluster_size=args.min_cluster_size
        )
        archived_ids = maintenance.archive_stale_superseded_memories(
            stale_before=args.stale_before
        )
        print(f"summarized={len(summary_ids)} archived={len(archived_ids)}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
