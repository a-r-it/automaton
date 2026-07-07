---
type: concept
default_dir: concepts
routing_signal: "Technical concept, pattern, framework, how-to"
required_sections: [Key Points, Details, Related Concepts, Sources]
tiebreaker: "If content explains what X is, it's a concept (vs decision which records a choice between options)."
---

# Concept Articles

One article per atomic piece of knowledge. These are facts, patterns, decisions, preferences, and lessons extracted from your conversations.

## Article template

````markdown
---
title: "Concept Name"
type: concept
tags: [domain, topic]
sources:
  - "{{DAILY}}/2026-04-01.md"
  - "{{DAILY}}/2026-04-03.md"
confidence: high
created: 2026-04-01
updated: 2026-04-03
---

# Concept Name

[2-4 sentence core explanation]

## Key Points

- [Bullet points, each self-contained]

## Details

[Deeper explanation, encyclopedia-style paragraphs]

## Related Concepts

- [[concepts/related-concept]] — How it connects

## Sources

- [[{{DAILY}}/2026-04-01.md]] — Initial discovery during project setup
- [[{{DAILY}}/2026-04-03.md]] — Updated after debugging session
```
````
