# Skill Repo Relocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `memory-system-operator` into this repository as the canonical skill source, fix repository references to use shareable paths, and replace the local Codex skill directory with a symlink to the repo copy.

**Architecture:** First create a repository-owned skill directory under `skills/memory-system-operator/` and populate it with the existing `SKILL.md`, `references/`, and `agents/` files. Then update repo docs and plan files to refer to the repository copy rather than a machine-local skill path. Finally, switch `~/.codex/skills/memory-system-operator` to a symlink that points at the repository directory and verify the resulting layout.

**Tech Stack:** Markdown, YAML, shell filesystem operations, symlinks, ripgrep

---

## File Structure

Planned files and responsibilities:

- Create: `skills/memory-system-operator/SKILL.md`
  Canonical repository copy of the skill entrypoint.
- Create: `skills/memory-system-operator/references/local-memory-system.md`
  Skill-local reference material kept in-repo.
- Create: `skills/memory-system-operator/agents/openai.yaml`
  Agent metadata moved into the repository-owned skill.
- Modify: `docs/superpowers/plans/2026-04-05-memory-system-v2.md`
  Replace machine-local skill path references with repo paths.
- Modify: `docs/superpowers/plans/2026-04-07-main-merge-and-adaptive-weighting.md`
  Replace machine-local skill path references with repo paths.
- Modify: `docs/superpowers/specs/2026-04-07-skill-repo-relocation-design.md`
  Keep wording aligned with the implemented repo path.
- Verify: `~/.codex/skills/memory-system-operator`
  Replace the existing local directory with a symlink to the repo skill.

### Task 1: Create The Repository-Owned Skill Directory

**Files:**
- Create: `skills/memory-system-operator/SKILL.md`
- Create: `skills/memory-system-operator/references/local-memory-system.md`
- Create: `skills/memory-system-operator/agents/openai.yaml`

- [ ] **Step 1: Capture the current source files and verify the repo skill directory does not exist yet**

```bash
find /Users/chenchen/.codex/skills/memory-system-operator -maxdepth 3 -type f | sort
find skills -maxdepth 3 -type f 2>/dev/null | sort
```

Expected: the local skill files exist under `~/.codex/skills/...`, and `skills/memory-system-operator/` is not present yet.

- [ ] **Step 2: Create the repository skill directory structure**

```bash
mkdir -p skills/memory-system-operator/references skills/memory-system-operator/agents
```

- [ ] **Step 3: Copy the current skill files into the repository**

```bash
cp /Users/chenchen/.codex/skills/memory-system-operator/SKILL.md skills/memory-system-operator/SKILL.md
cp /Users/chenchen/.codex/skills/memory-system-operator/references/local-memory-system.md skills/memory-system-operator/references/local-memory-system.md
cp /Users/chenchen/.codex/skills/memory-system-operator/agents/openai.yaml skills/memory-system-operator/agents/openai.yaml
```

- [ ] **Step 4: Verify the repository now contains the canonical skill files**

```bash
find skills/memory-system-operator -maxdepth 3 -type f | sort
```

Expected: the three expected files are present in the repository skill directory.

### Task 2: Replace Machine-Local Skill References In Repo Docs

**Files:**
- Modify: `docs/superpowers/plans/2026-04-05-memory-system-v2.md`
- Modify: `docs/superpowers/plans/2026-04-07-main-merge-and-adaptive-weighting.md`
- Modify: `docs/superpowers/specs/2026-04-07-skill-repo-relocation-design.md`

- [ ] **Step 1: Write the failing repo-path verification search**

```bash
rg -n '/Users/chenchen/.codex/skills/memory-system-operator|~/.codex/skills/memory-system-operator' docs
```

Expected: FAIL in the sense that it returns matches from plan files that still point at the machine-local path.

- [ ] **Step 2: Update repo docs to use `skills/memory-system-operator/...` as the canonical path**

```text
Replace `/Users/chenchen/.codex/skills/memory-system-operator/SKILL.md`
with `skills/memory-system-operator/SKILL.md`
```

Constraint: keep skill-internal references like `references/local-memory-system.md` relative inside `SKILL.md`.

- [ ] **Step 3: Re-run the repo-path verification search**

Run: `rg -n '/Users/chenchen/.codex/skills/memory-system-operator|~/.codex/skills/memory-system-operator' docs`
Expected: no matches unless a line is explicitly documenting the symlink installation step.

### Task 3: Switch The Local Codex Skill Install To A Symlink

**Files:**
- Verify: `~/.codex/skills/memory-system-operator`

- [ ] **Step 1: Inspect the existing local skill path before changing it**

```bash
ls -la /Users/chenchen/.codex/skills/memory-system-operator
readlink /Users/chenchen/.codex/skills/memory-system-operator || true
```

Expected: the path is a real directory, not already a symlink.

- [ ] **Step 2: Replace the local directory with a backup plus symlink to the repo copy**

```bash
mv /Users/chenchen/.codex/skills/memory-system-operator /Users/chenchen/.codex/skills/memory-system-operator.backup
ln -s /Users/chenchen/codexClaw/skills/memory-system-operator /Users/chenchen/.codex/skills/memory-system-operator
```

- [ ] **Step 3: Verify the symlink resolves to the repository skill**

```bash
ls -la /Users/chenchen/.codex/skills | rg 'memory-system-operator'
readlink /Users/chenchen/.codex/skills/memory-system-operator
find /Users/chenchen/.codex/skills/memory-system-operator -maxdepth 3 -type f | sort
```

Expected: the symlink target is `/Users/chenchen/codexClaw/skills/memory-system-operator` and the expected files remain visible through the symlink.

### Task 4: Final Verification And Clean Summary

**Files:**
- Verify: repository working tree

- [ ] **Step 1: Run the final reference checks**

```bash
rg -n 'memory-system-operator' docs skills
rg -n '/Users/chenchen/.codex/skills/memory-system-operator|~/.codex/skills/memory-system-operator' docs skills
```

Expected: the first command finds the new repo skill references; the second finds no stale canonical-path references in repo-owned docs.

- [ ] **Step 2: Review the final working tree state**

```bash
git status --short
git diff --stat
```

- [ ] **Step 3: Summarize the resulting installation model**

```text
The canonical skill source now lives at `skills/memory-system-operator/` in the repository.
The local Codex skill path is a symlink to that repository directory.
Repo docs refer to the repository path, not a machine-local canonical location.
```
