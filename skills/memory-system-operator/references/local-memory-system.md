# Local Memory System Reference

## Repo Paths

- Project root: current repository root
- Database: `memory/memory.db`
- Handoff brief: `memory/current-brief.md`

## Core Modules

- `src/memory_system/cli.py`
  Command-line entrypoints: `init`, `remember`, `handoff`, `list`, `inspect`, `summarize`, `archive`, `maintain`
- `src/memory_system/write_pipeline.py`
  Validates observations and writes durable memory plus pending items
- `src/memory_system/retrieval.py`
  Classifies task state and returns scoped memory/pending context
- `src/memory_system/maintenance.py`
  Handles interrupted-session recovery and suspect staging state
- `src/memory_system/handoff.py`
  Generates the markdown brief with safe replacement semantics
- `src/memory_system/repository.py`
  SQLite access layer
- `src/memory_system/schema.py`
  Database bootstrap

## Recommended Agent Lifecycle

### Session start

1. Ensure the DB exists. Initialize it if missing.
2. If the previous run may have crashed, run recovery.
3. If quick orientation helps, read `memory/current-brief.md`.

### During work

1. Use retrieval for the current task instead of reading everything.
2. Write durable facts, decisions, and unfinished work as they become clear.
3. Keep writes compact and high-signal.

### Session end

1. Regenerate the handoff brief.
2. Leave the DB as the source of truth.

## CLI Commands

Initialize with the module entrypoint:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli init --db memory/memory.db
```

Remember:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli remember \
  --db memory/memory.db \
  --text "Need to resume unfinished work." \
  --type task \
  --topic workflow \
  --kind handoff_note \
  --durability 0.9 \
  --cost 0.9 \
  --confidence 0.8 \
  --unfinished
```

Generate handoff:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli handoff --db memory/memory.db --output memory/current-brief.md
```

Summarize eligible committed clusters:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli summarize \
  --db memory/memory.db \
  --min-cluster-size 3
```

Archive stale superseded memories:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli archive \
  --db memory/memory.db \
  --stale-before 2026-04-01T00:00:00+00:00
```

Run summarize and archive together:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli maintain \
  --db memory/memory.db \
  --min-cluster-size 3 \
  --stale-before 2026-04-01T00:00:00+00:00
```

List durable memory with JSON lifecycle visibility:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli list \
  --db memory/memory.db \
  --status committed \
  --limit 10
```

Inspect one durable memory as JSON:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli inspect \
  --db memory/memory.db \
  --id summary-123
```

## Notes

- `remember` requires `--kind` and `--confidence`.
- `list` and `inspect` are JSON-first visibility commands for durable memory.
- `summarize` and `maintain` require `--min-cluster-size` to be a positive integer.
- `archive` and `maintain` require an ISO-8601 `--stale-before` cutoff.
- `project_memory` entries also require `--project-name`.
- Scores must be finite numbers between `0` and `1`.
- `unfinished` must be a real boolean in the Python API.
- Retrieval is intentionally lightweight and token-based; it is good for V1 continuity, not semantic search.
- The `memory-system` shell command is optional and only exists if the package has been installed into the active environment.
