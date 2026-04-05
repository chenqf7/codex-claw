from pathlib import Path

import pytest

from memory_system.cli import main


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
            ]
        )


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
            ]
        )
