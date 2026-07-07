# automaton

A Claude Code **marketplace** named `automaton` that ships three plugins:

- **research** (`research:`) — structured web research workflow
- **mnemic** (`mnemic:`) — per-project knowledge base that captures Claude Code conversations into typed wiki articles; queryable and compounds over time
- **development** (`development:`) — OpenSpec / dev-workflow toolkit: brainstorming, planning, TDD, debugging, code review, gates

## Requirements

- [uv](https://docs.astral.sh/uv/) — Python package manager (install once globally; required by `mnemic`)
- Python 3.12+ (for `mnemic`)

## Install

```bash
# Step 1: register the marketplace
claude plugin marketplace add a-r-it/automaton

# Step 2: install the plugin(s) you want
claude plugin install research@automaton
claude plugin install mnemic@automaton
claude plugin install development@automaton
```

Reload plugins in your current session with `/reload-plugins`, or start a new session.

## Quick start

```
mnemic:wiki setup    # first-time setup per project; creates wiki/, daily/, sources/ and enables capture hooks
mnemic:wiki help     # all wiki commands

research:research "what are the best practices for X in 2025"
```

## Sources & inspiration

- [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) (coleam00)
- [Karpathy LLM wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [atomicmemory-llm-wiki-compiler](https://github.com/atomicmemory/llm-wiki-compiler)
- [Pratiyush llm-wiki](https://github.com/Pratiyush/llm-wiki)
- [tonbistudio llm-wiki](https://github.com/tonbistudio/llm-wiki)
- [OmegaWiki](https://github.com/skyllwt/OmegaWiki) (skyllwt)
