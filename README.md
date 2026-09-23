# automaton

A Claude Code **marketplace** named `automaton` that ships two plugins:

- **research** (`research:`) — structured web research: the `research:research` skill (scout/analyst agents) plus `research:business-research`, a multi-analyst business panel that produces a single self-contained, source-verified HTML report
- **development** (`development:`) — OpenSpec / dev-workflow toolkit: brainstorming, planning, TDD, debugging, code review, gates

## Requirements

- Python 3.13+ on `PATH` as `python3` for `research`'s business-research scripts (stdlib only — nothing installed)

## Install

```bash
# Step 1: register the marketplace
claude plugin marketplace add a-r-it/automaton

# Step 2: install the plugin(s) you want
claude plugin install research@automaton
claude plugin install development@automaton
```

Reload plugins in your current session with `/reload-plugins`, or start a new session.

## Quick start

```
research:research "what are the best practices for X in 2025"
research:business-research "is it worth building a PDF spell-check Telegram bot"
```

