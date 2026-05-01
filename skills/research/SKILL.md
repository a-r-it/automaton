---
name: research
description: MANDATORY for ANY web search. Triggers on "поищи", "найди", "что есть", "есть ли", tool/library lookups, comparisons.
argument-hint: [research query]
allowed-tools: WebSearch WebFetch Write Glob Read TaskCreate TaskUpdate TaskList
---

# Research

Anti-hallucination web research pipeline. Four phases — Strategy (plan scouts) → Discovery (parallel search) → Analysis (fetch & verify) → Synthesize (answer to user). Phases 1–3 run as `Agent` calls; Phase 4 runs inline. The report is saved to disk; only a short pointer goes to chat.

## When to Use

**This skill replaces direct WebSearch calls.** Any web research goes through this pipeline.

- Tools, libraries, APIs, comparisons, pricing
- "поищи", "найди", "есть ли", "какие есть"
- When you need verified facts with sources, not guesses

## When NOT to Use

- Codebase search → use Grep / Glob directly
- Reading a single known URL → use WebFetch directly
- Pure synthesis of already-collected data → analyze without launching new research

## Pipeline

If `$ARGUMENTS` is empty, ask the user what to research before proceeding.

```
$ARGUMENTS
    │
    ▼
Pre-flight: derive slug → Glob check → TaskList check
    │
    ▼
Phase 1: Strategy → TaskCreate "Strategy: <query>" → haiku Agent → JSON scout plan → TaskUpdate completed
    │
    ▼
Phase 2: Discovery → TaskCreate "Discovery: <query>" → haiku × N → deduped URL list → TaskUpdate completed
    │
    ▼
Phase 3: Analysis → TaskCreate "Analysis: <query>" → sonnet Agent (bypassPermissions) → sources/research/{slug}.md → TaskUpdate completed
    │
    ▼
Phase 4: Synthesize (this skill, no Agent) → 1–3 paragraph answer in chat
```

## Pre-flight

Before launching any phase, execute these three steps in order.

### Derive slug

Compute the kebab-case slug from `$ARGUMENTS` using the slug naming rule (see Slug naming section at the bottom). Store it — the output file path uses this slug. Do not output the slug to chat.

### Anti-duplication — file check

`Glob("sources/research/<slug>.md")`. If the file exists:
- If `$ARGUMENTS` contains a re-research signal (`"перезапусти"`, `"refresh"`, `"force"`) → proceed with the full pipeline; the existing report will be overwritten.
- Otherwise → skip Phases 1–3 and jump directly to Phase 4 using the existing file.

### Anti-duplication — task check

`TaskList`. Scan the returned tasks for one where:
- `metadata.query` matches `$ARGUMENTS` exactly
- `status` is `"in_progress"`

If such a task exists → tell the user: "Research for this query is already running in this session." and abort. Do not launch a duplicate pipeline.

### Create all phase tasks upfront

After confirming no duplicate exists, create three tasks at once. Each task uses this description template (substitute `{phase}`):

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

| # | phase | subject | activeForm |
|---|---|---|---|
| 1 | `strategy` | `Strategy: <$ARGUMENTS>` | `Planning research strategy` |
| 2 | `discovery` | `Discovery: <$ARGUMENTS>` | `Scouting sources` |
| 3 | `analysis` | `Analysis: <$ARGUMENTS>` | `Verifying sources` |

All three start as `pending`. Each phase `TaskUpdate`s its own task as it begins and completes.

## Phase 1 — Strategy

### Task management

`TaskUpdate → in_progress` on the Strategy task created in Pre-flight.

Launch one `Agent` with `model: haiku`. No tools needed — pure reasoning. Pass the research query into the prompt below. Returns a JSON scout plan; pass it unchanged into Phase 2.

**Prompt (verbatim, substituting `$ARGUMENTS`):**

```
You are a search planner. You receive a research query and design a search strategy.

RULES:
- Analyze the query: narrow/factual, broad/comparative, or multi-faceted?
- Decide how many scouts (1-4):
  - Simple factual → 1-2
  - Broad research / comparison → 3-4
  - **Default to 2 scouts. Only go to 3-4 when the query is clearly multi-domain (e.g., comparing products, surveying an entire field). When in doubt, choose fewer.**
- For each scout, define:
  - angle: short focus description
  - queries: 2-3 concrete search queries optimized for web search
- Each scout MUST have a DISTINCT angle — no overlapping queries
- Do NOT search. Do NOT analyze. Only plan.

OUTPUT FORMAT (strict JSON, nothing else):

{
  "scouts": [
    {
      "angle": "short description of this scout's focus",
      "queries": ["search query 1", "search query 2"]
    }
  ]
}

RESEARCH QUERY: $ARGUMENTS
```

### Phase 1 result handling

After the Agent returns:

- **Returned JSON is valid** → `TaskUpdate → completed`, updating subject to `"Strategy (N scouts): <$ARGUMENTS>"` where N = `scouts.length`. Proceed to Phase 2.
- **Returned JSON is invalid or empty** → retry once with the identical prompt. Task stays `in_progress` during retry.
  - Retry returns valid JSON → `TaskUpdate → completed`, updating subject to `"Strategy (N scouts): <$ARGUMENTS>"`. Proceed to Phase 2.
  - Retry also invalid or empty → `TaskUpdate → completed`. Abort with this message to the user:
    > "Research aborted: Phase 1 (Strategy) failed to return valid JSON after 2 attempts."

## Phase 2 — Discovery

### Task management

`TaskUpdate → in_progress` on the Discovery task, updating subject to `"Discovery (N scouts): <$ARGUMENTS>"` where N = scout count from Phase 1. After all parallel scout Agents return → `TaskUpdate → completed`, updating subject to `"Discovery (N scouts → M URLs): <$ARGUMENTS>"` where M = deduplicated URL count.

Scouts returning zero results is not an error — proceed to Phase 3 with whatever URLs were collected (even an empty list).

Parse the planner's JSON. For each scout entry, launch ONE `Agent` with `model: haiku`. **All `Agent` calls MUST be in a SINGLE message** — this is critical for parallelism. Do not number scouts — use the angle name in the description (e.g., `Scout: prompt engineering`, not `Scout 1: prompt engineering`).

**Prompt (verbatim per scout, substituting `{scout.queries}` one per line and `{scout.angle}`):**

```
You are a search scout. Your ONLY job is to find URLs and snippets. Do NOT analyze, synthesize, or recommend.

RULES:
- Execute each search query below via WebSearch
- Return ONLY what WebSearch gave you in the format below
- Do NOT WebFetch anything
- Do NOT add commentary, preamble, or summary
- Do NOT invent URLs — only return what WebSearch gave you

SEARCH QUERIES:
{scout.queries, one per line}

ANGLE: {scout.angle}

OUTPUT FORMAT (strict, no deviations):

- URL: https://example.com/page
  Title: Page Title
  Snippet: Brief excerpt from search result
```

### Post-processing

After all scouts return:
1. Group results by scout angle.
2. Deduplicate identical URLs (same URL from multiple scouts → keep first occurrence with both angles noted).
3. Pass the consolidated plain-text list into Phase 3.

## Phase 3 — Analysis

### Task management

`TaskUpdate → in_progress` on the Analysis task, updating subject to `"Analysis (M URLs): <$ARGUMENTS>"` where M = URL count from Phase 2.

Launch ONE `Agent` with `model: sonnet` and `mode: "bypassPermissions"`. The mode is required because the agent needs `Write` access to save the report.

**Prompt:** Read `references/analyst-prompt.md` (in the skill directory) and use its full content as the agent prompt. Substitute the `{input_urls_and_question_and_optional_hints}` placeholder at the bottom with:
- The full URL list from Phase 2
- The original research question (`$ARGUMENTS`)
- The kebab-case slug for the output filename
- Any optional priority hints (clearly labeled as HINTS, not facts)

### Phase 3 result handling

After the Agent returns:

- **Return contains `sources/research/{slug}.md`** (anywhere in the text) → `TaskUpdate → completed`, updating subject to `"Analysis: sources/research/{slug}.md"`. Proceed to Phase 4.
- **`sources/research/{slug}.md` not found in return** → retry once with the identical prompt and the same URL list. Task stays `in_progress` during retry.
  - Retry return contains `sources/research/{slug}.md` → `TaskUpdate → completed`, updating subject to `"Analysis: sources/research/{slug}.md"`. Proceed to Phase 4.
  - Retry also lacks `sources/research/{slug}.md` → `TaskUpdate → completed`. Abort with this message to the user:
    > "Research aborted: Phase 3 (Analysis) failed to write the report after 2 attempts."

Note: `TaskUpdate → completed` on abort is a cleanup formality — Claude Code has no `failed` status. The error message in chat is the actual signal of failure.

## Phase 4 — Synthesize for user

After the verifier returns:

1. **Read the saved file once** via the Read tool.
2. **Write a concise answer to the user** — 1-3 paragraphs, directly addressing the research question. Lead with the answer, not the methodology.
3. **Cite the file path** so the user can read the full report if they want depth.
4. If "Limitations" lists gaps that materially affect the answer, mention the most important 1-2 in a single sentence.

### Output format

Write a navigational pointer, not a summary. Structure:
1. One-sentence verdict — the answer to the question.
2. One critical differentiator or caveat, if something non-obvious surfaced.
3. File path.

Everything else (features, numbers, sources, migration notes) is in the file — the user will read it. The file is the source of truth; the chat answer is a pointer.

- **Hard cap: 150 words.** Count before writing.
- **Answer in the language of the user's question** (Russian → Russian, English → English).

## Slug naming

Use kebab-case summary of the research query, max ~6 words. For non-Latin queries, transliterate or translate key terms. Examples:
- `selectel-timeweb-trust-2026`
- `vk-tunnel-bypass-strategies-2026`
- `amnezia-managed-vpn-whitelist-bypass-2026`
- `react-server-components-streaming`
- `gitea-forgejo-selfhosted-git-2025`  ← from Russian "поищи сравнение Gitea и Forgejo..."

Save under `sources/research/{slug}.md` relative to the current project working directory.
