# development

A **Claude-Code-only** development workflow: design → plan → TDD → review → ship, with the
discipline enforced by the harness rather than volunteered by the model.

The methodology comes from [obra/superpowers](https://github.com/obra/superpowers) and its
Claude-Code-native fork [pcvelz/superpowers](https://github.com/pcvelz/superpowers), which this
build takes its inspiration and several of its skills from. It has since diverged: multi-harness
support is gone, and the design phase has been rebuilt around the architect below.

## Requirements

Nothing below is bundled.

| Needed for | Requirement |
|---|---|
| `/system-design` | The **OpenSpec CLI** on `PATH` (developed against 1.6.0). Without it the architect stops at its first command. |
| Any hook | `bash`, `jq`, `sed`. A missing `jq` makes a hook **fail open** — it passes silently instead of enforcing. On Windows without bash, `run-hook.cmd` exits successfully having run nothing. |
| Model routing | `python3` — any 3.x. One stdlib-only script sanitises the routing file before it is injected. |
| Visual companion | `node` |
| Cross-model review (optional) | A Codex MCP server you configure yourself. The architect discloses a missing advisor pass and continues, so this weakens review rather than blocking it. |

### Install

```bash
# the plugin
claude plugin marketplace add https://github.com/a-r-it/automaton
claude plugin install development@automaton

# the architect's CLI
npm i -g @fission-ai/openspec

# jq, if you don't have it
brew install jq          # macOS
sudo apt install jq      # Debian/Ubuntu
```

`python3` ships with macOS and most Linux distributions — `python3 --version` to confirm. `npm`
comes with `node`, so if the OpenSpec install worked you already have both. Then
`/reload-plugins`, or start a new session.

Check what landed:

```bash
openspec --version && jq --version && python3 --version && node --version
```

## Two entry points

**`/system-design <what you want to build>`** launches the **architect** — a background agent that
turns intent into an approved OpenSpec change: proposal → per-capability delta specs → design. It
never implements. Every artifact is drafted, validated, reviewed by a read-only `artifact-reviewer`,
and put in front of you before the next one starts. The specs artifact first consults a routed panel
of expert agents whose MUST requirements become the delta specs. Watch it with `claude agents`.

**`/brainstorm`** is the classic flow — explore, ask, offer approaches, write a design doc, hand off
to `writing-plans`. Unchanged, and still where `developer-workflow` routes creative work.

Either way, implementation is the same: `writing-plans` → `executing-plans` /
`subagent-driven-development` → TDD → review → verification.

## What's inside

16 skills · 7 commands · 10 agents · 4 registered hooks · 8 dormant hooks.

Run `/onboard` for a guided setup of everything optional below — it asks one question per feature
and writes the files.

## Hooks

Four are registered by the plugin and need no settings edit:

| Event | Hook | What it does |
|---|---|---|
| SessionStart | `session-start` | Injects `developer-workflow` plus any active routing / commit-strategy notice |
| TaskCreate | `pre-taskcreate-model-tier` | Blocks a plan task whose metadata has no valid `modelTier` |
| Agent | `pre-agent-model-routing` | Blocks a dispatch whose model disagrees with the in-progress task's tier |
| EnterPlanMode | `pre-enterplanmode-block` | Denies native plan mode, which traps the session |

Eight more ship as files in `hooks/` and are **not** registered — enable the ones you want from
`.claude/settings.json`:

| Hook | What it does | Guard |
|---|---|---|
| `pre-commit-check-tasks` | Blocks `git commit` while a task is `in_progress` | — |
| `post-task-complete-revalidate` | Blocks closing a user-gate task without per-criterion evidence | `DEVELOPMENT_USERGATE_GUARD` |
| `stop-revalidate-user-gates` | Blocks "plan complete" when gates were closed without proof | `DEVELOPMENT_USERGATE_STOP_GUARD` |
| `pre-task-blockedby-enforce` | Refuses `in_progress` while `blockedBy` tasks are still open | `DEVELOPMENT_BLOCKEDBY_GUARD` |
| `pre-agent-task-dispatch-validate` | Enforces a task's `subagentType` / `model` / `dispatchBrief` | `DEVELOPMENT_DISPATCH_GUARD` |
| `post-agent-return-validate` | Rejects a subagent report missing required evidence tokens | `DEVELOPMENT_AGENT_RETURN_GUARD` |
| `stop-deflection-guard` | Blocks "context is full" excuses below 50% real usage | `DEVELOPMENT_DEFLECTION_GUARD` |
| `pre-askuser-handoff-guard` | Re-forces the `writing-plans` execution-method question | `DEVELOPMENT_ROUTING_GUARD` |

Every hook file opens with a header explaining its logic, its inputs, and its escape hatch — read
that before enabling one. All hooks fail open on error. `DEVELOPMENT_HOOKS=0` disables all of them
at once; `DEVELOPMENT_ROUTING_GUARD=0` and `DEVELOPMENT_PLANMODE_GUARD=0` cover the registered ones.

> A task metadata `"model"` pin is currently unchecked: `pre-agent-model-routing` defers pins to
> `pre-agent-task-dispatch-validate`, which is dormant. Register it if you rely on pins.

## Optional configuration

Both files may live in the project (`.automaton/development/`) or as a user default
(`~/.automaton/development/`). Project first, then user — the first file found wins entirely, with
no merging. Delete the file to switch the feature off.

**`model-routing.json`** — route plan-execution subagents to cheaper models. Tiers are abstract on
purpose; the file decides what they mean today.

```json
{"mechanical": "haiku", "standard": "sonnet", "frontier": "inherit"}
```

`mechanical` = 1–2 files, complete spec, no design judgment (most tasks in a good plan) ·
`standard` = multi-file integration, pattern matching, debugging · `frontier` = design and
architecture judgment. `"inherit"` runs that tier on the session model. Implementers run at their
task's tier; spec and code-quality reviewers run at `standard`; the final whole-plan reviewer stays
at session level. Without the file every gate no-ops.

**`workflow.json`** — one commit per plan instead of one per task.

```json
{"commitStrategy": "at-end"}
```

Plans are then written without per-task Commit steps and end with a single commit task blocked by
all the others; implementers do not commit, and reviewers read the uncommitted diff. Valid values
are `"per-task"` (default) and `"at-end"`. There is no enforcement gate here — the session-start
notice is the only delivery mechanism, so it applies from the next session on.

## Credits

Built on **obra/superpowers** (Jesse Vincent) and **pcvelz/superpowers**, both MIT. Several skills
here still descend directly from them. Original copyrights are retained — see `NOTICE`.
