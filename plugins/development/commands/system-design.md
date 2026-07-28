---
description: "Launch the architect — the design lead. Turns implementation intent into an approved OpenSpec change: proposal, per-capability delta specs, and design. Never implements. Runs as its own background session."
argument-hint: '[what you want to build]'
disable-model-invocation: true
allowed-tools: Bash(claude:*)
---

The user's request for the architect: `$ARGUMENTS`

1. Run exactly this command. If `$ARGUMENTS` is empty, use the prompt
   `Collaborate with me on requirements and design — ask me what we are building` instead of `$ARGUMENTS`:
   ```bash
   claude --agent development:architect --name architect --bg "$ARGUMENTS"
   ```
2. Report the backgrounded session id the command prints.
3. Tell the user: the architect is running in the background — open agent view (`←` or
   `claude agents`) to watch it, `Space` to peek, `→`/`Enter` to attach. The row shows
   **needs input** when the architect has a question.
