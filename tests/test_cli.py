import json
from pathlib import Path
import subprocess
import sys

import pytest

from memory_system.cli import main
from memory_system.models import MemoryRecord
from memory_system.repository import MemoryRepository


def test_cli_init_and_handoff_workflow(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    handoff_path = tmp_path / "memory" / "current-brief.md"

    main(["init", "--db", str(db_path)])
    main(
        [
            "remember",
            "--db",
            str(db_path),
            "--text",
            "Need to resume unfinished work.",
            "--type",
            "fact",
            "--topic",
            "workflow",
            "--durability",
            "0.9",
            "--cost",
            "0.9",
            "--kind",
            "handoff_note",
            "--confidence",
            "0.8",
            "--unfinished",
        ]
    )
    main(["handoff", "--db", str(db_path), "--output", str(handoff_path)])

    assert handoff_path.exists()
    assert "Need to resume unfinished work." in handoff_path.read_text()


def test_cli_list_outputs_filtered_json_rows(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="summary-1",
            type="summary",
            payload={
                "text": "Alpha summary",
                "source_ids": ["mem-1"],
                "source_type": "fact",
            },
            importance=1.0,
            confidence=1.0,
            freshness=1.0,
            status="committed",
            source="system",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T00:00:00Z",
        )
    )

    main(
        [
            "list",
            "--db",
            str(db_path),
            "--status",
            "committed",
            "--type",
            "summary",
            "--topic",
            "alpha",
            "--limit",
            "5",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["id"] == "summary-1"
    assert payload[0]["lifecycle_reason"] == "summary_memory"


def test_cli_inspect_outputs_summary_linked_lifecycle_json(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="summary-1",
            type="summary",
            payload={
                "text": "Alpha summary",
                "source_ids": ["mem-1"],
                "source_type": "fact",
            },
            importance=1.0,
            confidence=1.0,
            freshness=1.0,
            status="committed",
            source="system",
            topic_key="alpha",
            supersedes=None,
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T00:00:00Z",
        )
    )
    repository.upsert_memory(
        MemoryRecord(
            id="mem-1",
            type="fact",
            payload={"text": "Alpha fact"},
            importance=0.8,
            confidence=0.8,
            freshness=0.8,
            status="superseded",
            source="cli",
            topic_key="alpha",
            supersedes="summary-1",
            created_at="2026-04-14T00:00:00Z",
            updated_at="2026-04-14T01:00:00Z",
        )
    )

    main(["inspect", "--db", str(db_path), "--id", "mem-1"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "mem-1"
    assert payload["lifecycle"]["reason"] == "superseded_by_summary"
    assert payload["lifecycle"]["summary_id"] == "summary-1"
    assert payload["lifecycle"]["summary_topic_key"] == "alpha"


def test_cli_inspect_rejects_missing_memory_id(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    with pytest.raises(SystemExit):
        main(["inspect", "--db", str(db_path), "--id", "missing-id"])

    assert "Memory not found: missing-id" in capsys.readouterr().err


def test_cli_summarize_creates_summary_records(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    for index in range(3):
        main(
            [
                "remember",
                "--db",
                str(db_path),
                "--text",
                f"Cluster fact {index}",
                "--type",
                "fact",
                "--topic",
                "alpha",
                "--durability",
                "0.9",
                "--cost",
                "0.9",
                "--kind",
                "handoff_note",
                "--confidence",
                "0.8",
            ]
        )

    main(
        [
            "summarize",
            "--db",
            str(db_path),
            "--min-cluster-size",
            "3",
        ]
    )

    repository = MemoryRepository(db_path)
    summaries = repository.list_memories(limit=5, status="committed")

    assert len(summaries) == 1
    assert summaries[0].type == "summary"
    assert summaries[0].payload["source_type"] == "fact"
    assert len(summaries[0].payload["source_ids"]) == 3


def test_cli_archive_moves_stale_superseded_memories_to_archived(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])
    repository = MemoryRepository(db_path)

    repository.upsert_memory(
        MemoryRecord(
            id="mem-old",
            type="fact",
            payload={"text": "Old superseded memory"},
            importance=0.5,
            confidence=0.8,
            freshness=0.5,
            status="superseded",
            source="test",
            topic_key="alpha",
            supersedes="summary-1",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )

    main(
        [
            "archive",
            "--db",
            str(db_path),
            "--stale-before",
            "2026-03-01T00:00:00+00:00",
        ]
    )

    archived = repository.get_memory("mem-old")

    assert archived is not None
    assert archived.status == "archived"


def test_cli_maintain_runs_summarize_then_archive(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])
    repository = MemoryRepository(db_path)

    for index in range(3):
        main(
            [
                "remember",
                "--db",
                str(db_path),
                "--text",
                f"Cluster fact {index}",
                "--type",
                "fact",
                "--topic",
                "alpha",
                "--durability",
                "0.9",
                "--cost",
                "0.9",
                "--kind",
                "handoff_note",
                "--confidence",
                "0.8",
            ]
        )

    repository.upsert_memory(
        MemoryRecord(
            id="mem-old",
            type="fact",
            payload={"text": "Old superseded memory"},
            importance=0.5,
            confidence=0.8,
            freshness=0.5,
            status="superseded",
            source="test",
            topic_key="alpha",
            supersedes="summary-legacy",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )

    main(
        [
            "maintain",
            "--db",
            str(db_path),
            "--min-cluster-size",
            "3",
            "--stale-before",
            "2026-03-01T00:00:00+00:00",
        ]
    )

    committed = repository.list_memories(limit=5, status="committed")
    archived = repository.get_memory("mem-old")

    assert len(committed) == 1
    assert committed[0].type == "summary"
    assert archived is not None
    assert archived.status == "archived"



@pytest.mark.parametrize("command", ["summarize", "maintain"])
def test_cli_rejects_non_positive_min_cluster_size(
    tmp_path: Path, command: str, capsys
):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    arguments = [command, "--db", str(db_path), "--min-cluster-size", "0"]
    if command == "maintain":
        arguments.extend(["--stale-before", "2026-03-01T00:00:00+00:00"])

    with pytest.raises(SystemExit):
        main(arguments)

    assert "value must be a positive integer" in capsys.readouterr().err


def test_cli_rejects_out_of_range_scores(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    with pytest.raises(SystemExit):
        main(
            [
                "remember",
                "--db",
                str(db_path),
                "--text",
                "Bad scores should fail.",
                "--type",
                "fact",
                "--topic",
                "workflow",
                "--durability",
                "1.5",
                "--cost",
                "0.9",
                "--kind",
                "handoff_note",
                "--confidence",
                "0.8",
            ]
        )


@pytest.mark.parametrize("invalid_flag", ["--durability", "--cost", "--confidence"])
def test_cli_rejects_out_of_range_scores_for_each_field(
    tmp_path: Path, invalid_flag: str
):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    arguments = [
        "remember",
        "--db",
        str(db_path),
        "--text",
        "Out-of-range scores should fail.",
        "--type",
        "fact",
        "--topic",
        "workflow",
        "--durability",
        "0.9",
        "--cost",
        "0.9",
        "--kind",
        "handoff_note",
        "--confidence",
        "0.8",
    ]
    invalid_index = arguments.index(invalid_flag) + 1
    arguments[invalid_index] = "1.5"

    with pytest.raises(SystemExit):
        main(arguments)


def test_cli_rejects_nan_scores(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    with pytest.raises(SystemExit):
        main(
            [
                "remember",
                "--db",
                str(db_path),
                "--text",
                "NaN scores should fail.",
                "--type",
                "fact",
                "--topic",
                "workflow",
                "--durability",
                "nan",
                "--cost",
                "0.9",
                "--kind",
                "handoff_note",
                "--confidence",
                "0.8",
            ]
        )


def test_cli_rejects_invalid_kind_at_parser_boundary(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    with pytest.raises(SystemExit):
        main(
            [
                "remember",
                "--db",
                str(db_path),
                "--text",
                "Invalid kind should fail before the writer runs.",
                "--type",
                "fact",
                "--topic",
                "workflow",
                "--durability",
                "0.9",
                "--cost",
                "0.9",
                "--kind",
                "summary",
                "--confidence",
                "0.8",
            ]
        )

    assert "invalid choice" in capsys.readouterr().err


def test_cli_remember_persists_kind_confidence_and_project_name(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    main(
        [
            "remember",
            "--db",
            str(db_path),
            "--text",
            "Project-scoped memory should persist.",
            "--type",
            "fact",
            "--topic",
            "project-memory",
            "--durability",
            "0.9",
            "--cost",
            "0.9",
            "--kind",
            "project_memory",
            "--confidence",
            "0.61",
            "--project-name",
            "atlas",
        ]
    )

    memory = MemoryRepository(db_path).list_memories(limit=1)[0]

    assert memory is not None
    assert memory.memory_kind == "project_memory"
    assert memory.project_name == "atlas"
    assert memory.confidence == 0.61
    assert memory.payload == {"text": "Project-scoped memory should persist."}


def test_cli_rejects_missing_kind(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    with pytest.raises(SystemExit):
        main(
            [
                "remember",
                "--db",
                str(db_path),
                "--text",
                "Kind is required.",
                "--type",
                "fact",
                "--topic",
                "workflow",
                "--durability",
                "0.9",
                "--cost",
                "0.9",
                "--confidence",
                "0.8",
            ]
        )

    assert "the following arguments are required: --kind" in capsys.readouterr().err


def test_cli_rejects_missing_project_name_for_project_memory(tmp_path: Path, capsys):
    db_path = tmp_path / "memory" / "memory.db"
    main(["init", "--db", str(db_path)])

    with pytest.raises(SystemExit):
        main(
            [
                "remember",
                "--db",
                str(db_path),
                "--text",
                "Project memories require a project name.",
                "--type",
                "fact",
                "--topic",
                "project-memory",
                "--durability",
                "0.9",
                "--cost",
                "0.9",
                "--kind",
                "project_memory",
                "--confidence",
                "0.8",
            ]
        )

    assert "--project-name is required when --kind is project_memory" in capsys.readouterr().err


def test_module_invocation_executes_cli_commands(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"
    handoff_path = tmp_path / "memory" / "current-brief.md"

    base_args = [sys.executable, "-m", "memory_system.cli"]
    env = {"PYTHONPATH": "src"}

    subprocess.run(
        [*base_args, "init", "--db", str(db_path)],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    subprocess.run(
        [
            *base_args,
            "remember",
            "--db",
            str(db_path),
            "--text",
            "Module invocation should persist memory.",
            "--type",
            "fact",
            "--topic",
            "workflow",
            "--durability",
            "0.9",
            "--cost",
            "0.9",
            "--kind",
            "handoff_note",
            "--confidence",
            "0.8",
            "--unfinished",
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    subprocess.run(
        [
            *base_args,
            "summarize",
            "--db",
            str(db_path),
            "--min-cluster-size",
            "1",
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    subprocess.run(
        [
            *base_args,
            "maintain",
            "--db",
            str(db_path),
            "--min-cluster-size",
            "1",
            "--stale-before",
            "2026-03-01T00:00:00+00:00",
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    subprocess.run(
        [*base_args, "handoff", "--db", str(db_path), "--output", str(handoff_path)],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    assert db_path.exists()
    assert handoff_path.exists()
    assert "Module invocation should persist memory." in handoff_path.read_text()


def test_module_invocation_executes_visibility_commands(tmp_path: Path):
    db_path = tmp_path / "memory" / "memory.db"

    base_args = [sys.executable, "-m", "memory_system.cli"]
    env = {"PYTHONPATH": "src"}

    subprocess.run(
        [*base_args, "init", "--db", str(db_path)],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    subprocess.run(
        [
            *base_args,
            "remember",
            "--db",
            str(db_path),
            "--text",
            "Visibility module invocation should persist memory.",
            "--type",
            "fact",
            "--topic",
            "visibility",
            "--durability",
            "0.9",
            "--cost",
            "0.9",
            "--kind",
            "handoff_note",
            "--confidence",
            "0.8",
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    listed = subprocess.run(
        [
            *base_args,
            "list",
            "--db",
            str(db_path),
            "--status",
            "committed",
            "--limit",
            "5",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    payload = json.loads(listed.stdout)
    assert payload

    inspected = subprocess.run(
        [
            *base_args,
            "inspect",
            "--db",
            str(db_path),
            "--id",
            payload[0]["id"],
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    inspect_payload = json.loads(inspected.stdout)
    assert inspect_payload["id"] == payload[0]["id"]
