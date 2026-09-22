---
name: openspec-setup
description: >
  Installs the `development` OpenSpec schema and its config into a project or a
  store.
when_to_use: >
  Trigger phrases: "openspec setup", "install the development schema". Also when
  the `development` schema does not resolve from the project, and when design
  work is about to start in a repo that has no `openspec/`. Anti-triggers:
  authoring an artifact; registering a store only to read from.
---

# OpenSpec setup

To install the `development` schema into a surface, follow these steps.

## 1. Name the surface

```
Bash:
  command: openspec context             # the root resolved from here
Bash:
  command: openspec store list --json   # id + root of every registered store
```

Ask which one when both exist and the request does not say.

## 2. Read the surface before anything is written

Nothing is created until this is read — what is already there decides whether there is a
question at all:

```
Bash:
  command: cat <surface>/openspec/config.yaml
```

- **No `openspec/` at all** — nothing can be lost. Creating the root and installing is one
  proposal and one agreement; step 3 does not apply. The only `config.yaml` that would exist is
  the one `init` is about to write for us to replace, and asking permission to discard a file
  created seconds earlier by this same run is a question with no content.
- **`openspec/` is there and its `config.yaml` is already identical** to
  `${CLAUDE_PLUGIN_ROOT}/openspec/config.yaml` — no question either. Go to step 4.
- **`openspec/` is there and its `config.yaml` differs** — step 3. This is the only case where
  something of the project's own can be lost.

## 3. The one question — asked only when a config that is not ours is there

The script replaces `<surface>/openspec/config.yaml` wholesale. Everything else it writes is
ours: the `schemas/development/` directory. `specs/`, `changes/`, `archive/` and schemas under
other names are never touched — schemas coexist by name, side by side.

So exactly one thing can be lost, and exactly one question follows from it — ask it with what
the file currently binds and carries filled in:

```
AskUserQuestion:
  question: "<surface>/openspec/config.yaml binds `schema: <name>` and carries <its own
    `context:` and `rules:` | no rules of its own>. Ours replaces it wholesale."
  header: "config.yaml"
  options:
    - label: "Back it up, then replace"
      description: "Current file copied to config.yaml.bak.<timestamp>; ours installed."
    - label: "Replace it"
      description: "No copy kept. The current binding, `context:` and `rules:` are gone."
    - label: "Stop"
      description: "Nothing is written. The surface keeps resolving whatever it resolves now."
```

Do not offer to merge and do not merge: the backup lands beside the new file, both readable,
and whoever wrote the original is the one who knows what of it still matters.

## 4. Create the root if it is missing, then install

A root that does not exist yet is the user's to authorise: say where it will be created and
that the schema is installed with it, and get agreement — one proposal covering both, never a
second question afterwards. Then run, for a project from the surface's own root:

```
Bash:
  command: openspec init --tools none
Bash:
  command: openspec store setup <id> --path <folder>
```

`--tools none`: this flow drives OpenSpec through the architect, and the files `init` writes for
other AI tools would be a second, unowned instruction source.

Then install, whether the root was just created or already existed:

```
Bash:
  command: ${CLAUDE_PLUGIN_ROOT}/scripts/openspec-schema <surface> [--backup]
```

## 5. Verify

Run both with the surface's root as the working directory — `schema which` takes no store flag,
so a store is verified by standing in it:

```
Bash:
  command: openspec schema which development --json
Bash:
  command: openspec schema validate development
```

Pass is all three: `"source": "project"`, a path inside this surface, and
`Schema 'development' is valid`. Anything else — report what came back and stop. A half-bound
surface is worse than an unbound one: the architect would author against a contract nobody chose.

## Report

The surface (kind, and its path or store id), what was created, whether a backup was made and
where it landed, and both verification outputs.
