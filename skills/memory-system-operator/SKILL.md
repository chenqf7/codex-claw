---
name: memory-system-operator
description: Operate the repository-local SQLite-backed AI memory system for storing durable facts, tracking unfinished work, recovering interrupted sessions, selectively retrieving context, and generating the agent handoff brief. Use when Codex needs to remember project or user context across sessions, resume unfinished work, repair suspect state after an interrupted run, or refresh `memory/current-brief.md`.
---

# Memory System Operator

## Overview

Use this skill from the repository root that contains the memory system. The current `main` branch includes the V2 lifecycle and the summary/archive flow, so the standard workflow is: initialize if needed, recover conservatively, retrieve selectively with telemetry persistence when useful, write durable or pending memory intentionally, and refresh the markdown handoff brief.

## Workflow

### Session start

Start each new agent session with the same sequence.

- Default database path: `memory/memory.db`
- Default handoff brief path: `memory/current-brief.md`

1. Verify the local memory store exists.

If the database is missing, initialize it with the module entrypoint:

```bash
cd <repo-root>
/usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli init --db memory/memory.db
```

If you have installed the package as a console script, you may use:

```bash
cd <repo-root>
memory-system init --db memory/memory.db
```

2. Recover interrupted runs conservatively when there is a credible chance the previous run died mid-write.

```python
from pathlib import Path

from memory_system.maintenance import MemoryMaintenance

maintenance = MemoryMaintenance(Path("memory/memory.db"))
maintenance.recover_unclean_sessions()
```

The current implementation is intentionally conservative:

- it prefers not to corrupt unrelated sessions
- it marks staged rows as `suspect` only for the current session, or for a sole active session when no current session is known

3. Read `memory/current-brief.md` if it exists for fast orientation, but treat SQLite as the source of truth.

4. Retrieve selectively for the current task instead of loading the whole store.

```python
from pathlib import Path

from memory_system.retrieval import MemoryRetriever

retriever = MemoryRetriever(Path("memory/memory.db"))
result = retriever.retrieve(
    "continue adaptive weighting work from last time",
    persist=True,
)
```

Use the retrieval result as working context, not as a full transcript. `persist=True` is appropriate when the current task is meaningfully using prior context and should update retrieval telemetry.

When working from a fresh clone, prefer `PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli ...` because the `memory-system` shell command may not be installed in the current environment.

### During work

Use `remember` when new durable or unfinished context should survive later sessions.

Write memory intentionally.

For durable facts, preferences, or decisions, prefer the module entrypoint:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli remember \
  --db memory/memory.db \
  --text "User prefers long-term memory first." \
  --type fact \
  --topic user-preferences \
  --durability 0.95 \
  --cost 0.90
```

For unfinished work that should also appear in pending memory:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli remember \
  --db memory/memory.db \
  --text "Need to finish adaptive weighting rollout." \
  --type task \
  --topic retrieval-ranking \
  --durability 0.40 \
  --cost 0.95 \
  --unfinished
```

Keep scores between `0` and `1`. Invalid scores and invalid `unfinished` values are rejected.

When a retrieved memory proves useful, explicitly mark it as used:

```python
retriever.mark_memory_used(result.memory_ids[0])
```

For maintenance-oriented cleanup or compaction work, use `MemoryMaintenance` directly:

```python
from pathlib import Path

from memory_system.maintenance import MemoryMaintenance

maintenance = MemoryMaintenance(Path("memory/memory.db"))
summary_ids = maintenance.summarize_eligible_clusters(min_cluster_size=3)
archived_ids = maintenance.archive_stale_superseded_memories(
    stale_before="2026-04-01T00:00:00+00:00"
)
expired_ids = maintenance.expire_stale_pending_items(
    stale_before="2026-04-01T00:00:00+00:00",
    max_priority=0.3,
)
```

Resolve, cancel, reopen, or expire pending items deliberately so the pending layer stays trustworthy.

### Session end

Whenever memory changes materially, refresh the brief for the next agent:

```bash
cd <repo-root>
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli handoff --db memory/memory.db --output memory/current-brief.md
```

This file is a derived view, not the source of truth.

## Practical Rules

- Use durable memory for facts, preferences, and decisions that would be costly to forget.
- Use pending memory for unfinished work, blockers, or promised follow-up.
- Persist retrieval telemetry when the current task is meaningfully using prior context.
- Mark retrieved durable memory as used only when it actually helped with the current task.
- Use maintenance flows deliberately for summary creation, stale superseded archive, and conservative pending expiration.
- Resolve, cancel, reopen, or expire pending items deliberately so the pending layer stays trustworthy.
- Do not treat the handoff markdown as authoritative over SQLite.
- Do not bypass retrieval by loading the entire DB into context.
- After meaningful fixes or interrupted work, run recovery before trusting staged state.

## References

Read [references/local-memory-system.md](references/local-memory-system.md) when you need:

- module-to-responsibility mapping
- the recommended agent lifecycle
- the most important file paths and commands
