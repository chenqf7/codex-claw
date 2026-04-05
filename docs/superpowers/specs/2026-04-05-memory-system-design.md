# Memory System Design

## Goal

Build an AI-first memory system that helps the agent preserve high-value context without overloading itself with unnecessary detail. The system should prioritize long-term memory first, while also carrying unfinished work across sessions so the agent can resume intelligently after interruptions.

The design follows the constraints in [Agent.md](/Users/chenchen/codexClaw/Agent.md): memory must remain compact, adaptive, and selectively retrievable. The system should optimize for AI usefulness rather than human readability.

## Product Intent

The memory system exists to solve three recurring failures:

1. Durable information gets forgotten across sessions.
2. Unfinished work gets dropped when a session ends unexpectedly or context shifts.
3. Too much recalled detail harms performance more than forgetting does.

The system should therefore behave less like a transcript archive and more like a compact, self-maintaining knowledge base with explicit handling for active work and interrupted execution.

## Core Principles

### 1. Long-term memory is the primary layer

The highest priority is to retain durable facts, user preferences, project conventions, prior decisions, and other high-value context that should survive across sessions.

### 2. Pending work is a separate first-class layer

Unfinished tasks, promises, blockers, and partial progress should not be mixed into durable memory. They require a dedicated representation so they can be resumed, resolved, or retired cleanly.

### 3. Retrieval is selective and state-driven

The system should not preload all memory at session start. It should classify the current situation first, then retrieve only the memory slices needed for the current task state.

### 3.5. Storage and handoff are different concerns

The canonical memory store should optimize for AI retrieval efficiency, while agent handoff should optimize for quick orientation. These should be separate layers. Structured storage remains the source of truth, and any human-readable or agent-readable summary should be generated from it rather than maintained independently.

### 4. Memory policy is adaptive but bounded

The system may adjust its storage and compression behavior to better match user habits, but only within controlled limits. Adaptation must improve relevance, not change the meaning of stored truth.

### 5. Interrupted execution must be recoverable

If the previous run exited unexpectedly, the system should detect ambiguous state and avoid trusting half-written memory blindly.

## Memory Model

The memory store is AI-oriented and structured. It is not required to be human-readable.

The main record types for V1 are:

- `fact`: durable project or user knowledge
- `preference`: user tendencies, style, or instruction patterns
- `decision`: prior choices with future impact
- `task`: active or deferred units of work
- `open_loop`: incomplete threads, blockers, promised follow-up, unanswered questions
- `summary`: compressed rollups of clusters of related lower-level records
- `episode`: session or work-unit level context used for provenance and recovery

Each memory record should include compact metadata:

- `id`
- `type`
- `payload`
- `importance`
- `confidence`
- `freshness`
- `status`
- `source`
- `created_at`
- `updated_at`
- `supersedes`
- `topic_key`

This metadata supports ranking, merging, expiration, integrity checks, and adaptive policy tuning.

## Judgment Rubric

The agent should not ask the user what memory matters on every task. Instead, it should use a built-in rubric for both writing and recall.

### Recall rubric

Candidate memories are scored by:

- `task_relevance`: how directly the memory helps with the current request or active workstream
- `durability`: whether the knowledge is likely to matter again later
- `actionability`: whether the memory changes what the agent should do next
- `cost_of_forgetting`: how much rework, repeated error, or dropped commitment forgetting would cause
- `recency`: whether the memory is still timely
- `trust`: whether the information is confirmed by user input, code, or repeated evidence
- `scope_fit`: whether the memory is broad and useful without reintroducing overload

### Write rubric

The agent should promote information into stable long-term memory only when durability and cost of forgetting are both meaningfully high. Pending memory should be written when something is unfinished, blocked, promised, deferred, or at risk of being lost before completion.

### Forgetting rubric

The system should aggressively remove or compress memory that is stale, low-confidence, duplicated, or too detailed to justify its retrieval cost.

## Retrieval Strategy

Retrieval begins with state classification rather than full-session hydration.

The classifier should distinguish among at least these situations:

- `continuation`: the user is resuming unfinished work
- `dependency_recall`: the new task depends on prior decisions or stored knowledge
- `fresh_task`: the task is largely independent and should start with minimal recall
- `recovery`: the previous execution may have ended unexpectedly, requiring integrity checks before normal recall

The retrieval pipeline for V1 is:

1. Classify current state
2. Determine which knowledge categories are needed
3. Retrieve a small set of top-ranked candidate records
4. Merge or summarize them into a compact working context
5. Include unresolved pending items only when they are relevant to the active task or recovery state

This prevents startup overload and ensures memory is pulled on demand.

## Handoff View

Although the canonical memory store is structured and AI-oriented, the next agent may still need a fast orientation surface when it does not share the previous live context. To support that, the system should generate a compact readable handoff artifact from the database.

This handoff artifact is not a second memory system. It is a derived view that exists only to summarize the most important current state.

Suggested file:

- `memory/current-brief.md`

Suggested contents:

- memory system health and last clean completion state
- currently active pending items
- top durable facts and decisions with current relevance
- suspect or recovery-sensitive items that need cautious handling
- current policy posture, such as whether compression or pending retention has adapted recently

Rules for the handoff artifact:

- it is generated, not manually maintained
- it does not replace database retrieval
- it should remain compact enough to read quickly
- it should favor orientation over completeness
- it may be omitted from prompt context unless the current task benefits from it

The intended use is to help a new agent understand the current memory system and recent continuity state without forcing a full memory retrieval pass.

## Adaptive Policy

The memory system may optimize itself according to user habits, but only in bounded ways.

Examples of permitted adaptation:

- increasing or lowering the threshold for closing pending items based on how often the user reopens work
- changing compression aggressiveness if the user prefers concise continuity over detailed recall
- increasing the weight of preferences if the user repeatedly reinforces them across sessions

Examples of forbidden adaptation:

- rewriting confirmed user preferences without evidence
- silently discarding durable high-cost knowledge
- changing semantic meaning just to reduce storage size

Adaptation should operate on scoring thresholds, merge policy, expiration policy, and ranking weights, not on truth itself.

## Integrity and Crash Recovery

Unexpected termination can leave memory in a disordered state. V1 should explicitly model write lifecycle and execution integrity.

### Required lifecycle states

- `staged`: observed but not yet promoted
- `committed`: validated and active
- `superseded`: replaced by a newer record
- `resolved`: completed pending item
- `archived`: retained for low-priority historical reference
- `suspect`: ambiguous due to interrupted write or inconsistent completion markers

### Recovery behavior

Each execution session should have a session record with start, heartbeat or progress markers, and final completion state. If a later run discovers a previously active session without a clean completion marker, related staged writes and open transitions should be marked `suspect`.

Suspect records should be treated conservatively:

- exclude them from high-confidence recall by default
- allow them to participate in recovery summaries
- revalidate them if supported by durable evidence or explicit user confirmation

This avoids promoting corrupted or half-finished state into trusted memory.

## V1 Architecture

### Storage engine

Use `SQLite` for V1.

Rationale:

- local and fast
- structured and queryable
- compact enough for a small AI-oriented memory store
- simple to maintain and evolve
- supports transactional writes, which helps integrity handling

Embeddings or vector search can be added later if recall quality needs improvement. V1 should first prove value with typed records and deterministic scoring.

### Initial schema

Suggested tables:

- `memories`
- `pending_items`
- `staging_memories`
- `episodes`
- `sessions`
- `integrity_events`
- `retrieval_logs`
- `policy_state`

### Derived artifacts

Suggested generated outputs:

- `memory/current-brief.md`

The generated handoff view should be created from committed and relevant database records after retrieval or maintenance passes. It should never be treated as authoritative if it diverges from the database.

### Main pipelines

Write pipeline:

1. Observe candidate memory
2. Normalize into structured form
3. Stage record
4. Score for promotion, merge, archive, or drop
5. Commit transaction with lifecycle markers

Retrieval pipeline:

1. Inspect current request and execution state
2. Classify continuity and dependency needs
3. Score candidate stable records and pending items
4. Select top relevant subset
5. Return compact summary payload for the agent

Maintenance pipeline:

1. Deduplicate similar records
2. Compress clusters into summary records
3. Resolve or expire pending items
4. Decay stale low-value memory
5. Re-rank policy parameters within bounded limits
6. Flag unresolved integrity anomalies

## Boundaries for V1

V1 should include:

- local database initialization
- typed memory insert and update operations
- separate handling for long-term memory and pending work
- selective retrieval for a task string or classified state
- lifecycle markers for safe write and recovery handling
- a cleanup and compression pass
- a generated markdown handoff summary for cross-agent orientation

V1 should not include:

- full transcript ingestion
- unbounded auto-save of everything the model sees
- heavy vector infrastructure before deterministic retrieval is validated
- complex human-facing interfaces
- manually curated markdown memory as a second source of truth

## Testing Strategy

The implementation should be testable in isolation from the full agent runtime.

Key test areas:

- promotion rules for stable memory versus pending memory
- ranking behavior for retrieval across task states
- deduplication and summary compression
- expiration and resolution behavior
- crash recovery handling for interrupted staged writes
- policy adaptation staying within allowed bounds

The most important failure mode to test is false trust after interruption: records created during an unclean exit must not silently become trusted memory.

## Recommended Implementation Path

1. Build the SQLite schema and transactional write API.
2. Implement typed memory and pending-item storage with lifecycle states.
3. Implement the state classifier and selective retrieval path.
4. Add recovery markers and suspect-state handling.
5. Add maintenance routines for dedupe, compression, and expiration.
6. Add bounded policy adaptation.
7. Integrate the library or CLI into the agent workflow.

## Open Questions Deferred Beyond V1

- whether embeddings materially improve retrieval quality enough to justify the added complexity
- how the agent runtime should expose memory summaries internally
- whether some memory classes should use different retention windows or separate stores

## Decision Summary

The system will be an AI-first, SQLite-backed memory layer with two primary functional domains:

- durable long-term memory for facts, preferences, and decisions
- active pending memory for unfinished work and recovery-sensitive execution context

It will retrieve selectively based on current task state, adapt its policy to user habits within bounded limits, and explicitly mark suspect state after interrupted execution so corrupted memory is not silently trusted.

The database will remain the source of truth, while a compact generated markdown handoff view will provide fast orientation for the next agent without becoming a parallel memory system.
