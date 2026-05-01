---
type: entity
default_dir: entities
routing_signal: "Person, tool, project, or organization mentioned prominently"
required_sections: [Overview, Characteristics, Related Entities, Sources]
---

# Entity Articles

Articles about specific people, tools, projects, or organizations mentioned prominently in conversations or sources.

## Article template

````markdown
---
title: "Name"
type: entity
tags: [person|tool|project|org]
sources:
  - "{{DAILY}}/2026-04-01.md"
confidence: high
created: 2026-04-01
updated: 2026-04-01
---

# Name

## Overview

[What this entity is — 2-4 sentences]

## Characteristics

[Key traits, properties, or notable behaviors]

## Related Entities

- [[entities/related]] — relationship description

## Sources

- [[{{DAILY}}/2026-04-01.md]] — context of mention
```
````
