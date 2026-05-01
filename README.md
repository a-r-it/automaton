# automaton

Claude Code skill pack for automated development.

## Requirements

- [uv](https://docs.astral.sh/uv/) — Python package manager (install once globally)
- Python 3.12+

## Skills

- **wiki** — captures Claude Code conversations into typed wiki articles; queryable knowledge base that compounds over time
- **research** — structured web research workflow

## Install

```
claude plugin install gh:a-r-it/automaton
```

Reload plugins in your current session with `/reload-plugins`, or start a new session.

## Quick start

```
automaton:wiki setup    # first-time setup per project; creates wiki/, daily/, sources/ and enables capture hooks
automaton:wiki help     # all wiki commands

automaton:research "what are the best practices for X in 2025"
```

## Sources & inspiration

- [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) (coleam00)
- [Karpathy LLM wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [atomicmemory-llm-wiki-compiler](https://github.com/atomicmemory/llm-wiki-compiler)
- [Pratiyush llm-wiki](https://github.com/Pratiyush/llm-wiki)
- [tonbistudio llm-wiki](https://github.com/tonbistudio/llm-wiki)
- [OmegaWiki](https://github.com/skyllwt/OmegaWiki) (skyllwt)
