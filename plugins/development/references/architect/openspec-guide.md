# OpenSpec Agent Reference Guide

Self-contained reference for agents working with OpenSpec artifacts. No external documentation needed.

---

## 1. Directory Structure

```
project-root/
└── openspec/
    ├── config.yaml              # Project config (schema, context, rules)
    ├── specs/                   # Source of truth — current system behavior
    │   ├── auth/
    │   │   └── spec.md
    │   └── payments/
    │       └── spec.md
    └── changes/                 # Proposed modifications
        ├── add-dark-mode/       # Active change
        │   ├── proposal.md
        │   ├── specs/
        │   │   └── ui/
        │   │       └── spec.md  # Delta spec
        │   ├── design.md
        │   └── tasks.md
        └── archive/             # Completed changes
            └── 2025-01-24-add-dark-mode/
```

**`openspec/specs/`** — Source of truth. Describes how the system currently behaves. Updated when changes are archived.

**`openspec/changes/<name>/`** — Active change. Contains artifacts (proposal, specs, design, tasks) for a proposed modification. Each change is self-contained.

**`openspec/changes/archive/`** — Completed changes. Preserved for audit trail with date prefix.

---

## 2. Change Lifecycle

```
create → proposal → specs → design → tasks → implement → verify → archive
```

1. **Create** — Create change folder (via CLI or mkdir).
2. **Proposal** — Capture intent, scope, and affected capabilities.
3. **Specs** — Define behavior changes as delta specs (ADDED/MODIFIED/REMOVED requirements).
4. **Design** — Document technical approach, decisions, and rationale.
5. **Tasks** — Break implementation into checkable task groups.
6. **Implement** — Work through tasks, checking them off.
7. **Verify** — Validate implementation matches artifacts.
8. **Archive** — Merge delta specs into source of truth, move change to archive.

---

## 3. Artifact Formats

### proposal.md

Captures WHY this change is needed and WHAT it affects.

```markdown
# Proposal: <Change Name>

## Why
1-2 sentences on the problem or opportunity. What problem does this solve? Why now?

## What Changes
- Bullet list of changes
- Be specific about new capabilities, modifications, or removals
- Mark breaking changes with **BREAKING**

## Capabilities

### New Capabilities
- `<kebab-case-name>`: <brief description>
  (Each creates specs/<name>/spec.md in the change folder)

### Modified Capabilities
- `<existing-name>`: <what requirement is changing>
  (Each needs a delta spec file. Check openspec/specs/ for existing names.)

## Impact
Affected code, APIs, dependencies, systems.
```

**Key rule:** The Capabilities section is the contract between proposal and specs. Each capability listed here MUST have a corresponding spec file.

### specs/\<capability\>/spec.md (Delta Specs)

Defines WHAT the system should do — behavior changes relative to current specs.

```markdown
# Delta for <Capability>

## ADDED Requirements

### Requirement: <Name>
The system SHALL <observable behavior>.

#### Scenario: <Name>
- **WHEN** <condition or action>
- **THEN** <expected outcome>
- **AND** <additional outcome> (optional)

## MODIFIED Requirements

### Requirement: <Name>
The system MUST <updated behavior>.
(Previously: <old behavior>)

#### Scenario: <Name>
- **WHEN** <condition>
- **THEN** <new expected outcome>

## REMOVED Requirements

### Requirement: <Name>
**Reason**: <why removed>
**Migration**: <what to use instead>
```

**Delta sections:**

| Section | Meaning | On Archive |
|---------|---------|------------|
| `## ADDED Requirements` | New behavior | Appended to main spec |
| `## MODIFIED Requirements` | Changed behavior | Replaces existing requirement |
| `## REMOVED Requirements` | Deprecated behavior | Deleted from main spec |
| `## RENAMED Requirements` | Name change only | FROM:/TO: format |

**Format rules:**
- Each requirement: `### Requirement: <name>` followed by description.
- Use RFC 2119 keywords: **SHALL/MUST** (absolute requirement), **SHOULD** (recommended), **MAY** (optional).
- Each scenario: `#### Scenario: <name>` with **WHEN/THEN** format.
- Scenarios MUST use exactly 4 hashtags (`####`).
- Every requirement MUST have at least one scenario.
- MODIFIED requirements: copy the ENTIRE requirement block from existing spec, then edit. Partial content loses detail at archive time.

**Spec writing principles:**
- Spec = behavior contract, NOT implementation plan.
- Describe observable behavior users or downstream systems rely on.
- Include: inputs, outputs, error conditions, external constraints.
- Avoid: class/function names, library choices, step-by-step implementation.
- Quick test: if implementation can change without changing externally visible behavior, it doesn't belong in the spec.

### design.md

Captures HOW to implement the change — technical approach and decisions.

```markdown
# Design: <Change Name>

## Context
Background, current state, constraints, stakeholders.

## Goals / Non-Goals

**Goals:**
- What this design aims to achieve

**Non-Goals:**
- What is explicitly out of scope

## Decisions

### Decision: <Name>
<Choice made> because:
- <rationale point 1>
- <rationale point 2>

**Alternatives considered:**
- <Alternative A> — rejected because <reason>
- <Alternative B> — rejected because <reason>

## Risks / Trade-offs
- [Risk] -> Mitigation
- [Trade-off] -> Accepted because <reason>

## Open Questions
- <Outstanding decisions or unknowns>
```

**What drives its depth:**
- Cross-cutting change (multiple modules) or new architectural pattern.
- New external dependency or significant data model changes.
- Security, performance, or migration complexity.
- Ambiguity that benefits from technical decisions before coding.

OpenSpec itself treats the design as optional and lets simple changes omit it. This flow does
not: every change ends at an approved design, and a simple one gets a short design rather than
none. A project schema that calls the artifact conditional is describing the document, not
deciding whether this flow authors one.

### tasks.md

Implementation checklist with trackable tasks.

```markdown
# Tasks

## File Map
- Create: `src/auth/token.ts`
- Modify: `src/auth/login.ts:45-60`
- Test: `tests/auth/token.test.ts`

## 1. <Task Group Name>
- [ ] 1.1 <Task description>
- [ ] 1.2 <Task description>

## 2. <Task Group Name>
- [ ] 2.1 <Task description>
- [ ] 2.2 <Task description>

## QA Notes

**What was implemented:**
- <summary bullets>

**Critical scenarios to test:**
- <scenarios>

**Edge cases and known limitations:**
- <limitations>

**Test targets:**
- <file paths and line ranges>
```

**Format rules:**
- Group related tasks under `##` numbered headings.
- Each task MUST be a checkbox: `- [ ] X.Y Task description`.
- Tasks should be small enough to complete in one session.
- Order tasks by dependency (what must be done first).
- File Map section at the top (not a checklist).
- QA Notes section at the end (not a checklist) — written after implementation, before verify.

---

## 4. CLI Commands Reference

Commands that agents use:

| Command | Purpose |
|---------|---------|
| `openspec new change <name>` | Create change folder. If CLI doesn't support this, create manually: `mkdir -p openspec/changes/<name>/` |
| `openspec status --change <name> --json` | Get artifact state (done/ready/blocked) |
| `openspec instructions <artifact> --change <name> --json` | Get rich instructions for an artifact |
| `openspec list` | List active changes |
| `openspec validate <name>` | Validate implementation against artifacts |
| `openspec archive <name>` | Merge delta specs into source of truth, move to archive |
| `openspec init` | Initialize OpenSpec in a project (creates openspec/ directory) |

**Status output example:**
```json
{
  "artifacts": [
    {"id": "proposal", "status": "done"},
    {"id": "specs", "status": "ready"},
    {"id": "design", "status": "ready"},
    {"id": "tasks", "status": "blocked", "missingDeps": ["specs"]}
  ]
}
```

---

## 5. Delta Specs Rules

### Writing Deltas

1. **ADDED** — New behavior. Write full requirement + scenarios.
2. **MODIFIED** — Changed behavior. Copy the ENTIRE existing requirement block from `openspec/specs/<capability>/spec.md`, paste under `## MODIFIED Requirements`, then edit. Never write partial content.
3. **REMOVED** — Deprecated behavior. Include `**Reason**` and `**Migration**` fields.
4. **RENAMED** — Name change only. Use `FROM: <old name>` / `TO: <new name>` format.

### What Happens on Archive

When `openspec archive` runs:
- ADDED requirements are appended to the main spec.
- MODIFIED requirements replace the existing requirement (matched by header text).
- REMOVED requirements are deleted from the main spec.
- The change folder moves to `openspec/changes/archive/YYYY-MM-DD-<name>/`.
- All artifacts are preserved in the archive for audit trail.

### Before Writing Deltas

Always read `openspec/specs/` first to understand:
- What capabilities already exist (use existing names for MODIFIED).
- What requirements are already defined (don't duplicate as ADDED).
- What the current behavior is (to write accurate MODIFIED content).

---

## 6. Surfaces: Roots and Stores

A **root** is a project-local `openspec/` directory resolved from the working directory. A
**store** is a standalone OpenSpec repo registered on this machine and addressed by id from
anywhere.

| Command | Purpose |
|---------|---------|
| `openspec context` | Name the resolved root for the current directory |
| `openspec store list --json` | List registered stores (id + location) |
| `openspec store setup <id> --path <folder>` | Create AND register a store (git init by default) |
| `openspec store register <path>` | Register an existing store folder |
| `openspec store unregister <id>` | Forget a registration, keep the files |
| `openspec store doctor <id>` | Check a store's registration and metadata |

**Store mode:** when a change lives in a store, pass `--store <id>` on every command that
accepts it (`new change`, `status`, `instructions`, `validate`, `templates`, `show`).
Without the flag, commands act on the root resolved from the working directory.

**Creating a missing surface** is a user-visible action — propose, get confirmation, then
run (`openspec init [path]` for a project root; `openspec store setup` for a store). After
creating, verify (`openspec context` / `openspec store doctor <id>`) and confirm the bound
schema in `openspec/config.yaml` (`schema: <name>`) — a fresh surface binds the packaged
default schema. Commands like `templates` resolve the packaged schema unless told
otherwise: pass `--schema <name>` explicitly and check the output says `Source: project`.
