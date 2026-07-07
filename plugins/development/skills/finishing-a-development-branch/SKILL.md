---
name: finishing-a-development-branch
description: Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup
---

# Finishing a Development Branch

## Overview

Guide completion of development work by presenting clear options and handling chosen workflow.

**Core principle:** Verify tests → Detect environment → Present options → Execute choice → Clean up.

**Announce at start:** "I'm using the finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, verify tests pass:**

```bash
# Run project's test suite
npm test / cargo test / pytest / go test ./...
```

**If tests fail:**
```
Tests failing (<N> failures). Must fix before completing:

[Show failures]

Cannot proceed with merge/PR until tests pass.
```

Stop. Don't proceed to Step 2.

**If tests pass:** Continue to Step 2.

### Step 2: Detect Environment

**Determine workspace state before presenting options:**

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
```

This determines which menu to show and how cleanup works:

| State | Menu | Cleanup |
|-------|------|---------|
| `GIT_DIR == GIT_COMMON` (normal repo) | Standard 4 options | No worktree to clean up |
| `GIT_DIR != GIT_COMMON`, named branch | Standard 4 options | Provenance-based (see Step 6) |
| `GIT_DIR != GIT_COMMON`, detached HEAD | Reduced 3 options (no merge) | No cleanup (externally managed) |

### Step 3: Determine Base Branch

```bash
# Try common base branches
git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
```

Or ask: "This branch split from main - is that correct?"

### Step 4: Present Options

Present the choice with a single **`AskUserQuestion`** call — the native structured picker — not a typed-number prose list. The options are mutually exclusive and few (≤4), which is exactly what `AskUserQuestion` is for; it lets the user click instead of retyping a number and keeps the choice unambiguous (a prose "1… 2… which option?" is the open-ended-question pitfall in Common Mistakes). Fill `<feature-branch>` / `<base-branch>` / `<path>` from Steps 2–3, and put each option's context in its `description` — don't precede the question with a wall of prose.

**Normal repo and named-branch worktree — exactly these 4 options:**

```yaml
AskUserQuestion:
  question: "Implementation is complete and tests pass. How do you want to finish <feature-branch>?"
  header: "Finish branch"
  multiSelect: false
  options:
    - label: "Merge to <base-branch> locally"
      description: "Merge <feature-branch> into <base-branch> locally, verify tests on the result, then delete the branch (and clean up a development-created worktree)."
    - label: "Push + open a PR"
      description: "Push <feature-branch> and open a Pull Request; the worktree stays alive so you can iterate on review feedback. Needs a configured remote."
    - label: "Keep the branch as-is"
      description: "Leave <feature-branch> and its worktree in place — you'll integrate it later. Nothing is merged, pushed, or deleted."
    - label: "Discard this work"
      description: "Permanently delete the branch, its commits, and any worktree. You'll be asked to type 'discard' to confirm before anything is removed."
```

**Detached HEAD (externally managed workspace) — exactly these 3 options (no local merge):**

```yaml
AskUserQuestion:
  question: "Implementation is complete and tests pass. You're on a detached HEAD (externally managed workspace). How do you want to finish?"
  header: "Finish branch"
  multiSelect: false
  options:
    - label: "Push as a new branch + open a PR"
      description: "Create a branch from this HEAD, push it, and open a Pull Request. Needs a configured remote."
    - label: "Keep as-is"
      description: "Leave the work in place — you'll handle it later. Nothing is pushed or deleted."
    - label: "Discard this work"
      description: "Permanently delete the commits (and any branch you create from this HEAD). You'll be asked to type 'discard' to confirm first."
```

Map the selected option to the matching section in Step 5. The one place that deliberately stays a typed prompt is the **discard confirmation** (Step 5, Option 4): a single click is too cheap for an irreversible delete, so selecting "Discard" routes to a typed `discard` gate before anything is removed.

### Step 5: Execute Choice

#### Option 1: Merge Locally

```bash
# Get main repo root for CWD safety
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"

# Merge first — verify success before removing anything
git checkout <base-branch>
git pull
git merge <feature-branch>

# Verify tests on merged result
<test command>

# Only after merge succeeds: cleanup worktree (Step 6), then delete branch
```

Then: Cleanup worktree (Step 6), then delete branch:

```bash
git branch -d <feature-branch>
```

#### Option 2: Push and Create PR

```bash
# Push branch
git push -u origin <feature-branch>

# Create PR
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<2-3 bullets of what changed>

## Test Plan
- [ ] <verification steps>
EOF
)"
```

**Do NOT clean up worktree** — user needs it alive to iterate on PR feedback.

#### Option 3: Keep As-Is

Report: "Keeping branch <name>. Worktree preserved at <path>."

**Don't cleanup worktree.**

#### Option 4: Discard

Selecting "Discard" in the picker routes here — it does NOT delete anything yet. **Require a typed confirmation first** (a single click is too cheap for an irreversible delete):
```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>
- Worktree at <path>

Type 'discard' to confirm.
```

Wait for exact confirmation.

If confirmed:
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
```

Then: Cleanup worktree (Step 6), then force-delete branch:
```bash
git branch -D <feature-branch>
```

### Step 6: Cleanup Workspace

**Only runs for Options 1 and 4.** Options 2 and 3 always preserve the worktree.

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
WORKTREE_PATH=$(git rev-parse --show-toplevel)
```

**If `GIT_DIR == GIT_COMMON`:** Normal repo, no worktree to clean up. Done.

**If worktree path is under `.worktrees/` or `worktrees/`:** This plugin created this worktree — we own cleanup.

```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
git worktree remove "$WORKTREE_PATH"
git worktree prune  # Self-healing: clean up any stale registrations
```

**Otherwise:** The host environment (harness) owns this workspace. Do NOT remove it. If your platform provides a workspace-exit tool, use it. Otherwise, leave the workspace in place.

## Quick Reference

| Option | Merge | Push | Keep Worktree | Cleanup Branch |
|--------|-------|------|---------------|----------------|
| 1. Merge locally | yes | - | - | yes |
| 2. Create PR | - | yes | yes | - |
| 3. Keep as-is | - | - | yes | - |
| 4. Discard | - | - | - | yes (force) |

## Common Mistakes

**Skipping test verification**
- **Problem:** Merge broken code, create failing PR
- **Fix:** Always verify tests before offering options

**Prose options instead of the picker**
- **Problem:** A typed-number list ("1. Merge … Which option?") is the open-ended-question trap — ambiguous, easy to misread, and forces the user to retype a number.
- **Fix:** Present the choice with `AskUserQuestion` (4 options, or 3 for detached HEAD). The discard *confirmation* deliberately stays a typed gate — see Option 4.

**Cleaning up worktree for Option 2**
- **Problem:** Remove worktree user needs for PR iteration
- **Fix:** Only cleanup for Options 1 and 4

**Deleting branch before removing worktree**
- **Problem:** `git branch -d` fails because worktree still references the branch
- **Fix:** Merge first, remove worktree, then delete branch

**Running git worktree remove from inside the worktree**
- **Problem:** Command fails silently when CWD is inside the worktree being removed
- **Fix:** Always `cd` to main repo root before `git worktree remove`

**Cleaning up harness-owned worktrees**
- **Problem:** Removing a worktree the harness created causes phantom state
- **Fix:** Only clean up worktrees under `.worktrees/` or `worktrees/`

**No confirmation for discard**
- **Problem:** Accidentally delete work
- **Fix:** Require typed "discard" confirmation

## Red Flags

**Never:**
- Proceed with failing tests
- Merge without verifying tests on result
- Delete work without confirmation
- Force-push without explicit request
- Remove a worktree before confirming merge success
- Clean up worktrees you didn't create (provenance check)
- Run `git worktree remove` from inside the worktree

**Always:**
- Verify tests before offering options
- Detect environment before presenting menu
- Present the choice via `AskUserQuestion` (4 options, or 3 for detached HEAD) — not a typed-number prose list
- Get typed confirmation for Option 4 (the one deliberate exception — never a one-click discard)
- Clean up worktree for Options 1 & 4 only
- `cd` to main repo root before worktree removal
- Run `git worktree prune` after removal
