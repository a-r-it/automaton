# Graph: design

## Stages and transitions

One row is one edge. Inside its brackets, `|` separates the alternative conditions under which
that edge may be taken — each on its own line, each with what leaving under it produces. Before
every transition, announce `Transition: <current> → <next> (<reason>)`, find the row, and quote
the single condition line you are travelling on. A pair of stages not joined by a row here, or a
reason not listed on the row that joins them, is FORBIDDEN.

When the edge you are taking is inside a bounded loop, the announcement is also where the count
lives — say which round it opens and against which bound:
`Transition: Validation → Drafting (validate failed — validation round 2 of 3)`.

A bound is written in one form and only one: `<counter> rounds < N` on the edge that opens a
round, `N <counter> rounds reached` on the edge that resolves it — `loops` in place of `rounds`
where the loop is one. Both name the same counter, or they are not a pair.

```
Exploration → Questioning [ proposal, delta specs and the code they touch read; authoring
                            contract pulled ]

Questioning → Options     [ no unknown remains that would change which approach is picked ]

Options     → Exploration [ the approach the user leans toward rests on code not yet read ]
Options     → Drafting    [ the user picked an approach ]

Drafting    → Options     [ drafting exposed a fork the picked approach does not answer ]
Drafting    → Validation  [ design drafted or revised ]

Validation  → Drafting    [ `openspec validate` failed or a requirement has no decision
                            covering it, and validation rounds < 3 ]
Validation  → Review      [ `openspec validate` clean, and coverage complete ]
Validation  → Approval    [ 3 validation rounds reached and still failing or incomplete —
                            present the design with the outstanding findings named; the user
                            decides ]

Review      → Validation  [ a finding was fixed in the document, so it has changed since it
                            was last validated ]
Review      → Approval    [ every finding dispositioned, and the document has not changed
                            since it was last validated
                          | a reader is unavailable and the document has not changed since
                            it was last validated — that absence travels to the user in the
                            approval message ]

Approval    → Drafting    [ the user asked for changes inside the picked approach ]
Approval    → Options     [ the user wants a different approach ]
```

Entry: Exploration on a first pass. Returning from the router, enter at the stage the change
demands — Exploration if the specs moved, Drafting if only the wording did. Entry is the
router's call and is not an edge: the rule above governs movement inside the graph, not
arrival at it.

Exit: Approval with the user's approval. This is the flow's terminal artifact — hand control
back to the router, carrying what OpenSpec cannot tell it (see Handback).

Guardrails:
- Editing an artifact, asking the user a question, or calling a tool does not itself change the
  current stage.
- **Rounds are counted only where you run or dispatch something.** In this graph that is
  `Validation`, and its round is a **pair**: one `Validation → Drafting` plus the
  `Drafting → Validation` that follows it (bound: 3). At the bound resolve rather than loop —
  take `Validation → Approval` and put the outstanding findings in front of the user.
  `Review → Validation → Review` is not a loop of its own: the return either leaves for
  Approval or passes through Drafting, which the validation bound already counts.
- **Working with the user is not counted at all.** Ask as many questions as the work needs; go
  back to Exploration and to Options as often as the approach demands; take the rework at
  Approval as many times as they ask for it. None of it has a round number, and none of it has
  a bound.
- **Upstream is settled.** The proposal and the delta specs arrive here approved and are trusted
  as given. This graph never edits them and never argues with them; a requirement is an
  obligation to design for, not a claim to test.
- Never name a section of an artifact. Which sections exist is the schema's business, the
  schema is the project's, and it differs between projects and machines. To know what a
  document contains, read it; to know what it must contain, pull its instructions.
- **Cosmetic** is wording, typos, and formatting — nothing else. A fix applied at Approval
  without re-validating is cosmetic by that definition; anything that changes what the
  document says takes the rework edge instead.
- **Abort.** A user decision to abort overrides the graph; nothing else does. It is not a
  transition and has no edge: stop at the stage you are on and leave its task `in_progress`.
  Hand nothing back.

## Per-stage guidance

How-to, never a second source of structural truth. Which edge to take is the section above's
business.

Every `openspec` call below carries `--store <id>` when the change lives in a store, and omits
it when it lives in a project root. The router settled which before you got here; if that is not
established, you are not in this graph yet — return to routing rather than resolve it here. A
command that travels in a dispatch prompt carries every placeholder resolved: the subagent starts
in the session cwd and cannot find the root on its own.

**Exploration.**

- Read the proposal and every delta spec first. They are the obligation this document answers:
  what the system must observably do. You are here to decide how.
- Then read the code those requirements land in — how it does the job today, what the seams and
  neighbouring patterns are, what constrains a change there. This is where the unknown actually
  is, and it is the only place this stage investigates.
- Pull the authoring contract:

  ```
  Bash:
    command: openspec instructions design --change <slug> [--store <id>] --json
  ```

  It tells you the **shape** of the document, never whether to write one. A design is authored
  for every change; where a project's schema calls it optional, that is the tool's generic
  advice about a document, not this flow's rule about a change.

**Questioning.**

- Ask about HOW only. What the system must do is settled; a question that reopens it is a
  question for a graph you already left.
- One question at a time, multiple choice where the alternatives are nameable.
- What is worth asking: constraints you cannot read off the code (compatibility, dependencies
  they will not take, operational limits), what has been tried here before and why it was
  dropped, tool and pattern preferences, what must not break, and which currency they would
  rather pay in — complexity, performance, migration cost.
- Do not ask what reading the code already answered.

**Options.**

- Put 2–3 whole designs to the user. Each is one coherent approach end to end, not a menu of
  independent forks — the user is picking a direction, not assembling one.
- They must differ in substance: a different seam to extend, a different boundary, a different
  thing traded away. Three wordings of one approach is a fake choice.
- For each: how it meets the requirements, what it costs, what it risks, and what it forecloses.
  Lead with your recommendation and say why. Where investigation honestly leaves one viable
  approach, show that one, and name what was ruled out and by what evidence.
- Whatever is rejected here is written down at Drafting with its reason. A rejected alternative
  is part of the decision, not discarded work.
- The **visual companion** belongs to this stage and nowhere else — an architecture or data-flow
  diagram is often the difference between an approach the user can judge and one they can only
  agree with. Offer it just-in-time, as its own message, the first time a comparison is
  genuinely clearer shown than told; read
  `${CLAUDE_PLUGIN_ROOT}/references/visual-companion.md` before starting it. Anything settled on
  a screen is transcribed into the design — the screens are never an input to what comes next.
  Stop the server when you leave this graph.

**Drafting.**

- Draft section by section, in the order the pulled contract declares.
- Author HOW. What the system does is the specs' job — restating it here only creates a second
  copy to drift.
- Every decision names the requirements it covers, in whatever words the document's own prose
  allows. That naming is what makes coverage checkable at Validation without a side-file.
- Record the alternatives rejected at Options with the reason each was rejected.

**Validation.**

- Run it once per entry into this stage. What it reports decides the edge — fixing is Drafting's
  work, not this stage's:

  ```
  Bash:
    command: openspec validate <slug> [--store <id>]
  ```

- Then check coverage yourself: every requirement in every delta spec of this change is covered
  by at least one decision. `openspec validate` checks the document's structure; it has never
  read the specs against it.

**Review.**

- You do not review your own draft — dispatch fresh eyes. Two readers, both calls in ONE
  message: they answer the same question from different models, and running them together costs
  one round instead of two.

  ```
  Agent:
    subagent_type: development:artifact-reviewer
    description: "Review design"
    prompt: |
      Artifact: design
      Change: <slug>
      Path: <path to design.md>
      Contract: run exactly this command, and no others —
      `openspec instructions design --change <slug> [--store <id>] --json`
      Other artifacts of this change: <proposal path; the delta spec paths>
      Decisions agreed with the user: <every choice and assumption settled in the
      conversation — the document must carry them; flag any that are missing or
      contradicted>
  ```

  ```
  mcp__codex__codex:
    prompt: |
      Read-only review of an implementation design. Paths: <design>, <proposal>,
      <delta specs>. The proposal and specs are approved and fixed — do not
      propose changes to them. Report against the design only: requirements no
      decision covers, decisions that contradict each other or the specs, risks
      and failure modes the approach does not address, and anything the codebase
      makes unworkable as written.
    sandbox: read-only
  ```

  Leave `model` unset; `mcp__codex__codex-reply(threadId, …)` continues the thread. Neither
  reader edits — everything they return is advice you disposition.

- Disposition every finding: fix it in the artifact, or reject it with a stated reason. Neither
  reader holds a veto, but neither raises anything you may skip in silence. Recommendations are
  yours to take or leave. The dispositions go into this stage's task description: they travel in
  the handback, and a compaction must not be able to take them.
- All of it happens inside this stage — open no tasks for findings.
- Dispatch a review for a draft the readers have not seen. Arriving here after a re-validation
  that only carried out fixes you already dispositioned, do not dispatch again — confirm every
  finding is dispositioned and leave.
- **A reader that never ran is a hole, not a formality.** If either dispatch fails, name which
  one and why in the approval message: a design one reader saw is not a design that passed two.
  Advice never blocks, but a gap the user is not told about is not a disclosure.

**Approval.**

- Section by section, scaled to complexity; ask after each whether it looks right.
- Arriving here at a bound — validation still failing, or a reader that never ran — name it in
  that message; the user decides with it in view, not around it.
- Cosmetic fixes: apply directly. Proceed only once they approve.

## Handback

`openspec status --json` reports whether an artifact's output files exist plus their resolved
paths, so the path is always recoverable and never belongs in a handback. What it cannot report,
only you can:

- that the **user approved** — `done` means "a file exists", never "we settled it";
- that validation came back **clean and complete**, and at which round — `status` does not carry
  it, and it cannot see a requirement no decision covers;
- the **review dispositions**, rejected findings included, with their stated reasons, and
  whether both readers ran at all;
- that this is the flow's terminal artifact: with the design approved, the change is ready to
  hand off downstream.
