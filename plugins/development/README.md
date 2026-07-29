# development

A **Claude-Code-only** development workflow: design → plan → TDD → review → ship, with the
discipline enforced by the harness rather than volunteered by the model.

After installing, run `/onboard` — it walks through the optional features one question at a time
and writes the configuration for you.

## Requirements

Nothing below is bundled.

| Needed for | Requirement |
|---|---|
| `/system-design` | The **OpenSpec CLI** on `PATH` (developed against **1.6.0**). Without it the architect stops at its first command. The command also launches with `worktree.bgIsolation` forced to `none`, which outranks whatever the project's `.claude/settings.json` says — its artifacts exist to be read and approved in your own tree. |
| Any hook | `bash`, `jq`, `sed`. A missing `jq` makes a hook **fail open** — it passes silently instead of enforcing. On Windows without bash, `run-hook.cmd` exits successfully having run nothing. |
| Model routing | `python3` — any 3.x. One stdlib-only script sanitises the routing file before it is injected. |
| Visual companion | `node` |
| Cross-model review (optional) | A Codex MCP server you configure yourself. The architect discloses a missing advisor pass and continues, so this weakens review rather than blocking it. |

## Install

```bash
# the plugin
claude plugin marketplace add https://github.com/a-r-it/automaton
claude plugin install development@automaton

# the architect's CLI
npm i -g @fission-ai/openspec

# jq, if you don't have it
brew install jq          # macOS
sudo apt install jq      # Debian/Ubuntu
```

`python3` ships with macOS and most Linux distributions — `python3 --version` to confirm. `npm`
comes with `node`, so if the OpenSpec install worked you already have both. Then
`/reload-plugins`, or start a new session.

Check what landed:

```bash
openspec --version && jq --version && python3 --version && node --version
```

## Sources

- [obra/superpowers](https://github.com/obra/superpowers) — Jesse Vincent, MIT. The methodology
  this plugin is built on; several skills here still descend directly from it.
- [pcvelz/superpowers](https://github.com/pcvelz/superpowers) — MIT. The Claude-Code-native fork
  this build merged from.
- [OpenSpec](https://github.com/Fission-AI/OpenSpec) — the spec-and-change tool the architect
  authors through.

This build has since diverged from both forks: multi-harness support is gone and the design phase
was rebuilt around the architect. Original copyrights are retained — see `NOTICE`.
