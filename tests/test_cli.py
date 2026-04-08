from pathlib import Path
import subprocess
import sys

import pytest

from memory_system.cli import main
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
        [*base_args, "handoff", "--db", str(db_path), "--output", str(handoff_path)],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    assert db_path.exists()
    assert handoff_path.exists()
    assert "Module invocation should persist memory." in handoff_path.read_text()
