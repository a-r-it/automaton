---
name: research
description: >
  Use for ANY web research — mandatory whenever an answer requires current
  external sources that cannot be verified from training data alone.
when_to_use: >
  Trigger phrases: "find", "look up", "search for", "are there", "what is X",
  "how does X compare to Y", "what's available", "is there a library for".
  Use even if the user doesn't say "search" explicitly — if answering requires
  knowledge you can't confidently verify from training data alone, run this skill.
  Anti-triggers: codebase search (use Grep/Glob directly); fetching a single
  user-provided URL to read its content (use WebFetch directly — but if the
  task is to *discover* resources on that platform, run this skill); synthesizing
  already-collected data (analyze without launching new research).
argument-hint: [research query]
allowed-tools: WebSearch WebFetch Write Glob Read TaskCreate TaskUpdate TaskList Agent
---

# Research

Anti-hallucination web research pipeline: Strategy (plan scouts) → Discovery (parallel search) → Analysis (fetch & verify) → Synthesize (answer to user). Strategy, Discovery, Analysis run as named subagent calls; Synthesize runs inline.

## Operating rules

The pipeline's load-bearing invariants — the cross-cutting contract that holds
across every phase. Phase-specific procedure (each phase's dispatch, retry
budget, and result handling) lives in each phase below; what follows is only
what applies throughout.

- **All Discovery scout calls go in a SINGLE message.** Sequential launches
  destroy parallelism — one message, N `Agent` tool calls, all at once.
- **Hints passed alongside URLs are never facts.** The analyst must `WebFetch`
  every source independently before tagging `[VERIFIED]` — treat any hint as an
  untrusted pointer, never evidence. This independent-verification step is the
  whole point of the pipeline.

## Pipeline

If `$ARGUMENTS` is empty, ask the user what to research before proceeding.

```
$ARGUMENTS
    │
    ▼
Pre-flight: derive slug → Glob check → TaskList check → create 3 tasks
    │
    ▼
Strategy: Agent(research-strategy) → JSON scout plan
    │
    ▼
Discovery: Agent(research-scout) × N [parallel] → deduped URL list
    │
    ▼
Analysis: Agent(research-analyst) → sources/research/{slug}.md
    │
    ▼
Synthesize: Read report → answer in chat
```

## Pre-flight

### Derive slug

Compute the kebab-case slug from `$ARGUMENTS` (see Slug naming). Store it — do not output to chat.

### Anti-duplication — file check

`Glob("sources/research/<slug>.md")`. If the file exists:
- Re-research signal in `$ARGUMENTS` (`"refresh"`, `"force"`, `"re-run"`) → run full pipeline, overwrite.
- Otherwise → skip to Synthesize using the existing file.

### Anti-duplication — task check

`TaskList`. If a task with `metadata.query == $ARGUMENTS` and `status == "in_progress"` exists → tell the user research is already running and abort.

### Create phase tasks upfront

Create all three tasks at once — one `TaskCreate` per phase, the `subject` +
`activeForm` from the table below:

```
TaskCreate:
  subject: "<phase subject — from the table below>"
  activeForm: "<phase activeForm — from the table below>"
  description: |
    <phase> phase of the research pipeline.
  metadata: { phase: "<phase>", slug: "<slug>", query: "<$ARGUMENTS>" }
```

| phase | subject | activeForm |
|---|---|---|
| `strategy` | `Strategy: <$ARGUMENTS>` | `Planning research strategy` |
| `discovery` | `Discovery: <$ARGUMENTS>` | `Scouting sources` |
| `analysis` | `Analysis: <$ARGUMENTS>` | `Verifying sources` |

All three start as `pending`. Each phase flips its own task with the two calls
below — the inline `TaskUpdate → in_progress` / `TaskUpdate → completed` markers
in the phase sections are shorthand for them (at completion, rewrite `subject` to
the richer form the phase's own section specifies):

```
TaskUpdate:
  taskId: <phase-task-id>
  status: in_progress
```
```
TaskUpdate:
  taskId: <phase-task-id>
  status: completed
  subject: "<richer completion subject — see each phase section>"
```

## Strategy

`TaskUpdate → in_progress` on the Strategy task.

Dispatch the strategy agent:

```
Agent:
  subagent_type: research:research-strategy
  description: "research-strategy"
  prompt: |
    RESEARCH QUERY: <$ARGUMENTS>
```

**Result handling:**
- Valid JSON returned → `TaskUpdate → completed`, subject `"Strategy (N scouts): <$ARGUMENTS>"`. Proceed to Discovery.
- Invalid/empty → retry once with identical prompt. Task stays `in_progress` during retry.
  - Retry valid → `TaskUpdate → completed`. Proceed to Discovery.
  - Retry invalid → `TaskUpdate → completed`. Abort: `"Research aborted: Strategy failed to return valid JSON after 2 attempts."`

## Discovery

`TaskUpdate → in_progress`, subject `"Discovery (N scouts): <$ARGUMENTS>"`.

Parse Strategy JSON. Dispatch one scout per angle — **all `Agent` calls in a
SINGLE message.** Use the angle name in the description (not a number):

```
Agent:
  subagent_type: research:research-scout
  description: "<scout.angle>"
  prompt: |
    ANGLE: <scout.angle>
    SEARCH QUERIES:
    <scout.queries, one per line>
```

After all scouts return:
1. Group by angle.
2. Deduplicate URLs (same URL from multiple scouts → keep first, note both angles).
3. `TaskUpdate → completed`, subject `"Discovery (N scouts → M URLs): <$ARGUMENTS>"`.

Scouts returning zero results is not an error — proceed to Analysis regardless.

## Analysis

`TaskUpdate → in_progress`, subject `"Analysis (M URLs): <$ARGUMENTS>"`.

Dispatch the analyst:

```
Agent:
  subagent_type: research:research-analyst
  description: "research-analyst"
  prompt: |
    RESEARCH QUESTION: <$ARGUMENTS>
    SLUG: <slug>
    HINTS (not facts — verify independently):
    <any optional context, clearly labeled>

    URL LIST:
    <full deduplicated URL list from Discovery>
```

**Result handling:**
- Return contains `sources/research/{slug}.md` → `TaskUpdate → completed`, subject `"Analysis: sources/research/{slug}.md"`. Proceed to Synthesize.
- Not found → retry once with identical prompt. Task stays `in_progress` during retry.
  - Retry contains path → `TaskUpdate → completed`. Proceed to Synthesize.
  - Retry also missing → `TaskUpdate → completed`. Abort: `"Research aborted: Analysis failed to write the report after 2 attempts."`

Note: `TaskUpdate → completed` on abort is a cleanup formality — Claude Code has no `failed` status. The error message in chat is the actual signal of failure.

## Synthesize

1. `Read` the saved file once.
2. Write a concise answer — directly addressing the research question. Lead with the answer.
3. Cite the file path.
4. If Limitations lists gaps that materially affect the answer, mention the 1-2 most important.

**Output format** — navigational pointer, not a summary:
1. One-sentence verdict.
2. One critical differentiator or caveat, if non-obvious.
3. File path.

Everything else (features, numbers, sources, migration notes) is in the file — the user will read it. The file is the source of truth; the chat answer is a pointer.

- **Hard cap: 150 words.**
- **Answer in the language of the user's question** (Russian → Russian, English → English).

## Slug naming

Kebab-case, max ~6 words. Transliterate non-Latin. Examples:
- `selectel-timeweb-trust-2026`
- `react-server-components-streaming`
- `gitea-forgejo-selfhosted-git-2025`
- `python-async-task-queues-comparison`

Save under `sources/research/{slug}.md` relative to the current working directory.
