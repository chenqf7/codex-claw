# Memory System V2 Design

## Goal

Upgrade the local memory system from a minimal V1 continuity layer into a more trustworthy, easier-to-use V2 workflow that new agents can adopt with very little setup cost.

This phase focuses on four concrete improvements:

1. add a higher-level skill-driven entrypoint for new agents
2. upgrade the generated handoff so it is easier to read and trust
3. add explicit lifecycle management for pending work
4. record retrieval counts and lightweight usage feedback so recall can improve over time

The goal of this phase is not to make the system fully automatic. It should become safely semi-automatic: able to track useful signals and maintain continuity without aggressively rewriting or deleting memory on its own.

## Non-Goals

This phase does not implement:

- automatic hard deletion of durable memories
- embedding-based retrieval
- fully automatic policy tuning
- full summary compression and archive migration
- broad self-modifying ranking logic

Those can be layered on later after the system becomes easier to trust operationally.

## Product Outcomes

After this phase:

- a new agent should have one clear workflow for starting and ending a session
- pending work should no longer accumulate indefinitely without closure states
- the handoff should explain current work, not just dump top records
- retrieval should leave behind measurable evidence of what was recalled and what proved useful

## Design Principles

### 1. Trust before cleverness

The system should explain why something is being surfaced before it starts changing memory weights aggressively.

### 2. Semi-automatic, not opaque

The system may collect signals automatically, but destructive or meaning-changing actions should remain conservative.

### 3. Support the next agent first

The best measure of success is whether a fresh agent can orient quickly and continue work safely.

### 4. Lifecycle beats accumulation

Pending items and retrieval signals should move through clear states instead of becoming permanent clutter.

## Scope

This phase introduces changes in four areas:

- agent entry workflow
- handoff structure
- pending item lifecycle
- retrieval telemetry and feedback

## 1. Agent Entry Workflow

### Problem

Today, a new agent needs to understand several low-level commands and file paths before it can use the system confidently. That makes continuity fragile.

### Solution

Provide a higher-level skill workflow on top of the existing memory system. The skill should not replace SQLite as the source of truth. It should package the normal operating sequence into a single repeatable procedure.

### Required workflow

At session start:

1. ensure the database exists
2. recover unclean sessions if needed
3. read the generated handoff if present
4. retrieve scoped memory for the current task

During work:

1. write durable memory intentionally
2. write unfinished work into pending items
3. optionally confirm whether retrieved items were actually useful

At session end:

1. resolve or update affected pending items
2. regenerate the handoff

### Deliverable

Either extend the current `memory-system-operator` skill or add a thin higher-level skill that wraps it. The final user experience should feel like one entrypoint, not a collection of unrelated commands.

## 2. Handoff Upgrade

### Problem

The current handoff is a short list of durable memory and active pending items. It is useful, but it does not help a fresh agent quickly answer:

- what is happening now
- what still needs attention
- what is long-term context versus short-term context
- what information may be unreliable

### Solution

Replace the current flat output with a structured handoff that separates orientation concerns.

### Required sections

The new handoff should contain:

1. `Current Focus`
   A compact summary of the most relevant active work based on pending state and recent retrieval activity.
2. `Active Pending Items`
   The currently open work items, ordered by urgency and freshness.
3. `Durable Context`
   Stable facts, preferences, and decisions that remain useful across sessions.
4. `Recent Changes`
   Newly added or recently updated records that may matter even if they are not the highest-ranked durable memories.
5. `Caution Items`
   Suspect, conflicting, or otherwise low-trust records that should not silently drive behavior.

### Ranking guidance

The handoff should not always show the same top durable memories. It should combine:

- long-term importance
- current task relevance
- recent activity

This avoids a static top-five problem where the same records dominate forever.

## 3. Pending Lifecycle

### Problem

Pending items currently behave like append-only active tasks. Without closure states, the pending list will become noisy and less trustworthy over time.

### Solution

Introduce explicit pending lifecycle states and transitions.

### Required states

- `active`
- `resolved`
- `cancelled`
- `expired`
- `reopened`

### Required transitions

- new unfinished work enters as `active`
- completed work becomes `resolved`
- abandoned work becomes `cancelled`
- stale, unconfirmed work may become `expired`
- previously closed work may return to `reopened`

### Operational rules

- only `active` and `reopened` items should appear by default in normal retrieval and handoff views
- `resolved`, `cancelled`, and `expired` items should remain queryable for audit and history
- reopening an item should preserve lineage instead of creating hidden duplicates

## 4. Retrieval Telemetry And Feedback

### Problem

The system currently retrieves memory but learns nothing from retrieval events. This blocks any later attempt to improve ranking safely.

### Solution

Track retrieval activity and lightweight usefulness feedback separately from the memory truth itself.

### Required telemetry

For each retrieval event, record:

- query text
- classified state
- selected memory ids
- selected pending ids
- timestamp

For each memory and pending item, maintain derived usage fields:

- `retrieval_count`
- `last_retrieved_at`
- `use_count`
- `last_used_at`

### Feedback model

The system should distinguish:

- `retrieved`: the item was surfaced to the agent
- `used`: the item was confirmed relevant to the task

This distinction matters because repeated retrieval alone is a weak signal.

### Use of telemetry

In this phase, telemetry may be used for:

- improving handoff ranking
- delaying expiration for repeatedly used items
- identifying likely summary candidates in later phases

In this phase, telemetry should not silently rewrite the semantic meaning of memory records.

## Data Model Changes

### `pending_items`

Add fields needed for lifecycle and continuity:

- `closed_at` nullable timestamp
- `supersedes` nullable id
- `reopened_from` nullable id

### `memories`

Add lightweight retrieval metadata:

- `retrieval_count` integer default `0`
- `last_retrieved_at` nullable timestamp
- `use_count` integer default `0`
- `last_used_at` nullable timestamp

### `pending_items`

Add the same lightweight retrieval metadata:

- `retrieval_count` integer default `0`
- `last_retrieved_at` nullable timestamp
- `use_count` integer default `0`
- `last_used_at` nullable timestamp

### `retrieval_logs`

Expand the payload so each event can record both memory ids and pending ids, plus whether usage feedback was later attached.

## API And CLI Direction

This phase should expand the Python API first and only add minimal CLI surface area where it meaningfully improves operations.

Recommended additions:

- repository methods to transition pending items between states
- repository methods to increment retrieval and usage counters
- retrieval methods that optionally persist retrieval telemetry
- maintenance helpers that expire only low-signal stale pending items
- handoff rendering that consumes lifecycle and telemetry signals

CLI additions are optional for this phase, but if added they should focus on:

- marking pending items resolved or cancelled
- reopening pending items
- regenerating the handoff after state changes

## Safety Rules

- retrieval signals may influence ranking, but not overwrite truth
- expired pending items should not be hard-deleted in this phase
- suspect records should remain visible in caution-oriented views
- any automatic expiration must be conservative and explainable
- durable memory should not be deleted automatically in this phase

## Testing Requirements

This phase should add or update tests for:

- pending lifecycle transitions
- retrieval logging and per-item counters
- usage feedback updates
- handoff section generation and ordering behavior
- startup workflow behavior exposed through the skill-guided path

## Success Criteria

This phase is successful when:

1. a new agent can use one documented workflow to start and end a session
2. pending items no longer remain permanently active by default
3. retrieval leaves behind measurable usage signals
4. the handoff helps a fresh agent distinguish current work from stable context
5. all automatic behavior remains conservative and explainable

## Future Extensions

Once this phase is stable, the system will be ready for:

- summary record generation
- archive migration
- bounded weight adaptation
- smarter expiration policy
- richer retrieval ranking
