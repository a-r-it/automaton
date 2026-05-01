# setup

## Routing

Dispatch by `ARGUMENTS`:

- No extra args (bare `setup`) → **Guided bootstrap** section below (7-step task list).
- `setup refresh-schemas` → **Refresh schemas** section.
- `setup verify` → **Verify** section.
- `setup summary` → **Summary** section.
- Any other subcommand → relay `wiki-setup --help` to the user and stop.

---

## Guided bootstrap

Before any step runs, create the full task list via `TaskCreate` (all six at once):

1. Check uv installed
2. Sync Python dependencies
3. Create wiki directories
4. Enable automation hooks
5. Configure .gitignore
6. Verify environment

Before each step, `TaskUpdate → in_progress`; after, `→ completed`.

**On non-zero exit from any command below, relay the script's stderr to the
user verbatim and stop.** Leave the current task `in_progress`, mark every
subsequent task `deleted` with a short reason.

## 1. Check uv

```bash
check-uv
```

## 2. Sync dependencies

```bash
wiki-setup sync-deps
```

## 3. Initialize wiki tree

```bash
wiki-setup init-tree
```

## 4. Hooks

Ask via `AskUserQuestion`:

- Question: "Enable automatic conversation capture and context injection for this project?"
- Options:
  - `Enable` — session-start loads the wiki index into context, session-end flushes the transcript to the daily-logs directory, pre-compact captures context before auto-compaction.
  - `Skip` — hooks stay registered but do nothing. Toggle later with `automaton:wiki hooks enable` / `automaton:wiki hooks disable`.

Then, if the user chose `Enable`:

```bash
wiki-setup hooks --enable
```

If the user chose `Skip`:

```bash
wiki-setup hooks --skip
```

(Mark the task completed with a note "user skipped hook activation".)

## 5. Gitignore

(a) Probe eligibility:

```bash
wiki-setup gitignore-eligible
```

Parse the stdout JSON `{"git": bool, "eligible": [str]}`. If `git` is false or
`eligible` is empty, mark the task completed with note "nothing to offer" and
skip to step 6.

(b) Build `AskUserQuestion` options dynamically from `eligible`, each labelled
`"<dir>/ — <purpose>"`, plus a `Nothing` option. Purposes:

- `wiki/` — compiled knowledge base (LLM-owned articles + indexes)
- `daily/` — raw conversation logs (append-only)
- `sources/` — external reference docs (immutable after ingest)
- `Nothing` — track remaining eligible directories in git

Question text: "Which of these should be added to `.gitignore`?"

(c) If the user selected at least one directory (and not only `Nothing`):

```bash
wiki-setup gitignore-apply --dirs=<csv>
```

If the user selected only `Nothing` or nothing at all, skip the apply and mark
the task completed with note "user declined".

## 6. Verify

```bash
wiki-setup verify
```

## 7. Print summary

```bash
wiki-setup summary
```

---

## Refresh schemas

Re-applies plugin-shipped schema templates (`memory/librarian/schemas/*.md`) to
the active wiki. Use after the plugin updates `_schema.md` contents or when
`wiki-render-prompt` / compile fails with `missing YAML frontmatter` / `no
schemas found`.

Interactive: for each existing user `_schema.md` that differs from the plugin
version, prints a diff and prompts `[k]eep (default) / [o]verwrite`. New
schemas (directories with no `_schema.md`) are written without prompting.

```bash
wiki-setup refresh-schemas
```

Behavior:
- Matches user schemas by `type:` frontmatter field, not by directory — safe
  under directory renames (`decisions/` → `adr/`).
- On overwrite: writes `_schema.md.bak` with the previous content, then
  replaces `_schema.md`.
- Prints a final `Summary: N kept, M overwritten, K new` line.

On non-zero exit: relay stderr verbatim and stop. Common causes: plugin
schemas missing mandatory `type:` or `default_dir:` frontmatter.

Running non-interactively (e.g. as part of an orchestrated flow), pipe the
desired answer:

```bash
printf 'o\n' | wiki-setup refresh-schemas   # overwrite single diff
printf 'k\n' | wiki-setup refresh-schemas   # keep user version
```

---

## Verify

Runs environment sanity checks: `hooks.json` validity and `wiki-compile
--dry-run`. On success exits 0 silently. On failure, relay script stderr to
the user verbatim.

```bash
wiki-setup verify
```

Use after a refactor touching `bin/hook-*`, `hooks/hooks.json`,
`memory/scripts/*`, or `_schema.md` files.

---

## Summary

Prints the activation summary (hooks marker state, wiki tree presence,
git-tracked directories) for the current project.

```bash
wiki-setup summary
```

Read-only; always exits 0.
