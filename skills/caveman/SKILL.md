---
name: caveman
description: Switch caveman terse mode — /caveman lite|full|ultra|off
user-invocable: true
argument-hint: "lite|full|ultra|off"
---

Switch caveman terse mode. Valid: `lite`, `full`, `ultra`, `off`.

## Steps

**1. Validate** — normalize `$ARGUMENTS`: strip whitespace, lowercase. Must be exactly `lite`, `full`, `ultra`, or `off`. If empty or unrecognized, respond with exactly:
```
Usage: /caveman lite|full|ultra|off
```
Stop. Make no changes.

**2. Edit config** — run via Bash (`$ARGUMENTS` and `${CLAUDE_PLUGIN_ROOT}` are substituted by Claude Code before execution):

```bash
${CLAUDE_PLUGIN_ROOT}/skills/caveman/scripts/caveman-switch '$ARGUMENTS'
```

**3. Inject rules** — if `$ARGUMENTS` (normalized) is `off`, skip this step. Otherwise, read `${CLAUDE_PLUGIN_ROOT}/skills/caveman/references/prompt.md` via Read tool and follow its rules for the remainder of this session.

**4. Confirm** — respond with **only** the bracketed confirmation. No narration, no explanation:
- `lite` → `[CAVEMAN: LITE]`
- `full` → `[CAVEMAN: FULL]`
- `ultra` → `[CAVEMAN: ULTRA]`
- `off` → `[CAVEMAN: OFF]`
