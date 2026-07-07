<!--
Change protocol: L1 = wording only, L2 = structure change (test with compile), L3 = schema/routing change (full regression pass required).
-->
# Librarian — Wiki Compile Schema

## Architecture

### `{{DAILY}}/` — conversation log format

```
{{DAILY}}/
├── 2026-04-01.md
├── 2026-04-02.md
├── ...
```

Each file follows this format:

```markdown
# Daily Log: YYYY-MM-DD

## Sessions

### Session (HH:MM) - Brief Title

**Context:** What the user was working on.

**Key Exchanges:**
- User asked about X, assistant explained Y
- Decided to use Z approach because...
- Discovered that W doesn't work when...

**Decisions Made:**
- Chose library X over Y because...
- Architecture: went with pattern Z

**Lessons Learned:**
- Always do X before Y to avoid...
- The gotcha with Z is that...

**Action Items:**
- [ ] Follow up on X
- [ ] Refactor Y when time permits
```

### `{{WIKI}}/` — compiled output layout

```
{{WIKI}}/
  index.md           global catalog: all articles grouped by directory
  log.md             append-only operation log
  state.json         SHA-256 hashes for dedup
  flush.log          background process logs
  concepts/
    index.md
    *.md
  connections/
    index.md
    *.md
  entities/          people, tools, projects, organizations
    index.md
    *.md
  syntheses/         comparisons, cross-cutting analyses
    index.md
    *.md
  decisions/         architecture and product decisions
    index.md
    _schema.md
    *.md
  qa/
    index.md
    *.md
  <custom>/
    index.md
    _schema.md
    *.md
```

## Index Format

### Global `{{WIKI}}/index.md` — Articles Grouped by Directory

```markdown
# Wiki Index

## concepts/ (N articles)
| Article | Summary | Tags | Updated |
|---------|---------|------|---------|
| [[concepts/supabase-auth]] | Row-level security patterns and JWT gotchas | auth, supabase | 2026-04-02 |

## connections/ (N articles)
| Article | Summary | Tags | Updated |
|---------|---------|------|---------|
| [[connections/auth-and-webhooks]] | Token verification shared across auth and webhooks | auth, webhooks | 2026-04-04 |

## entities/ (N articles)
| Article | Summary | Tags | Updated |
|---------|---------|------|---------|
| [[entities/supabase]] | Postgres-based backend-as-a-service platform | tool, backend | 2026-04-02 |
```

Each directory gets its own `## <dir>/ (N articles)` section with a table. Articles inside the section use the same four columns: Article, Summary, Tags, Updated.

### Sub-Index `<dir>/index.md` — Same Table Format

Each directory has its own `index.md` in the same table format, listing only that directory's articles.

```markdown
# concepts/ Index

| Article | Summary | Tags | Updated |
|---------|---------|------|---------|
| [[concepts/supabase-auth]] | Row-level security patterns and JWT gotchas | auth, supabase | 2026-04-02 |
```

### Index Update Protocol (MANDATORY after every write)

After writing or updating any article file, execute these steps in order — every time, no exceptions:

1. Write or update the article file
2. Update `<dir>/index.md` — add a new row or update the existing row for this article
3. Update `{{WIKI}}/index.md` — add or update the article's row in the matching `## <dir>/` section; update the article count in the section header
4. Append to `{{WIKI}}/log.md`

## Frontmatter

All articles use this frontmatter schema:

```yaml
---
title: "..."
type: concept | connection | entity | synthesis | decision | qa | <custom>
tags: [tag1, tag2]
sources: ["{{DAILY}}/2026-04-15.md"]
confidence: high | medium | low
created: 2026-04-15
updated: 2026-04-15
---
```

**Confidence levels:**
- `high` — multiple corroborating sources, concrete examples
- `medium` — supported but limited examples or single source
- `low` — single mention, anecdotal, or speculative

**Optional fields:**

- `orphaned: true` — set by the compile-agent when **every** path in
  `sources:` is missing from disk. Cleared automatically on recompile
  when at least one source path exists. Lint reports but never mutates.
- `truncated: true` — set by the compile-agent when any contributing
  daily-log session carries a `**Truncated:** true` marker (written by
  `flush.py` when invoked from the PreCompact hook). Cleared automatically
  on recompile when no contributing section is marked. Indicates the
  article was compiled from a transcript tail that was about to be
  auto-compacted and may not reflect the full conversation.

## Content Routing Rules

Route by content signal, not source type:

{{ROUTING_TABLE}}

{{TIEBREAKERS}}

## Required Sections by Type

Used by the lint tool to validate article completeness:

{{REQUIRED_SECTIONS_TABLE}}

## Article Formats

{{ARTICLE_FORMATS}}

## Source Type Compilation Instructions

### Handling truncation and orphan state

When you write or update an article, set the optional `orphaned` and
`truncated` fields based on the current state of its sources (see
Frontmatter → Optional fields). These are your responsibility — lint
will not touch them, and no auto-fix script mutates them.

- `orphaned`: verify every path listed in `sources:` against the
  filesystem. If all are missing, set `orphaned: true`; if at least one
  exists, omit the field (or set it to `false`).
- `truncated`: for each daily log in `sources:`, inspect only the session
  sections that fed this article. If any such section starts with a
  `**Truncated:** true` line under its `### Session (HH:MM)` heading,
  set `truncated: true`; otherwise omit.

### When compiling a `{{DAILY}}/` file

1. Read the daily log file
2. Read `{{WIKI}}/index.md` to understand the current knowledge state
3. Read existing articles that may need updating
4. For each piece of knowledge found in the log:
   - Determine the type using Content Routing Rules above
   - If an existing article of that type covers this topic: UPDATE it, add the daily log as a source
   - If it's a new topic: CREATE a new article in the appropriate directory
5. If the log reveals a non-obvious connection between 2+ existing concepts: CREATE a `connections/` article
6. Follow the Index Update Protocol after every write
7. APPEND to `{{WIKI}}/log.md`

**Guidelines:**
- A single daily log may touch 3-10 knowledge articles
- Prefer updating existing articles over creating near-duplicates
- Write in encyclopedia style — factual, concise, self-contained
- Every article must have YAML frontmatter

### When compiling a `{{SOURCES}}/` file

1. Read the source file in full
2. Read `{{WIKI}}/index.md` to identify existing articles that may be enriched
3. The source file is a reference document (article, paper, repo README, doc page) — do not modify it
4. For each key insight or piece of knowledge in the source:
   - Determine the type using Content Routing Rules above
   - If a relevant existing article exists: UPDATE it with the new insight, add the source file path to `sources:`
   - If it's a new topic: CREATE a new article in the appropriate directory
5. For comparisons or trade-offs in the source: CREATE or update a `syntheses/` article
6. Link the source file path (e.g., `{{SOURCES}}/2026-04-15-supabase-docs.md`) in each article's `sources:` frontmatter
7. Follow the Index Update Protocol after every write

## Conventions

- **Wikilinks:** Use Obsidian-style `[[path/to/article]]` without `.md` extension. Full path from `{{WIKI}}/` is required (e.g., `[[concepts/slug]]`, not `[[slug]]`).
- **Writing style:** Encyclopedia-style, factual, third-person where appropriate
- **Dates:** ISO 8601 (YYYY-MM-DD for dates, full ISO for timestamps in log.md)
- **File naming:** lowercase, hyphens for spaces (e.g., `supabase-row-level-security.md`)
- **Frontmatter:** Every article must have YAML frontmatter with at minimum: title, type, sources, confidence, created, updated
- **Sources:** Always link back to the `{{DAILY}}/` log(s) or `{{SOURCES}}/` file(s) that contributed to an article
