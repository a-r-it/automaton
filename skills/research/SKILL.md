---
name: research
description: >
  Use this skill for ANY web research — mandatory whenever an answer requires
  current external sources that cannot be verified from training data alone.
  Anti-hallucination pipeline: scouts find URLs, analyst WebFetches and tags
  [VERIFIED]/[UNCERTAIN], report saved to disk.
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
allowed-tools: WebSearch WebFetch Write Glob Read TaskCreate TaskUpdate TaskList
---

# Research

Anti-hallucination web research pipeline: Strategy (plan scouts) → Discovery (parallel search) → Analysis (fetch & verify) → Synthesize (answer to user). Strategy, Discovery, Analysis run as named subagent calls; Synthesize runs inline.

## Gotchas

- **All Discovery scout calls must be in a SINGLE message** — sequential launches destroy parallelism. One message, N Agent tool calls, all at once.
- **Hints passed alongside URLs are NOT facts** — the analyst must WebFetch independently before tagging `[VERIFIED]`. This is the whole point of the pipeline.

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

Create three tasks at once. Template (substitute `{phase}`):

```
Phase of research pipeline.

```json:metadata
{
  "phase": "{phase}",
  "slug": "<slug>",
  "query": "<$ARGUMENTS>"
}
```
```

| phase | subject | activeForm |
|---|---|---|
| `strategy` | `Strategy: <$ARGUMENTS>` | `Planning research strategy` |
| `discovery` | `Discovery: <$ARGUMENTS>` | `Scouting sources` |
| `analysis` | `Analysis: <$ARGUMENTS>` | `Verifying sources` |

All three start as `pending`. Each phase `TaskUpdate`s its own task as it begins and completes.

## Strategy

`TaskUpdate → in_progress` on the Strategy task.

Launch `Agent(subagent_type: "automaton:research-strategy")` with the research query as the prompt:

```
RESEARCH QUERY: <$ARGUMENTS>
```

**Result handling:**
- Valid JSON returned → `TaskUpdate → completed`, subject `"Strategy (N scouts): <$ARGUMENTS>"`. Proceed to Discovery.
- Invalid/empty → retry once with identical prompt. Task stays `in_progress` during retry.
  - Retry valid → `TaskUpdate → completed`. Proceed to Discovery.
  - Retry invalid → `TaskUpdate → completed`. Abort: `"Research aborted: Strategy failed to return valid JSON after 2 attempts."`

## Discovery

`TaskUpdate → in_progress`, subject `"Discovery (N scouts): <$ARGUMENTS>"`.

Parse Strategy JSON. For each scout, launch `Agent(subagent_type: "automaton:research-scout")`. **All calls in a SINGLE message.** Use the angle name in the description (not a number).

Prompt per scout:
```
ANGLE: {scout.angle}
SEARCH QUERIES:
{scout.queries, one per line}
```

After all scouts return:
1. Group by angle.
2. Deduplicate URLs (same URL from multiple scouts → keep first, note both angles).
3. `TaskUpdate → completed`, subject `"Discovery (N scouts → M URLs): <$ARGUMENTS>"`.

Scouts returning zero results is not an error — proceed to Analysis regardless.

## Analysis

`TaskUpdate → in_progress`, subject `"Analysis (M URLs): <$ARGUMENTS>"`.

Launch `Agent(subagent_type: "automaton:research-analyst")` with:

```
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
