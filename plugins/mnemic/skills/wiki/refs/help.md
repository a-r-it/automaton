Print the following help text to the user:

---

**mnemic:wiki** — per-project conversation knowledge base

**Setup**
```
mnemic:wiki setup                   # guided first-time bootstrap
mnemic:wiki setup refresh-schemas   # re-apply plugin schema templates
mnemic:wiki setup verify            # sanity-check hooks + compile dry-run
mnemic:wiki setup summary           # print activation state
```
`setup` (no args) configures hooks and `.automaton/mnemic/config.toml`, creates `wiki/` and `daily/` at project root.
Run once per project. Use `refresh-schemas` after plugin updates that change
`_schema.md` contents.

**Compile** — extract knowledge from captured conversations
```
mnemic:wiki compile              # compile new/changed daily logs
mnemic:wiki compile --all        # force recompile everything
mnemic:wiki compile --dry-run    # preview what would be compiled
```

**Query** — ask the knowledge base
```
mnemic:wiki query "What auth patterns do I use?"
mnemic:wiki query "How does X work?" --save    # save answer into knowledge base
```

**Lint** — check knowledge base health (7 checks)
```
mnemic:wiki lint           # all checks (includes LLM contradiction scan)
mnemic:wiki lint --structural    # structural checks only (free, instant)
```

**Compiled knowledge:** `wiki/`  **Conversation logs:** `daily/`  (both at project root)
**Log file:** `wiki/flush.log` — check here if hooks aren't capturing

---
