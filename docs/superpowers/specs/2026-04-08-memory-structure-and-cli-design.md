# Memory Structure And CLI Design

**Goal:** Improve the stored memory structure so durable memories record explicit confidence, carry a higher-level business classification, and optionally capture a project name for project-scoped memory. Update the CLI so these fields are first-class inputs rather than implicit defaults.

## Problem

The current memory system has two gaps:

1. durable memories always get a hard-coded `confidence=0.8`, which makes confidence less meaningful than the rest of the scoring model
2. the stored shape does not cleanly distinguish between user preference memory, project-scoped memory, handoff notes, and learned practices

That makes the stored data less expressive and less useful for future ranking, filtering, and handoff presentation.

## Recommended Approach

Keep the existing low-level `type` field and add a new higher-level `memory_kind` field.

The existing `type` field should continue to represent the fine-grained memory shape already used by the codebase, such as `fact`, `task`, or `summary`.

The new `memory_kind` field should represent the user-facing business classification:

1. `user_preference`
2. `project_memory`
3. `handoff_note`
4. `learned_practice`

Also add `project_name` as an optional top-level durable-memory field so project-scoped memories can be grouped or filtered without digging into `payload`.

This keeps the current architecture compatible while making the memory model more expressive.

## Data Model

### Durable Memory

The `memories` table should store:

1. existing fields including `type`, `importance`, `confidence`, `freshness`, `status`, and `topic_key`
2. new `memory_kind TEXT NOT NULL`
3. new `project_name TEXT`

`confidence` remains the same database column, but it should no longer be hard-coded by the writer. It becomes an explicit input to observation validation and CLI writes.

### Pending Memory

No new required columns are needed in `pending_items` for this change.

Pending items should continue to use the existing `payload` plus `topic_key` structure.

## Validation Rules

The write pipeline should enforce:

1. `memory_kind` must be one of:
   - `user_preference`
   - `project_memory`
   - `handoff_note`
   - `learned_practice`
2. `confidence` must be a finite number between `0` and `1`
3. when `memory_kind == "project_memory"`, `project_name` is required and must be a non-empty string
4. when `memory_kind != "project_memory"`, `project_name` may be omitted or `None`

These rules apply to durable-memory writes. Existing unfinished-task behavior stays unchanged.

## CLI Behavior

The `remember` command should accept:

1. `--kind` for `memory_kind`
2. `--confidence` for explicit confidence
3. `--project-name` for project-scoped memories

Example:

```bash
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli remember \
  --db memory/memory.db \
  --text "The project prefers repository-local skills plus symlink installation." \
  --type fact \
  --kind project_memory \
  --project-name codex-claw \
  --topic skills \
  --durability 0.9 \
  --confidence 0.85 \
  --cost 0.9
```

CLI validation should mirror the writer validation:

1. `--kind` is required
2. `--confidence` is required
3. `--project-name` is required only for `project_memory`

## Migration Strategy

Existing databases should be upgraded in place through the current bootstrap migration flow.

Recommended migration defaults:

1. add `memory_kind` with a safe default for existing rows
2. use `handoff_note` as the migration default for legacy durable memories
3. add `project_name` as nullable with default `NULL`

The reason for defaulting old rows to `handoff_note` is that the current store mostly contains agent-generated backlog, handoff, and coordination memory rather than carefully tagged user preference or learned-practice data.

## Code Boundaries

### Schema

Add missing columns and backfill legacy rows safely.

### Model

Extend `MemoryRecord` with:

1. `memory_kind: str`
2. `project_name: str | None`

### Write Pipeline

Extend observation validation and writer behavior so:

1. `confidence` comes from input
2. `memory_kind` is validated
3. `project_name` is validated conditionally

### Repository

Read and write the new durable-memory fields through the repository layer.

### CLI

Expose the new write inputs and reject invalid combinations before writing.

## Testing

The implementation should add or update tests for:

1. schema bootstrap and migration adding `memory_kind` and `project_name`
2. repository round-trip of the new fields
3. writer validation for `memory_kind`, `confidence`, and conditional `project_name`
4. CLI acceptance of valid inputs
5. CLI rejection of missing `--kind`, missing `--confidence`, and missing `--project-name` for `project_memory`

## Non-Goals

This change does not redesign retrieval ranking.

This change does not require new handoff rendering sections yet.

This change does not redefine the meaning of existing `type` values such as `fact`, `task`, or `summary`.
