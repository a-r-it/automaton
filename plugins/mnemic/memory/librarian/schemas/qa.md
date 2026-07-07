---
type: qa
default_dir: qa
routing_signal: "Specific question answered and saved"
required_sections: [Answer, Sources Consulted, Follow-Up Questions]
---

# Q&A Articles

Filed answers from queries. Every complex question answered by the system can be permanently stored, making future queries smarter.

## Article template

````markdown
---
title: "Q: Original Question"
type: qa
question: "The exact question asked"
consulted:
  - "concepts/article-1"
  - "concepts/article-2"
confidence: medium
filed: 2026-04-05
created: 2026-04-05
updated: 2026-04-05
---

# Q: Original Question

## Answer

[The synthesized answer with [[wikilinks]] to sources]

## Sources Consulted

- [[concepts/article-1]] — Relevant because...
- [[concepts/article-2]] — Provided context on...

## Follow-Up Questions

- What about edge case X?
- How does this change if Y?
```
````
