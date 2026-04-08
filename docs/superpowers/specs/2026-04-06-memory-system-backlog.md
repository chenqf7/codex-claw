# Memory System Backlog

## Current State

The local memory system V2 lifecycle and summary/archive behavior are now merged into `main`.

The durable memory model has also been upgraded on `main` to support explicit confidence and higher-level memory classification:

- `memory_kind` now distinguishes:
  - `user_preference`
  - `project_memory`
  - `handoff_note`
  - `learned_practice`
- `project_name` is stored as a first-class field for project-scoped memory
- `remember` now requires explicit `--kind` and `--confidence`
- `project_memory` writes now require `--project-name`

The recently integrated work includes two major phases:

- V2 lifecycle improvements:
  - schema migration support
  - pending lifecycle states
  - retrieval and usage telemetry
  - structured handoff generation
  - conservative expiration for low-signal pending items
- Summary and archive lifecycle:
  - summary candidate selection by `topic_key + type`
  - atomic summary creation plus source superseding
  - maintenance-driven cluster summarization
  - stale superseded memory archiving
  - retrieval and handoff preference for summary over archived detail

The integration source for those two phases was:

- worktree: `/Users/chenchen/codexClaw/.worktrees/memory-system-v2`
- branch: `memory-system-v2`
- commit: `a734ba6`

## Must Do

- Keep the current verification baseline recorded.
  - Latest successful summary/archive verification: `34 passed`
  - Latest full worktree test run during implementation: `48 passed`
  - Latest local merged verification on `main`: `52 passed`
  - Latest local merged verification after memory structure + CLI upgrade on `main`: `68 passed`
- Keep the roadmap and handoff memory aligned with the actual shipped state.
  - V2 lifecycle and summary/archive are on `main`.
  - Adaptive weighting is implemented on `main`.
  - Explicit `memory_kind`, `project_name`, and input-driven `confidence` are implemented on `main`.
  - The `memory-system-operator` skill now lives under `skills/memory-system-operator/`.

## Should Do

- Add explicit maintenance entrypoints.
  - Consider CLI commands for `summarize`, `archive`, or a combined `maintain`.
- Improve lifecycle visibility.
  - Make it easier to inspect why a memory is `committed`, `summary`, `superseded`, or `archived`.
- Add stronger conflict handling before summary generation.
  - Detect contradictory or suspicious source clusters and avoid summarizing them automatically.
- Decide whether handoff rendering should surface `memory_kind` or `project_name` explicitly.
  - The data is now stored, but the handoff view still presents a simpler summary.

## Can Do Later

- Add time-window-aware summary clustering.
  - Current grouping is only `topic_key + type`.
- Add archive reheating.
  - Allow archived memory to move back into an active recall state if it becomes relevant again.
- Improve summary quality.
  - Move from deterministic joined text toward better structured summary payloads.
- Add richer retrieval ranking.
  - Current ranking is still lightweight and deterministic.
- Add bounded policy adaptation.
  - Tune thresholds for summarization and archiving based on long-term usage patterns.
- Add memory-kind-aware retrieval and maintenance policies.
  - Example: weight `user_preference` and `project_memory` differently during ranking or summarization.

## Suggested Next Step

If continuing implementation immediately, the next most valuable phase is:

1. add explicit maintenance CLI entrypoints
2. improve lifecycle visibility
3. add conflict handling before summary generation

This ordering builds on the merged lifecycle and adaptive-weighting baseline without reopening the completed integration work.
