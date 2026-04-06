# Skill Repo Relocation Design

**Goal:** Move `memory-system-operator` from a machine-local skill directory into this repository so the skill, references, and any helper scripts are shareable, versioned, and path-stable.

## Problem

The current skill lives under `~/.codex/skills/memory-system-operator`, which makes the skill entrypoint machine-local. That creates three problems:

1. the skill cannot be shared cleanly through the repository
2. helper assets like `references/` or future `scripts/` are tied to one machine path
3. docs and plans drift toward absolute-path instructions that other users cannot follow

## Recommended Approach

Create a repository-owned skill directory at `skills/memory-system-operator/` and treat it as the source of truth.

The directory will contain:

1. `skills/memory-system-operator/SKILL.md`
2. `skills/memory-system-operator/references/local-memory-system.md`
3. `skills/memory-system-operator/agents/openai.yaml`
4. optionally later: `skills/memory-system-operator/scripts/...`

The local Codex installation path `~/.codex/skills/memory-system-operator` will become a symlink pointing to the repository directory. That preserves local discoverability while making the repository copy canonical.

## Path Strategy

Path handling should follow two rules:

1. repository resources should be referenced by repository-relative paths when the audience is reading repo docs
2. skill-internal assets should be referenced relative to the skill root when the audience is reading `SKILL.md`

Concretely:

1. replace references to `~/.codex/skills/memory-system-operator/SKILL.md` in repo docs with `skills/memory-system-operator/SKILL.md`
2. keep `references/local-memory-system.md` as a relative skill-local reference inside `SKILL.md`
3. describe the project root as the current repository root rather than as a machine-specific installation requirement whenever possible

Absolute paths may still appear when the code itself truly needs a concrete default path, such as the default SQLite database location in this repo, but skill installation and skill asset discovery should no longer depend on a user-specific absolute path.

## Migration Behavior

The migration should be straightforward and local-first:

1. create the repository skill directory structure
2. copy or move the existing skill files into the repo
3. update repo docs and plan files that still point at the machine-local skill path
4. replace the existing `~/.codex/skills/memory-system-operator` directory with a symlink to the repository copy
5. verify the symlink resolves correctly and the moved files remain readable

## Testing

Verification should cover both content and installation shape:

1. confirm the repository contains the expected skill files
2. confirm `~/.codex/skills/memory-system-operator` is a symlink to the repo path
3. confirm no remaining repo docs point to the old machine-local skill path unless intentionally documenting the symlink step
4. confirm `SKILL.md` references local assets using skill-relative paths

## Non-Goals

This change does not redesign the memory workflow itself.

This change does not require introducing Python helper scripts immediately. It only creates a repository layout that supports them cleanly.
