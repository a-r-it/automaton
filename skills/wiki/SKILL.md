---
name: wiki
description: >-
  Per-project knowledge base that compiles Claude conversations into typed wiki articles.
  Trigger: user says compile, query, lint, ingest, or setup; user asks to search the wiki
  or knowledge base; user references a past decision or lesson; user wants to save an answer
  permanently. Anti-triggers: general code questions unrelated to knowledge management;
  research skill tasks. Commands: setup (activate in project), compile (daily/+sources/ to
  wiki/), query <question> [--save], lint [--structural], ingest <file>. Typed pages: concept,
  connection, entity, synthesis, decision, qa. Custom dirs via _schema.md. Hierarchical
  indexes: wiki/index.md (global) plus per-directory index.md (sub-index).
user-invocable: true
allowed-tools: Bash, AskUserQuestion, TaskCreate, TaskUpdate
argument-hint: "setup [refresh-schemas|verify|summary] | compile [--all] [--dry-run] | query <question> [--save] | lint [--structural] | ingest <file> | hooks [enable|disable|status] | render-prompt [--plugin-defaults] | help"
paths:
  - skills/wiki/refs/setup.md
  - skills/wiki/refs/compile.md
  - skills/wiki/refs/query.md
  - skills/wiki/refs/lint.md
  - skills/wiki/refs/ingest.md
  - skills/wiki/refs/hooks.md
  - skills/wiki/refs/render-prompt.md
  - skills/wiki/refs/help.md
---

# Wiki Skill

You are executing a wiki command. Follow the instructions in the
corresponding reference file already loaded into your context:

- `setup`   → refs/setup.md
- `compile` → refs/compile.md
- `query`   → refs/query.md
- `lint`    → refs/lint.md
- `ingest`  → refs/ingest.md
- `hooks`         → refs/hooks.md
- `render-prompt` → refs/render-prompt.md
- `help`          → refs/help.md

Unknown argument: tell the user
> Unknown command. Run `automaton:wiki help` to see available commands.
