# Memory Lifecycle Visibility Design

## Goal

Make the local memory system easier to inspect after the V2 lifecycle and summary/archive work by exposing durable-memory lifecycle state through the CLI, with JSON-first output suitable for tooling and debugging, while keeping the handoff brief lightweight.

## Problem

The current system can store and evolve durable memory through these states:

- `committed`
- `summary`
- `superseded`
- `archived`

The underlying data needed to explain those states already exists:

- `status`
- `type`
- `supersedes`
- summary payload fields such as `source_ids` and `source_type`
- retrieval and usage telemetry

But there is no direct CLI entrypoint for answering two basic questions:

1. which durable memories are in each lifecycle state right now
2. why a specific memory ended up in its current state

The handoff brief also stays intentionally compact, so it is not the right place to dump full lifecycle diagnostics.

## Scope

This phase adds lifecycle visibility for durable memory only.

In scope:

- JSON-first CLI commands for listing and inspecting durable memories
- lifecycle explanation derived from existing memory relationships
- small handoff hints for summary visibility

Out of scope:

- pending item inspection commands
- staging inspection commands
- schema changes
- new persisted lifecycle metadata
- conflict detection before summary generation
- richer text-first CLI rendering

## Design Principles

### 1. JSON-first over prose-first

The primary output should be structured and predictable so shell users, scripts, and later tooling can consume it directly.

### 2. Reuse current state instead of inventing new state

Lifecycle explanations should be derived from existing record fields and linked summary records. This keeps the first visibility layer cheap and low-risk.

### 3. Keep handoff compact

The handoff brief should expose only high-signal lifecycle cues. Detailed diagnosis belongs in CLI inspection.

## CLI Surface

Add two new durable-memory commands to `memory_system.cli`.

### `list`

Purpose:
- list durable memories with lightweight lifecycle visibility

Arguments:

- `--db` required
- `--status` optional
- `--type` optional
- `--topic` optional
- `--limit` optional, defaulting to the same small-debug scale used elsewhere

Output:
- JSON array

Each item should include:

- `id`
- `type`
- `status`
- `topic_key`
- `memory_kind`
- `project_name`
- `payload`
- `source`
- `supersedes`
- `created_at`
- `updated_at`
- `retrieval_count`
- `last_retrieved_at`
- `use_count`
- `last_used_at`
- `lifecycle_reason`

This command is for discovery, so it gets the short lifecycle explanation only.

### `inspect`

Purpose:
- explain one durable memory in full

Arguments:

- `--db` required
- `--id` required

Output:
- JSON object

If the record is missing, the command should fail clearly with a parser-style CLI error or a `SystemExit` path consistent with the rest of the CLI.

## Lifecycle Explanation Model

`inspect` should expose a nested `lifecycle` object while `list` exposes only `lifecycle_reason`.

### Base object shape

```json
{
  "id": "mem-123",
  "type": "fact",
  "status": "superseded",
  "topic_key": "alpha",
  "memory_kind": "handoff_note",
  "project_name": null,
  "payload": {
    "text": "Cluster fact 0"
  },
  "source": "cli",
  "supersedes": "summary-abc",
  "created_at": "2026-04-14T00:00:00+00:00",
  "updated_at": "2026-04-14T00:00:00+00:00",
  "retrieval_count": 0,
  "last_retrieved_at": null,
  "use_count": 0,
  "last_used_at": null,
  "lifecycle": {
    "reason": "superseded_by_summary",
    "summary_id": "summary-abc",
    "summary_topic_key": "alpha",
    "source_ids": null
  }
}
```

### Initial explanation rules

- `status == "committed"` and `type != "summary"`
  - `reason = "active_memory"`
- `status == "committed"` and `type == "summary"`
  - `reason = "summary_memory"`
  - expose `source_ids` from summary payload
- `status == "superseded"` and `supersedes` points to a summary record
  - `reason = "superseded_by_summary"`
  - expose `summary_id`
  - expose `summary_topic_key`
- `status == "superseded"` without a resolvable summary target
  - `reason = "superseded"`
- `status == "archived"` and `supersedes` is set
  - `reason = "archived_from_superseded"`
  - expose `summary_id` when resolvable
- `status == "archived"` without a resolvable upstream summary
  - `reason = "archived"`

The explanation layer should degrade safely when linked records are missing. The command should still return the current memory plus the best-effort reason.

## Internal Structure

### Repository responsibilities

Add repository helpers for:

- filtered durable-memory listing
- converting `MemoryRecord` into JSON-safe dictionaries
- resolving the linked summary record when a durable memory has `supersedes`

The repository should remain a data-access layer, not a formatting layer. Raw record retrieval stays there; lifecycle explanation assembly can live in a small CLI-facing helper or a new narrow module if that keeps responsibilities clearer.

### CLI responsibilities

The CLI should:

- parse filters and ids
- call repository helpers
- build derived lifecycle explanation objects
- emit canonical JSON with stable key names

The CLI should not mutate any memory state during visibility operations.

## Handoff Changes

Keep the current brief structure.

Only add lightweight lifecycle cues:

- in `Durable Context`, prefix summary records as `[summary]`
- in `Recent Changes`, emit `[memory:summary]` for summary records instead of plain `[memory]`

Do not:

- include archived records in durable context
- expand summary source ids into the brief
- emit full lifecycle JSON in the markdown brief

This preserves the handoff brief as an orientation artifact rather than turning it into a diagnostic report.

## Testing

Add tests for:

- `list` filtering by `status`, `type`, and `topic`
- `list` JSON rows including `lifecycle_reason`
- `inspect` on committed plain memory
- `inspect` on summary memory
- `inspect` on superseded memory linked to a summary
- `inspect` on archived memory linked to a summary
- missing-record failure path for `inspect`
- handoff summary labeling without expanding archived detail

The tests should prefer real repository data over mocks so lifecycle derivation is verified against actual stored records.

## Risks

### 1. Overloading `supersedes`

The current explanation logic assumes `supersedes` is enough to infer upstream summary relationships for superseded or archived detail records. If future lifecycle work broadens that field's meaning, the explanation layer may need refinement.

### 2. JSON shape drift

Because this CLI is intended to be scriptable, field names and explanation strings should be treated as a real interface once shipped. The first version should therefore stay intentionally small.

### 3. Handoff verbosity creep

It is easy to turn lifecycle visibility into too much markdown noise. This phase intentionally keeps detailed state out of the brief.

## Acceptance Criteria

This design is complete when:

1. durable memories can be listed from CLI with lightweight lifecycle reasons
2. a single durable memory can be inspected from CLI with a structured lifecycle explanation
3. the explanation is derived from current stored relationships without schema changes
4. the handoff brief shows summary-state hints without becoming a debug dump
