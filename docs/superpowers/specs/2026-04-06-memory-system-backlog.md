# Memory System Backlog

## Current State

The local memory system V2 lifecycle and summary/archive behavior are now merged into `main`.

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

- Keep the supporting docs and operator skill aligned with the merged code.
- Keep the current verification baseline recorded.
  - Latest successful summary/archive verification: `34 passed`
  - Latest full worktree test run during implementation: `48 passed`
  - Latest local merged verification on `main`: `49 passed`

## Should Do

- Implement adaptive weighting on top of the new telemetry fields.
  - Use `retrieval_count`, `last_retrieved_at`, `use_count`, and `last_used_at`.
  - Keep it bounded and explainable.
- Add explicit maintenance entrypoints.
  - Consider CLI commands for `summarize`, `archive`, or a combined `maintain`.
- Improve lifecycle visibility.
  - Make it easier to inspect why a memory is `committed`, `summary`, `superseded`, or `archived`.
- Add stronger conflict handling before summary generation.
  - Detect contradictory or suspicious source clusters and avoid summarizing them automatically.

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

## Suggested Next Step

If continuing implementation immediately, the next most valuable phase is:

1. finish doc and skill alignment on `main`
2. implement adaptive weighting

This ordering keeps the merged lifecycle work coherent before introducing dynamic ranking behavior.
