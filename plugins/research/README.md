# research plugin

Structured web-research workflows for Claude Code: the `research:research`
skill (general web research with scout/analyst agents) and the
`research:business-research` skill (multi-agent business research producing
a verified HTML report).

## Requirements

- **Python ≥ 3.13** on `PATH` as `python3` — the business-research
  validation and rendering scripts (`plugins/research/scripts/`) use 3.13
  features and are invoked with the system `python3`; no packages are
  required (stdlib only) and nothing is installed.

Part of the [automaton](../../README.md) marketplace.
