# hooks

Subcommand: `enable` | `disable` | `status` | (empty → `status`).

## Validate subarg

If the user passed anything other than `enable`, `disable`, `status`, or nothing,
tell the user:

> Unknown hooks subcommand. Expected: enable, disable, status.

Stop.

## Run

```bash
wiki-hooks <subarg>
```

(When subarg is empty, invoke the wrapper with no argument — it defaults to
`status`.)

## Output

Relay stdout verbatim — one line:

- `hooks: enabled`
- `hooks: disabled`
- `hooks: enabled (already)`
- `hooks: disabled (already)`

On non-zero exit, relay stderr verbatim and stop.

No `TaskCreate` — this is a single-step operation.
