---
name: writing-tests
description: >
  Writes unit tests for code that already exists — never touches production code.
when_to_use: >
  Trigger phrases: "write unit tests for X", "add tests to this module", "cover this class
  with tests". Also fires when the user asks for coverage of code that already works.
  Anti-triggers: test-first TDD on NEW behavior (use test-driven-development); diagnosing a
  failing test (use systematic-debugging); integration/e2e tests — this flow is unit-only.
argument-hint: [scope — module, class, or file]
---

# Writing tests — unit-test authoring

Scope in → committed green unit-test suite out, production code untouched. You are the
orchestrator: three subagents do all design and coding; you write nothing but the final
report and your bookkeeping under `.automaton/development/tests/<slug>/`.

The subagents — `development:test-scenario-designer` (GWT scenarios),
`development:test-scenario-critic` (read-only validation), and a stack-matched implementer
(`development:<stack>-test-implementer`, scenarios → tests) — never see each other's output
directly: every cross-agent fact travels through your briefs (critic findings → next designer
brief; confirmed-bug ids + active scenarios → implementer brief).

## Operating rules

- **Only test files change, and only test files are committed.** PROD-LOCK verifies this by
  content, not by anyone's word. Bookkeeping under `.automaton/development/tests/<slug>/` is
  never committed.
- **Never commit red.**
- **Never stop to ask the user — never call AskUserQuestion.** The scope named at invocation
  is the only user input this flow gets. Decide every fork yourself and record the decision;
  anything unresolvable is a park, a drop, or a Stop with a report — not a question.

## The graph as your task list

Before anything else, lay the graph out as tasks. The list, not your memory, is where the
current stage lives. Never invent a stage — the graph is the list.

One call per stage, in graph order:

```
TaskCreate:
  subject: "<stage name, verbatim from the graph>"
  description: |
    **Goal:** <one sentence — what leaving this stage produces, not how>
    **Work:** <one or two sentences, plain words — what actually happens in this
    stage: what gets read, decided, dispatched, or written, and by whom>
```

Chain them so none can be entered before the one it follows:

```
TaskUpdate:
  taskId: <task-id>
  addBlockedBy: [<task id of the preceding stage>]
```

On entering a stage, mark it `in_progress`; on taking an edge out, mark it `completed` — the
transition and the update are one act. A back edge returns you to a stage you already
completed: reopen that task (`in_progress`), never create a second one. Call `TaskList`
whenever you are unsure where you stand.

## Stages and transitions

Before every transition, announce `Transition: <current> → <next> (<reason>)`, verify the
edge is listed here, and quote the exact edge entry you are using. All transitions not
listed are FORBIDDEN.

```
Baseline  → Discovery [scope's existing tests green]
Baseline  → Stop      [scope's tests red: report, write nothing]
Discovery → Design    [scope→<slug>; test layout noted; in-scope production hashed]
Design    → Critique  [scenarios written or revised]
Critique  → Design    [Changes required or NEEDS_CONTEXT, and design rounds < 3]
Critique  → Route     [Approved / Approved with issues — or 3 rounds reached: exclude the still-flagged from the active set, log them parked, proceed]
Route     → Implement [an implementer agent for the detected stack exists]
Route     → Stop      [no implementer for the stack: hand back the approved scenario doc]
Implement → Verify    [implementer returned]
Verify    → Implement [reds to fix (test defect), reds to drop at the bound, or production to restore-and-re-dispatch]
Verify    → Design    [an enabled test is red but faithful — actual ≠ the scenario's asserted value: the scenario is wrong / a missed bug — re-examine it once]
Verify    → Stop      [production changed and cannot be safely restored (file was dirty at Discovery): report files + hashes, write nothing more]
Verify    → Commit    [completeness gate passes]
```

Entry: Baseline. Exit: Commit (success). Stop is the terminal for the early exits and the
unrestorable-production abort.

Guardrails:
- Editing a file, running a tool, or dispatching a subagent does not itself change the current
  stage.
- The two diagnostic loops are bounded: Design↔Critique ≤ 3 rounds, Implement↔Verify ≤ 3 fix
  rounds. At a bound, resolve rather than loop — park, drop, or restore (mechanics live in the
  edge guards and stages); a resolution does not extend the fix-round budget.
- A `Verify → Design` re-examination fires at most once per scenario; a scenario still red after
  it is dropped, not looped again.
- Never leave Verify toward Commit with red, with a production change, or with an active
  scenario that has no test case (see the completeness gate).
- A user decision to abort overrides the graph; nothing else does.

## Per-stage guidance

Tool how-to, never a second source of structural truth. Which edge to take is the section
above's business.

**Baseline.** A "green after" signal is worthless unless it was green before — you could not
tell your own regression from a pre-existing one — and you may not touch production to repair a
red baseline anyway. Run the existing tests **for the scope of the work** (the module or
package under test), not the whole project — a failure in unrelated code elsewhere is not your
baseline and must not block you:

```
Bash:
  command: <the project's scope-narrowed test command>
```

All green → `Baseline → Discovery`. Any red → `Baseline → Stop`: report the failing tests,
write nothing.

**Discovery.**

- Resolve the scope the user named (a module, class, file, or feature). If none was given, pick
  a coherent scope and proceed. Derive `<slug>` (kebab-case: `Cart` →
  `cart`; `:payments` → `payments`).
- Note where the scope's test sources live — Verify validates the implementer's reported paths
  against this. The stack and test libraries are the designer's to detect and record, not yours.
- **Find the existing tests** already covering the scope (their paths and contents). You hand
  these to the designer and critic so the flow adds *incremental* value, not coverage the repo
  already has.
- **Hash production (PROD-LOCK, part 1).** Record the content hash of every in-scope
  production file into `.automaton/development/tests/<slug>/prod-hashes.txt` (one
  `<hash>  <path>` line each). No copies are made — the project's version control already
  holds the committed state; the hash is your tamper detector. For each file also note
  whether it carries uncommitted local changes right now: a dirty file cannot be safely
  auto-restored later.

**Design.** Scenarios are the language-neutral contract, at
`.automaton/development/tests/<slug>/scenarios.md`. Dispatch the designer (first pass, or a fix
pass carrying the critic's findings):

```
Agent:
  subagent_type: development:test-scenario-designer
  description: "writing-tests — design scenarios for <slug>"
  prompt: |
    You are designing unit-test scenarios for: <scope> (slug: <slug>)

    ## Target code
    [FULL source of the unit(s) under test — paste it]

    ## Existing tests for this scope
    [paths + contents of tests already covering this code, or "none" — do not re-cover these]

    ## Context
    Test sources: [location]
    Write the GWT scenarios to: .automaton/development/tests/<slug>/scenarios.md

    ## Review findings        (fix pass only — omit on the first pass)
    [the findings verbatim]

    ## Before You Begin
    If the pasted context is not enough, return NEEDS_CONTEXT naming exactly what you need.

    ## Your Job
    1. Design GWT scenarios — one per intended test case. On a fix pass: cut the useless, add
       the missing, fix the inaccurate, keep ids.
    2. Detect the stack and test libraries (with versions) from the build files; record
       `stack`, `libraries`, and `target` at the top; use stable S<n> ids.
    3. Return the completion report.

    Work from: <project directory>
```

On its return, `Design → Critique`.

**Critique.** Fresh eyes judge the scenarios against the real code. Dispatch the critic:

```
Agent:
  subagent_type: development:test-scenario-critic
  description: "writing-tests — validate scenarios for <slug>"
  prompt: |
    You are validating unit-test scenarios for: <slug>

    ## Scenarios to validate
    [FULL contents of scenarios.md]

    ## Target code
    [FULL source of the unit(s)]

    ## Existing tests for this scope
    [paths + contents, or "none" — flag any scenario that duplicates existing coverage]

    ## Your Job
    Judge across the five dimensions; return the verdict.

    Work from: <project directory>
```

- `Changes required` / `NEEDS_CONTEXT`, rounds remaining → `Critique → Design`, the findings
  folded into the next designer brief.
- 3 rounds without approval → `Critique → Route` anyway, on that edge's guard.

**Route.** Match the stack recorded in the scenario doc against the available
`development:<stack>-test-implementer` agents. A match → `Route → Implement`. No implementer
for the stack → `Route → Stop`: the approved scenario doc is the deliverable; name the
implementers that do exist.

**Implement.** Dispatch the implementer. Pass only the **active** scenario blocks, the
confirmed-bug ids, and the project's test conventions:

```
Agent:
  subagent_type: <the stack's implementer agent>
  description: "writing-tests — implement tests for <slug>"
  prompt: |
    You are implementing unit tests from these approved scenarios.

    ## Active scenarios to implement    (render ONLY these — ignore anything under ## Parked)
    [the active `#### Scenario:` blocks, verbatim]

    ## Confirmed bugs
    [ids from your confirmed-bug list — scenarios that survived a Verify → Design re-examination
    with the contract upheld. Disable a scenario as a bug-marker ONLY if its id is here; on the
    first pass this list is empty]

    ## Target code
    [FULL source of the unit(s)]

    ## Context
    Stack & libraries: [the scenario doc's `stack` and `libraries` lines, verbatim]
    Test-source location + the project's existing test conventions: [...]

    ## Your Job
    1. Render each active scenario as a test case; never touch production code — only test files.
    2. Run the tests you wrote; report pass/fail and every file you touched.

    Work from: <project directory>
```

On its return, `Implement → Verify`.

**Verify.** Run the checks; the edge you take is the first that applies.

- **PROD-LOCK, part 2.** Re-hash every in-scope production file against `prod-hashes.txt`, and
  confirm every path in the implementer's "Files changed" is under the project's test sources.
  Production changed → for each changed file that was **clean** at Discovery, restore it to its
  pre-flow state through the project's version control, re-hash to confirm it matches the
  recorded hash again, then `Verify → Implement` with a sharpened warning. A changed file that
  was **dirty** at Discovery cannot be restored without destroying the user's uncommitted
  work — do not touch it: `Verify → Stop`, reporting the exact files and hashes so the user
  can revert deliberately. If a violation repeats after the warning, keep only the test-file
  changes and record the violation.
- **Green.** Run the scope's test command. For each red, take the edge that fits its cause:
  - the implementer's rendering is at fault (wrong assertion or setup vs the scenario), fix
    rounds remaining → `Verify → Implement` to fix the test;
  - the rendering is faithful, but the code's actual output differs from the scenario's asserted
    value → the scenario is wrong — a miss, possibly a bug the analysis missed → `Verify →
    Design` once: the designer corrects the expected value, or upholds it because the actual
    output contradicts the contract — an upheld scenario is a **confirmed bug**: add its id to
    your confirmed-bug list, and on re-implementation it renders as a disabled bug-marker;
  - reds still failing at the fix-round bound → `Verify → Implement` once more to remove exactly
    those tests (a drop, not a fix — recorded in your report).
- **Completeness gate** (all green + production untouched) → check, before Commit:
  - every **active** scenario maps to exactly one test case (enabled, or a confirmed-bug
    disabled marker, or explicitly dropped with a recorded reason);
  - the tests actually **compiled and were discovered** — not a no-source or unexpected
    zero-test run;
  - the scope regression command was actually executed, not skipped.
  All satisfied → `Verify → Commit`. A hole here is not "green" — treat it as a red and route
  to `Implement` or re-dispatch with the missing context.

**Commit.** Commit **only the test files** (the paths from the implementer's report, validated
as under the test sources) through the project's version control, with a clear message, e.g.
`test(<slug>): add unit tests from GWT scenarios`. Delete `prod-hashes.txt` — its job is done;
of the bookkeeping only `scenarios.md` outlives the run. Then print a short report:
scenarios designed / approved / parked, tests written / dropped / disabled as bug-markers,
bugs revealed, final green count, the commit id, and anything the user should look at.
