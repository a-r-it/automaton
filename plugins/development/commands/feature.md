---
description: "Launch feature-development — the background feature orchestrator. Takes the path to an approved spec (+ optional slug), plans it through the task-planner agent, and executes it task-by-task through implementer and reviewer agents. Runs as its own background session."
argument-hint: '<spec-path> [<slug>]'
disable-model-invocation: true
allowed-tools: Bash(claude:*)
---

The user's arguments for feature-development: `$ARGUMENTS`

1. If `$ARGUMENTS` is empty, tell the user this command needs the path to an approved
   spec (optionally followed by a slug), e.g.
   `/development:feature docs/development/specs/2026-07-31-thing-design.md thing`,
   and stop — there is no raw-idea mode; ideas start at `/development:brainstorm`.
2. Otherwise run exactly this command:
   ```bash
   claude --agent development:feature-development --name feature-development --bg --permission-mode auto \
     --settings '{"worktree":{"bgIsolation":"none"}}' "$ARGUMENTS"
   ```
3. Report the backgrounded session id the command prints.
4. Tell the user: feature-development is running in the background — open agent view (`←` or
   `claude agents`) to watch it, `Space` to peek, `→`/`Enter` to attach. The row shows
   **needs input** when it has a question; it pauses only on real gates.
