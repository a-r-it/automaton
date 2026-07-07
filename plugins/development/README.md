# development

A **Claude-Code-only** build of [Superpowers](https://github.com/obra/superpowers) — the agentic
software-development methodology (brainstorm → plan → TDD → review → ship), merged with the
Claude-Code-native fork [pcvelz/superpowers](https://github.com/pcvelz/superpowers).

This is a personal fork: multi-harness support (Codex/Cursor/Gemini/OpenCode) is removed; the
CC-native task gates, model-routing hooks, and gate skills are kept.

## Install (local dev)

    claude plugin marketplace add /path/to/development
    claude plugin install development@development-dev

Then `/reload-plugins`.

## What's inside

- 15 skills (TDD, systematic-debugging, brainstorming, writing/executing plans,
  subagent-driven-development, code review, git worktrees, gates, developer-workflow)
- 6 commands: `/brainstorm`, `/write-plan`, `/execute-plan`, `/gate-check`, `/specify-gate`, `/onboard`
- Active hooks: SessionStart context injection + PreToolUse model-routing/tier/handoff guards
- Opt-in enforcement hooks in `hooks/`

## Credits

Merge-port of **obra/superpowers** (Jesse Vincent) and **pcvelz/superpowers**, both MIT. See `NOTICE`.

---

## User-Thrown Gate Enforcement — Optional Flow

*Canonical design doc: [`docs/user-gate-flow.md`](docs/user-gate-flow.md). The section below is a reader-facing summary.*

This flow addresses a recurring failure: the user says "add a gate" or "verify it works" without specifying **how**, the agent invents a verification method, then finds it expensive at execution time and walks around it — closing the gate with an inline shortcut. The fix is a three-layer architecture that *never bothers the user during planning* and only surfaces a forced question when the agent genuinely can't proceed without one.

**The hooks ship always-on** (registered in the plugin's `hooks.json`) — no `.claude/settings.json` edit needed. They sit inert until a user-thrown gate task exists. Disable all development hooks with `DEVELOPMENT_HOOKS=0`, or individual hooks with their per-hook guards (see Environment Variables).

### Design principle — don't bombard the user during planning

Users who want questions will say "brainstorm". Users who ask for a gate during planning just want the work done, they don't want a four-question interrogation. So `writing-plans` is silent here: it applies the **stricter definition** of a gate and tags liberally. Better to over-tag and let the execution-time hook filter than to over-question the user mid-plan.

### The three layers

| Layer | When | What it does |
|-------|------|--------------|
| **Write-plan (silent tagging)** | Plan authoring | Detects gate-language in the brief ("verify", "prove", "gate", "first on one then all", "make sure", "don't proceed until"). Tags the resulting task with `userGate: true` + `tags: ["user-gate"]`. No user questions. Uses the stricter definition: strict user gates AND strict agent gates AND gray-in-between all get tagged. |
| **Execute-plan (hard trigger via hook)** | Task close / stop | The PostToolUse + Stop hooks fire when a tagged task is closed. The agent must then assess each criterion and choose one of two paths (below). |
| **`/specify-gate` slash command (dormant unless hook active)** | Execute-plan, only when the agent cannot proceed | Asked 3-4 structured questions to the user that lock down the HOW: observable outcome, proof mechanism, scope, failure policy. Produces a structured verify spec the agent consumes. |

### Agent decision at execute time

When a tagged task comes up, the agent asks itself: **do I know *how* to verify this?**

- **"Verify the `/health` endpoint returns 200"** → the HOW is self-evident. Agent just hits the endpoint, captures the output, posts `AC: <criterion> — PROVEN BY <evidence>`. No slash command needed. The hook sees the proof and passes.
- **"Check it works"** → the HOW is vague. Agent invokes `/specify-gate`, which asks the user the 3-4 minimal questions, then uses the answers to execute real verification. No silent invention, no inline shortcut.
- **Write-plan explicitly flagged `requiresUserSpecification: true`** → same path: invoke `/specify-gate`, ask the user.

The user is only interrupted at execute time, and only when the alternative is the agent making something up.

### Activation

Both hooks are always-on (registered in the plugin's `hooks.json`) — no `.claude/settings.json` edit needed. Disable them with `DEVELOPMENT_HOOKS=0` (all development hooks) or the per-hook guards below. When disabled:
- `writing-plans` still tags gates (harmless extra metadata).
- `/specify-gate` still exists but is never triggered automatically.
- Nothing enforces evidence at close — behavior is identical to vanilla.

Install one hook or both. The PostToolUse hook catches per-task closures; the Stop hook catches end-of-plan "everything done" claims. They compose — both firing on the same session is fine.

### Escape hatches

Both hooks fail-open on errors and have env-var kill switches (`DEVELOPMENT_USERGATE_GUARD=0`, `DEVELOPMENT_USERGATE_STOP_GUARD=0`) for one-off session bypasses without editing settings.

### Verify it's working

Tail the hook trace log while a tagged gate task is closing: `tail -F /tmp/claude-hooks/user-gate-trace.log`. See [Hook Trace Logging](#hook-trace-logging) for the full schema.

---

## Subagent Model Routing — Optional Flow

*Canonical design doc: [`docs/model-routing-flow.md`](docs/model-routing-flow.md). The section below is a reader-facing summary.*

This flow addresses a cost problem that frontier-priced models (Opus, Fable) made acute: plan execution via `subagent-driven-development` spawns an implementer plus two reviewers per task — plus re-dispatches for fixes and escalations — and every one of them inherits the session model by default. On a top-tier session, a ten-task plan means thirty-plus top-tier subagent dispatches, most doing work a cheaper model handles fine when the plan is well-specified. Prompt caching does not help here: caching discounts input tokens, while fan-out cost is dominated by freshly generated output. Routing lowers the per-token rate of dispatches; it does not impose token budgets or spend ceilings (see the design doc for boundaries).

**The whole flow is opt-in, with a single switch: `.automaton/development/model-routing.json` in your project.** The enforcement gates ship with the plugin but are dormant — without that file every check no-ops and behavior is byte-identical to vanilla. No settings to edit, no hooks to register.

### How it works — three harness-enforced layers

Skills prose is not enforcement; agents skip instructions under load. So every layer here is executed by the harness, not volunteered by the model:

| Layer | When | What it does |
|-------|------|--------------|
| **Session notice** (`session-start` hook) | Session start | Routing file detected → the tier rules and your mapping are injected into context. The agent starts the session already knowing the rules. |
| **Plan gate** (`pre-taskcreate-model-tier` hook) | Every `TaskCreate` | A plan task without a valid `"modelTier"` in its `json:metadata` fence is blocked — including plan-shaped tasks (template headers or numbered subjects) that omit the fence entirely; the block message contains the full tier table, so the agent fixes and re-issues without reading anything. |
| **Dispatch gate** (`pre-agent-model-routing` hook) | Every `Agent` dispatch | While tiered tasks are in progress, allows the union of the in-progress tasks' tier models plus the `standard` reviewer model; blocks anything else and names the correct dispatch per role. A concrete `"model"` pin in task metadata overrides the tier (pin enforcement: see [Recommended Configuration](#recommended-configuration)). |

Both gates fail open (parse errors never brick a session) and share a kill switch: `DEVELOPMENT_ROUTING_GUARD=0`.

> **The execution-method handoff is now hook-enforced.** `pre-askuser-handoff-guard` ships always-on (in `hooks.json`), re-forcing the writing-plans handoff `AskUserQuestion`. Set `DEVELOPMENT_HOOKS=0` (all hooks) to disable it if you prefer `writing-plans` to choose subagent-driven vs inline itself.

### The tiers

| Tier | Meaning |
|------|---------|
| `"mechanical"` | Touches 1-2 files, complete spec with code in the steps, no design judgment. Most tasks in a well-specified plan. |
| `"standard"` | Multi-file coordination, integration concerns, pattern matching, debugging. |
| `"frontier"` | Design judgment, architecture decisions, broad codebase understanding. |

Tiers are abstract on purpose — plans survive model generations; the routing file decides what they mean today.

### Setup

Prefer a guided setup? Run `/onboard` — it asks one multiple-choice question per optional feature and writes the files for you. Manual setup below achieves exactly the same.

Create `.automaton/development/model-routing.json` in your project:

```json
{"mechanical": "haiku", "standard": "sonnet", "frontier": "inherit"}
```

- Keys are the three tiers; values are Agent `model` values (`haiku`, `sonnet`, `opus`, `fable`).
- `"inherit"` means: omit the model parameter — that tier runs on the session model.
- Mapping all tiers to one model gives a flat cost cap with no per-task gradation.
- Delete the file to switch routing off — the gates go dormant instantly; existing tier annotations become inert metadata.
- **User-level default:** the file may instead live at `~/.automaton/development/model-routing.json`, applying to every project that has no project-level file. Lookup is project first, then user — the first file found wins entirely (no merging). A project file of all-`"inherit"` values switches routing off for that project while a user-level default exists.

### Role assignments when routing is on

Implementers (and fix re-dispatches) run at their task's tier. Spec and code-quality reviewers run at `standard` — reviewing against explicit criteria is mid-tier work, and review output is the expensive direction at frontier prices. The final whole-plan reviewer runs after all tasks complete (no task in progress, so the dispatch gate does not constrain it) and should stay at session level — one frontier judgment pass per plan. When an implementer reports BLOCKED and needs more reasoning, escalate one tier up by updating the task's metadata transparently — never silently down.

---

## Workflow Configuration — Optional Flow

*Canonical design doc: [`docs/workflow-config-flow.md`](docs/workflow-config-flow.md). The section below is a reader-facing summary.*

### Commit Strategy

By default, plan execution commits per task: every plan task ends with its own Commit step, and implementer subagents commit their work before review. That default is unchanged and recommended — frequent commits give fine-grained history and per-task rollback. Projects that prefer a single reviewable commit per plan can opt in to an at-end strategy.

**The whole flow is opt-in, with a single switch: `.automaton/development/workflow.json` in your project.** Without that file (or without the key), behavior is byte-identical to the default.

```json
{"commitStrategy": "at-end"}
```

When `at-end` is set, a notice injected at session start instructs the agent to:

- write plans without per-task Commit steps;
- end every plan with one final task — "Commit the full implementation" — blocked by all implementation tasks;
- tell implementer subagents not to commit (the coordinator runs that final task, making the single commit), with reviewers reading the uncommitted working-tree diff.

Setup notes:

- Prefer a guided setup? Run `/onboard` — it covers this feature alongside the other optional flows.
- Valid values are `"per-task"` (the default) and `"at-end"`; anything else falls back to per-task.
- **User-level default:** the file may instead live at `~/.automaton/development/workflow.json`, applying to every project that has no project-level file. Lookup is project first, then user — the first file found wins entirely (no merging). A project file of `{"commitStrategy": "per-task"}` restores per-task commits for that project while a user-level default exists.
- Unlike model routing, this flow has no enforcement gates — the session-start notice is the only delivery mechanism, so it takes effect from the next session on and relies on plan-time compliance (see the design doc for this boundary).
- Undo: delete the file or remove the `commitStrategy` key — per-task commits resume at the next session start.

---

## Recommended Configuration

### Disable Auto Plan Mode

Claude Code may automatically enter Plan mode during planning tasks, which conflicts with the structured skill workflows in this plugin. The `pre-enterplanmode-block` hook ships always-on (in `hooks.json`) and denies `EnterPlanMode` calls — no `permissions.deny` entry needed. Set `DEVELOPMENT_PLANMODE_GUARD=0` (or `DEVELOPMENT_HOOKS=0` for all hooks) to allow native plan mode.

### Block Commits With Incomplete Tasks

Optional `PreToolUse` hook that blocks `git commit` while a native task is `in_progress`. Pending tasks pass through, so per-task commit flows work as intended.

**Always on** — registered in the plugin's `hooks.json`; no `.claude/settings.json` edit needed. Disable every development hook with `DEVELOPMENT_HOOKS=0`, or just this one with its per-hook guard (see Environment Variables).

See the header of `hooks/pre-commit-check-tasks` for how it parses the session transcript and which task states count as open.

### Force Re-Validation on User-Thrown Gate Close

Optional `PostToolUse` hook that blocks when Claude closes a **user-thrown gate** task without capturing concrete evidence for every acceptance criterion. A user-thrown gate is any task that carries `"userGate": true` or a `"user-gate"` entry in `tags` inside its `json:metadata` fence — set by `writing-plans` when the user explicitly asked for a verification step ("make sure to verify X", "add a gate", "prove it on one, then all").

Non-gate tasks pass through silently. The hook only fires when `TaskUpdate` sets status to `completed`.

**Always on** — registered in the plugin's `hooks.json`; no `.claude/settings.json` edit needed. Disable every development hook with `DEVELOPMENT_HOOKS=0`, or just this one with its per-hook guard (see Environment Variables).

See the header of `hooks/post-task-complete-revalidate` for how it parses `json:metadata` and the `USER-ORDERED GATE` banner, and how the `DEVELOPMENT_USERGATE_GUARD=0` escape hatch works.

### Re-Validate Gates on "Plan Complete" Claims

Optional `Stop` hook that complements the PostToolUse hook above. It fires when Claude signals plan completion ("plan complete", "both gates passed", "implementation complete", etc.) but the transcript shows user-thrown gate tasks were closed without subsequent per-criterion proof. Requires Claude to post evidence in the form `AC: <criterion> — PROVEN BY <evidence>` before it can stop.

**Always on** — registered in the plugin's `hooks.json`; no `.claude/settings.json` edit needed. Disable every development hook with `DEVELOPMENT_HOOKS=0`, or just this one with its per-hook guard (see Environment Variables).

See the header of `hooks/stop-revalidate-user-gates` for the full list of completion keywords and the `DEVELOPMENT_USERGATE_STOP_GUARD=0` escape hatch.

### Enforce blockedBy Ordering on in_progress

Optional `PreToolUse` hook on `TaskUpdate` that refuses to move a task into `status=in_progress` while its `blockedBy` list still points at tasks that are not yet `completed`. Motivation: observed failure mode — a coordinator jumps to a later task ("this one is simpler, zero setup") even though its declared prerequisites feed it.

The hook does not silently refuse. Its stderr invites self-assessment first ("is this a hallucination — did you already do this work informally?"), offers three escalation paths (do the blocker, cancel it if truly obsolete, or raise the ordering to the user with AskUserQuestion), and explicitly warns against the bypass move of closing the blocker with status=completed without doing the work.

**Always on** — registered in the plugin's `hooks.json`; no `.claude/settings.json` edit needed. Disable every development hook with `DEVELOPMENT_HOOKS=0`, or just this one with its per-hook guard (see Environment Variables).

See the header of `hooks/pre-task-blockedby-enforce` for the transcript-walking logic and the `DEVELOPMENT_BLOCKEDBY_GUARD=0` escape hatch.

### Enforce per-task LLM/dispatch requirements

Optional `PreToolUse` hook on `Agent` that reads the currently in_progress task's `json:metadata` fence and refuses Agent calls that disagree with its `subagentType`, `model`, or `dispatchBrief`. Use when a plan's tasks are sensitive to which tier runs them — empirical measurements, coordinator-quality work, zero-cost batches.

If a task's metadata carries `{"model": "haiku"}` and the coordinator dispatches `model: "opus"`, this hook blocks the call with a stderr explaining the mismatch and three response options (retry with the required params, update metadata transparently, or escalate via AskUserQuestion).

When the task has no dispatch requirement in metadata, the hook passes silently.

**Always on** — registered in the plugin's `hooks.json`; no `.claude/settings.json` edit needed. Disable every development hook with `DEVELOPMENT_HOOKS=0`, or just this one with its per-hook guard (see Environment Variables).

See the header of `hooks/pre-agent-task-dispatch-validate` for the transcript-walking logic and the `DEVELOPMENT_DISPATCH_GUARD=0` escape hatch. Metadata keys are documented in `skills/shared/task-format-reference.md`.

### Force Subagent Evidence on Return

Optional `PostToolUse` hook on `Agent` that fires the moment a subagent's `tool_result` arrives — before the coordinator absorbs it and reports upward. If the in_progress task carries `requireEvidenceTokens` (multi-axis evidence requirement) or the `requireABCompare: true` shortcut, the hook checks that the subagent's report contains at least one token from each axis. Missing axes → block with stderr naming them, forcing immediate re-dispatch rather than "looks good" at close time.

When the task has no evidence requirement in metadata, the hook passes silently.

**Always on** — registered in the plugin's `hooks.json`; no `.claude/settings.json` edit needed. Disable every development hook with `DEVELOPMENT_HOOKS=0`, or just this one with its per-hook guard (see Environment Variables).

See the header of `hooks/post-agent-return-validate` for the metadata schema and the `DEVELOPMENT_AGENT_RETURN_GUARD=0` escape hatch.

### Hook Trace Logging

All three user-gate hooks (post-complete revalidate, stop revalidate, pre-blockedby enforce) write one-line decision traces to `/tmp/claude-hooks/user-gate-trace.log` (override via `DEVELOPMENT_USERGATE_TRACE_LOG`). Tail during development with:

```
tail -F /tmp/claude-hooks/user-gate-trace.log
```

Each line is pipe-separated: `TIMESTAMP | hook-name | task=N | event | reason`. Events include `enter`, `skip`, `parsed`, `scanned`, `pass`, `block`, `error`. Skip reasons identify the short-circuit (e.g. `tool=Bash`, `status=pending`, `superpowers-active`, `guard=0`). This is the fastest way to see why a hook did or did not fire on a specific task.

### Block Low-Context Stop Excuses

Optional `Stop`-event hook that blocks "fresh session later" / "context is full" deflections when real context usage is below 50%.

**Always on** — registered in the plugin's `hooks.json`; no `.claude/settings.json` edit needed. Disable every development hook with `DEVELOPMENT_HOOKS=0`, or just this one with its per-hook guard (see Environment Variables).

See the header of `hooks/stop-deflection-guard` for the full list of blocked phrases, configuration environment variables, and fail-open behavior.

### Environment Variables

| Variable | Default | Hook(s) | Effect |
|----------|---------|---------|--------|
| `DEVELOPMENT_ROUTING_GUARD` | `1` | model-routing gates | Set to `0` to bypass all routing enforcement for the current session |
| `DEVELOPMENT_USERGATE_GUARD` | `1` | post-task-complete-revalidate | Set to `0` to bypass per-task gate enforcement |
| `DEVELOPMENT_USERGATE_STOP_GUARD` | `1` | stop-revalidate-user-gates | Set to `0` to bypass end-of-plan gate enforcement |
| `DEVELOPMENT_BLOCKEDBY_GUARD` | `1` | pre-task-blockedby-enforce | Set to `0` to bypass blockedBy ordering checks |
| `DEVELOPMENT_DISPATCH_GUARD` | `1` | pre-agent-task-dispatch-validate | Set to `0` to bypass per-task dispatch validation |
| `DEVELOPMENT_AGENT_RETURN_GUARD` | `1` | post-agent-return-validate | Set to `0` to bypass subagent evidence checks |
| `DEVELOPMENT_PLANMODE_GUARD` | `1` | pre-enterplanmode-block | Set to `0` to allow Claude Code's native plan mode |
| `DEVELOPMENT_HOOKS` | `1` | ALL development hooks | Set to `0` to disable every development hook at once (global master switch) |
| `DEVELOPMENT_USERGATE_TRACE_LOG` | `/tmp/claude-hooks/user-gate-trace.log` | all user-gate hooks | Override trace log path |
