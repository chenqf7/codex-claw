from __future__ import annotations

import argparse
import math
from pathlib import Path

from memory_system.handoff import render_handoff
from memory_system.write_pipeline import ALLOWED_MEMORY_KINDS
from memory_system.schema import bootstrap_database
from memory_system.write_pipeline import MemoryWriter


def bounded_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")
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

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
