# Memory System Summary And Archive Design

## Goal

Add a semi-automatic summary and archive workflow to the local memory system so memory can stay compact, traceable, and useful over time without aggressive or opaque deletion.

This phase focuses on the memory lifecycle after durable memory has already been captured:

1. identify summary candidates conservatively
2. generate summary memory records for stable clusters
3. mark covered source records as `superseded`
4. archive older low-signal superseded records later under stricter rules

The design favors lifecycle clarity and recoverability over aggressive compression.

## Non-Goals

This phase does not implement:

- embeddings or semantic clustering
- fully automatic weight adaptation
- hard deletion of durable memories
- rewriting existing memory meaning
- summarizing unresolved or suspicious memory by default

## Product Outcomes

After this phase:

- memory growth is bounded by a visible summarize-and-archive lifecycle
- the same high-importance records do not dominate retrieval forever
- old detailed memory remains traceable without staying in the main recall path
- summary generation is explainable and conservative

## Design Principles

### 1. Semi-automatic, not silent

The system may identify and execute bounded maintenance actions, but it must do so through explicit, inspectable rules rather than opaque heuristics.

### 2. Preserve lineage

Original memory should remain traceable after summarization. Summary should compress access, not erase provenance.

### 3. Summary before archive

Records should first move from `committed` to `superseded`, then later to `archived` only if they remain low-signal.

### 4. Cluster by meaning already present in the system

The first version should use `topic_key + type` as the summary grouping key. This keeps behavior deterministic and aligned with the current schema.

## Scope

This phase introduces:

- summary candidate detection
- summary record generation
- supersede transitions
- archive candidate detection for old superseded memory
- maintenance helpers and tests for the new lifecycle

## Lifecycle Model

### Durable memory states in this phase

- `committed`
- `summary`
- `superseded`
- `archived`
- `suspect`

### Intended flow

1. stable detailed memory starts as `committed`
2. a conservative maintenance pass identifies a cluster candidate
3. the system creates one `summary` record for that cluster
4. covered `committed` records become `superseded`
5. much later, low-signal `superseded` records may become `archived`

The original records are never hard-deleted in this phase.

## Summary Candidate Rules

The system should only summarize a cluster when all of the following are true:

- all candidate records share the same `topic_key`
- all candidate records share the same `type`
- all candidate records are in `committed` state
- the cluster size meets a configured minimum threshold
- the cluster does not contain `suspect` material
- the cluster is not obviously active unfinished work

The first version should use `topic_key + type` as the grouping key. Time-window logic can come later if needed.

## Summary Record Design

The generated summary should be stored as a normal durable memory record with:

- `type = "summary"`
- `status = "committed"`
- `topic_key` equal to the source cluster topic
- `supersedes = None`

The payload should remain compact and AI-oriented. At minimum it should include:

- a short summary text
- the grouped source type
- the grouped source ids

This record becomes part of normal recall and handoff behavior.

## Supersede Rules

Once a summary record is created successfully:

- each covered source memory should move from `committed` to `superseded`
- the source memory should reference the summary through `supersedes`
- superseded records should remain queryable for lineage and audit

Superseded records should no longer dominate normal retrieval when an equivalent summary exists.

## Archive Rules

Archive should be stricter than summarization. A superseded record may move to `archived` only when all of the following are true:

- it is already `superseded`
- it has not been retrieved recently
- it has not been marked used recently
- it is not part of recent changes
- it does not appear to support active pending work

The first version should use simple deterministic thresholds such as:

- `last_retrieved_at` older than a configured cutoff, or never retrieved
- `last_used_at` older than a configured cutoff, or never used
- `updated_at` older than a configured cutoff

Archive remains reversible in principle because records are retained, not deleted.

## Retrieval Impact

Default recall behavior should shift to:

- prioritize `committed` and `summary`
- de-prioritize `superseded`
- exclude `archived` from normal high-confidence recall
- continue to surface `suspect` only in caution-oriented views

This phase does not require a sophisticated ranking rewrite. It only requires status-aware filtering and ordering adjustments where needed.

## Handoff Impact

The handoff should remain compact, but after this phase it may include summary records in `Durable Context` when they outrank the detailed source records they cover.

Superseded records should not crowd the normal durable section.

Archived records should remain out of the default handoff.

## Data Model Changes

This phase can reuse most existing schema fields if status transitions are already available. The only additional persisted relationship required is clear source lineage for summary generation.

If needed, add one of these minimal options:

- store grouped source ids inside summary payload
- or add a dedicated relationship table later

For this phase, storing grouped source ids inside summary payload is sufficient and lower risk.

## Maintenance Pipeline

Add a maintenance flow with two conservative operations:

### 1. Summarize eligible clusters

- scan committed memory by `topic_key + type`
- filter to eligible clusters above threshold
- create one summary record per eligible cluster
- mark source records as `superseded`

### 2. Archive stale superseded records

- scan `superseded` records
- filter to low-signal stale candidates
- mark eligible records as `archived`

These operations should be callable explicitly and safe to run multiple times.

## API Direction

Recommended additions:

- repository methods to list summarize-able clusters
- repository methods to create summary records
- repository methods to batch mark source records as `superseded`
- repository methods to list archive candidates
- repository methods to mark records as `archived`
- maintenance helpers that orchestrate summary creation and archive transitions

## Safety Rules

- do not summarize `suspect` memory
- do not summarize unresolved pending work into durable summary by default
- do not archive directly from `committed`
- do not hard-delete durable memory
- do not let summary creation partially succeed without marking source lineage consistently

## Testing Requirements

This phase should add or update tests for:

- summary candidate selection by `topic_key + type`
- summary record generation payload and status
- batch transition from `committed` to `superseded`
- archive candidate filtering from `superseded`
- exclusion of archived memory from default recall
- preservation of lineage after summarization

## Success Criteria

This phase is successful when:

1. stable detailed memory can be summarized into a durable summary record
2. summarized source records move to `superseded` instead of staying in the main recall path
3. stale superseded records can later move to `archived` under stricter rules
4. retrieval and handoff remain compact without losing traceability
5. no durable record is silently deleted

## Future Extensions

Once this phase is stable, the system will be ready for:

- time-window-aware summarization
- richer summary text generation
- adaptive thresholds based on retrieval/use patterns
- archive reheating if old records become relevant again
