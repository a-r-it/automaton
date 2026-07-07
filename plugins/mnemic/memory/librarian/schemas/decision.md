---
type: decision
default_dir: decisions
routing_signal: "Decision made with rationale (chose X over Y)"
required_sections: [Context, Decision, Alternatives, Consequences / Risks]
tiebreaker: "If content says 'we decided to use X', it's a decision (vs concept which explains what X is)."
---

# Decision Articles

Recorded decisions with rationale. Captures what was chosen, what alternatives were considered, and what consequences follow.

## Article template

````markdown
---
title: "Decision: ..."
type: decision
tags: [architecture|product|...]
sources:
  - "{{DAILY}}/2026-04-06.md"
confidence: high
created: 2026-04-06
updated: 2026-04-06
---

# Decision: ...

## Context

[Situation, constraints, problem being solved]

## Decision

[What was chosen]

## Alternatives

[What was considered but not chosen, and why not]

## Consequences / Risks

[What this means going forward, risks to watch]
```
````
