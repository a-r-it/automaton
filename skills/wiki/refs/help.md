Print the following help text to the user:

---

**automaton:wiki** — per-project conversation knowledge base

**Setup**
```
automaton:wiki setup                   # guided first-time bootstrap
automaton:wiki setup refresh-schemas   # re-apply plugin schema templates
automaton:wiki setup verify            # sanity-check hooks + compile dry-run
automaton:wiki setup summary           # print activation state
```
`setup` (no args) configures hooks and `.claude/wiki.json`, creates `wiki/` and `daily/` at project root.
Run once per project. Use `refresh-schemas` after plugin updates that change
`_schema.md` contents.

**Compile** — extract knowledge from captured conversations
```
automaton:wiki compile              # compile new/changed daily logs
automaton:wiki compile --all        # force recompile everything
automaton:wiki compile --dry-run    # preview what would be compiled
```

**Query** — ask the knowledge base
```
automaton:wiki query "What auth patterns do I use?"
automaton:wiki query "How does X work?" --save    # save answer into knowledge base
```

**Lint** — check knowledge base health (7 checks)
```
automaton:wiki lint           # all checks (includes LLM contradiction scan)
automaton:wiki lint --structural    # structural checks only (free, instant)
```

**Compiled knowledge:** `wiki/`  **Conversation logs:** `daily/`  (both at project root)
**Log file:** `wiki/flush.log` — check here if hooks aren't capturing

---
