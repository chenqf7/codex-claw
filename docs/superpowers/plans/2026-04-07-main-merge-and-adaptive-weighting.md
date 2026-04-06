# Main Merge And Adaptive Weighting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate `memory-system-v2` into `main`, bring docs and the operator skill up to date, and add bounded adaptive weighting on top of retrieval telemetry.

**Architecture:** First merge the already-implemented V2 lifecycle and summary/archive branch into the current `main` workspace while preserving local uncommitted changes. Then align the repo docs and external operator skill with the merged behavior. Finally, extend retrieval ranking with a small explainable weighting layer driven by existing telemetry fields, with tests defining the exact ordering behavior.

**Tech Stack:** Python 3.11, sqlite3, pytest, git worktrees, Markdown docs, Codex skill markdown

---

## File Structure

Planned files and responsibilities:

- Modify: `src/memory_system/retrieval.py`
  Add bounded adaptive weighting on top of semantic matching.
- Modify: `tests/test_retrieval.py`
  Lock in ranking behavior and telemetry-driven tie-breaking.
- Modify: `docs/superpowers/plans/2026-04-05-memory-system-v2.md`
  Keep prior implementation plan available on `main`.
- Modify: `docs/superpowers/plans/2026-04-05-memory-system-summary-archive.md`
  Keep prior summary/archive plan available on `main`.
- Modify: `docs/superpowers/specs/2026-04-05-memory-system-v2-design.md`
  Preserve the V2 design doc on `main`.
- Modify: `docs/superpowers/specs/2026-04-05-memory-system-summary-archive-design.md`
  Preserve the summary/archive design doc on `main`.
- Modify: `docs/superpowers/specs/2026-04-06-memory-system-backlog.md`
  Keep the handoff backlog document on `main` and update if needed after merge.
- Modify: `/Users/chenchen/.codex/skills/memory-system-operator/SKILL.md`
  Align the operator workflow with the merged V2 lifecycle and summary/archive behavior.
- Merge into current workspace: `memory-system-v2`
  Bring committed V2 code from the worktree branch into `main` without pushing.

### Task 1: Merge `memory-system-v2` Into `main` Safely

**Files:**
- Merge: `memory-system-v2`
- Verify: `src/memory_system/schema.py`
- Verify: `src/memory_system/repository.py`
- Verify: `src/memory_system/retrieval.py`
- Verify: `src/memory_system/handoff.py`
- Verify: `src/memory_system/maintenance.py`
- Verify: `tests/test_schema.py`
- Verify: `tests/test_repository.py`
- Verify: `tests/test_retrieval.py`
- Verify: `tests/test_handoff.py`
- Verify: `tests/test_maintenance.py`

- [ ] **Step 1: Confirm the current workspace state before merging**

```bash
git status --short
git branch --all --verbose --no-abbrev
git worktree list
```

- [ ] **Step 2: Merge the committed V2 branch into `main` without committing yet**

```bash
git merge --no-commit --no-ff memory-system-v2
```

Expected: merge applies the V2 code into the current workspace and pauses before commit so local changes can be reviewed.

- [ ] **Step 3: Inspect and resolve any overlap with local uncommitted changes**

```bash
git status --short
git diff -- src/memory_system/cli.py tests/test_cli.py .gitignore
```

Expected: the existing local edits remain intact or are reconciled intentionally.

- [ ] **Step 4: Verify the merged code composes cleanly**

```bash
pytest -q
```

Expected: all tests pass on the merged codebase, including the V2 suites.

### Task 2: Preserve And Align Docs And Operator Skill

**Files:**
- Modify: `docs/superpowers/plans/2026-04-05-memory-system-v2.md`
- Modify: `docs/superpowers/plans/2026-04-05-memory-system-summary-archive.md`
- Modify: `docs/superpowers/specs/2026-04-05-memory-system-v2-design.md`
- Modify: `docs/superpowers/specs/2026-04-05-memory-system-summary-archive-design.md`
- Modify: `docs/superpowers/specs/2026-04-06-memory-system-backlog.md`
- Modify: `/Users/chenchen/.codex/skills/memory-system-operator/SKILL.md`

- [ ] **Step 1: Compare the merged repository state with the docs backlog and the current operator skill**

```bash
sed -n '1,260p' docs/superpowers/specs/2026-04-06-memory-system-backlog.md
sed -n '1,260p' /Users/chenchen/.codex/skills/memory-system-operator/SKILL.md
```

- [ ] **Step 2: Update the backlog wording so it reflects that V2 is now on `main` and the next focus is adaptive weighting**

```markdown
## Current State

The local memory system V2 lifecycle and summary/archive behavior now live on `main`.

## Must Do

- Implement adaptive weighting on top of retrieval and usage telemetry.
```

- [ ] **Step 3: Update the operator skill so startup, retrieval, maintenance, and handoff guidance match the merged behavior**

```markdown
## Session start
- verify DB exists
- recover unclean sessions conservatively
- read `memory/current-brief.md`
- retrieve selectively for the current task

## During work
- use `remember` for durable facts and unfinished tasks
- use retrieval telemetry and mark memories used when they truly helped
- use maintenance flows for summarize/archive when needed
```

- [ ] **Step 4: Rebuild the handoff brief from the merged code**

```bash
PYTHONPATH=src /usr/local/opt/python@3.11/bin/python3.11 -m memory_system.cli handoff --db memory/memory.db --output memory/current-brief.md
```

Expected: `memory/current-brief.md` reflects the merged code and current backlog.

### Task 3: Add Adaptive Weighting With TDD

**Files:**
- Modify: `tests/test_retrieval.py`
- Modify: `src/memory_system/retrieval.py`

- [ ] **Step 1: Write a failing retrieval test for telemetry-driven ranking**

```python
def test_retrieve_prefers_more_used_memory_when_text_scores_tie(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    bootstrap_database(db_path)
    repo = MemoryRepository(db_path)
    now = "2026-04-07T00:00:00+00:00"

    repo.upsert_memory(
        MemoryRecord(
            id="mem-low-use",
            type="fact",
            payload={"text": "Adaptive weighting for retrieval ranking"},
            importance=0.8,
            confidence=0.8,
            freshness=1.0,
            status="committed",
            source="test",
            topic_key="ranking",
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
    )
    repo.upsert_memory(
        MemoryRecord(
            id="mem-high-use",
            type="fact",
            payload={"text": "Adaptive weighting for retrieval ranking"},
            importance=0.8,
            confidence=0.8,
            freshness=1.0,
            status="committed",
            source="test",
            topic_key="ranking",
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
    )
    repo.record_retrieval_event(
        state="fresh_task",
        query_text="adaptive weighting retrieval ranking",
        memory_ids=["mem-high-use"],
        pending_ids=[],
        created_at=now,
    )
    repo.mark_memory_used("mem-high-use", used_at=now)

    result = MemoryRetriever(db_path).retrieve("adaptive weighting retrieval ranking")

    assert result.memory_ids[0] == "mem-high-use"
```

- [ ] **Step 2: Run the targeted retrieval test and verify it fails for the right reason**

Run: `pytest tests/test_retrieval.py -k adaptive_weighting -v`
Expected: FAIL because retrieval ranking still ignores telemetry when semantic scores tie.

- [ ] **Step 3: Implement a bounded weighting layer in retrieval ranking**

```python
def _telemetry_bonus(record: Any) -> float:
    retrieval_count = getattr(record, "retrieval_count", 0)
    use_count = getattr(record, "use_count", 0)
    return min(0.75, retrieval_count * 0.05 + use_count * 0.15)

score = lexical_score + telemetry_bonus
```

Constraint: lexical matching must remain primary; telemetry may break ties or nudge close results but not dominate unrelated matches.

- [ ] **Step 4: Add one more failing test to prove irrelevant memories cannot leapfrog a direct match**

```python
def test_retrieve_keeps_direct_match_ahead_of_high_telemetry_irrelevant_memory(tmp_path: Path):
    ...
    assert result.memory_ids[0] == "mem-direct-match"
```

- [ ] **Step 5: Run the retrieval suite to verify the adaptive weighting behavior**

Run: `pytest tests/test_retrieval.py -v`
Expected: PASS

### Task 4: Run Full Verification And Leave `main` Ready For Local Commit

**Files:**
- Verify: repository working tree

- [ ] **Step 1: Run the full test suite on the final merged state**

Run: `pytest -q`
Expected: PASS with the full merged and adaptive-weighted codebase.

- [ ] **Step 2: Review the final working tree and staged merge state**

```bash
git status --short
git diff --stat
```

- [ ] **Step 3: Summarize remaining local-only state clearly before any commit or push decision**

```text
Main now contains the merged V2 lifecycle, updated docs and skill guidance, and adaptive weighting.
No push is performed.
```
