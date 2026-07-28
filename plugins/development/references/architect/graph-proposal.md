# Graph: proposal

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
Exploration → Questioning [ project state read; authoring contract pulled ]

Questioning → Drafting    [ no requirement-affecting unknown remains ]

Drafting    → Validation  [ proposal drafted or revised ]
Drafting    → Exploration [ a variant the user chose moves the scope — the questions that
                            settled the old scope no longer cover it ]

Validation  → Drafting    [ `openspec validate` failed, and validation rounds < 3 ]
Validation  → Review      [ `openspec validate` clean ]
Validation  → Approval    [ 3 validation rounds reached and still failing — present the
                            proposal with the outstanding findings named; the user decides ]

Review      → Validation  [ a finding was fixed in the document, so it has changed since it
                            was last validated ]
Review      → Approval    [ every finding dispositioned, and the document has not changed
                            since it was last validated ]

Approval    → Drafting    [ the user asked for changes ]
```

Entry: Exploration on a first pass. Returning from the router, enter at the stage the change
demands — Exploration if the scope moved, Drafting if only the wording did. Entry is the
router's call and is not an edge: the rule above governs movement inside the graph, not
arrival at it.

Exit: Approval with the user's approval — hand control back to the router, carrying what
OpenSpec cannot tell it (see Handback).

Guardrails:
- Editing an artifact, asking the user a question, or calling a tool does not itself change the
  current stage.
- **Rounds are counted only where you run or dispatch something.** In this graph that is
  `Validation`, and its round is a **pair**: one `Validation → Drafting` plus the
  `Drafting → Validation` that follows it (bound: 3). At the bound resolve rather than loop —
  take `Validation → Approval` and put the outstanding findings in front of the user.
  `Review → Validation → Review` is not a loop of its own: the return either leaves for
  Approval or passes through Drafting, which the validation bound already counts.
- **Working with the user is not counted at all.** Ask as many questions as the work needs;
  travel `Drafting → Exploration` and come back as often as the scope keeps moving; take the
  rework at Approval as many times as they ask for it. None of it has a round number, and none
  of it has a bound. Re-scope keeps the change, its slug, and the pulled schema valid across it;
  a re-scope that reaches other artifacts is the router's call, not this graph's.
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

- Read the current state through the lens of the request — files, docs, recent commits.
- Assess scope before detailed questions: a request spanning multiple independent subsystems is
  flagged and decomposed — each sub-project gets its own change.
- Pull the authoring contract before you question anyone. It states what the document will have
  to carry, and so it is the only thing that can tell you when you have asked enough:

  ```
  Bash:
    command: openspec instructions proposal --change <slug> [--store <id>] --json
  ```

**Questioning.**

- Open by asking the user to describe what they want in their own words, at whatever length
  suits them. You listen first — every question after that comes out of what their account
  leaves unsaid.
- The contract you pulled is your coverage checklist, never your interview script. Question the
  intent and the system; mapping what you hear onto the document is your job, not the user's.
  Ask them to supply a section by name and you hand them your paperwork — and an answer shaped
  to fit a box loses whatever the box has no room for.
- Do not ask what exploring the project already answered.
- Go until no requirement-affecting unknown remains. An unasked question survives as a silent
  assumption, and assumptions surface downstream as defects.
- Hunt what the user did not think to mention — the happy path is already in their account.
  Failure modes; lifecycle edges (first run, re-run, partial, interrupted, concurrent); who else
  is affected; collisions with what exists; deliberate exclusions; assumptions they believe you
  share; how anyone will later know it worked. An answer that surprises you is a seam — dig
  there before moving on.

**Drafting.**

- Draft section by section, in the order the pulled contract declares. Put 2–3 fillings of the
  current section to the user, take their pick, write it, and only then move on.
- The variants must differ in substance — scope drawn wider or narrower, a different driver
  named, a different set of capabilities touched. Three phrasings of one content is a fake
  choice. Where a section honestly admits one filling only, show that one and say why.
- Author the "what and why". Approaches, trade-offs, and rejected alternatives belong to the
  design artifact.
- Whichever section names the capabilities this change touches is the contract the delta specs
  must fulfil: research the existing `openspec/specs/` before drafting it, and offer no variant
  whose names you have not checked against what is already there.
- Variants differ within the scope Questioning settled. One that widens or narrows it is a
  re-scope, not a choice inside this stage: if the user takes it, say so and take
  `Drafting → Exploration`.

**Validation.**

- Run it once per entry into this stage. What it reports decides the edge — fixing is
  Drafting's work, not this stage's:

  ```
  Bash:
    command: openspec validate <slug> [--store <id>]
  ```

**Review.**

- You do not review your own draft — dispatch fresh eyes:

  ```
  Agent:
    subagent_type: development:artifact-reviewer
    description: "Review proposal"
    prompt: |
      Artifact: proposal
      Change: <slug>
      Path: <path to proposal.md>
      Contract: run exactly this command, and no others —
      `openspec instructions proposal --change <slug> [--store <id>] --json`
      Other artifacts of this change: <paths, or "none yet">
      Decisions agreed with the user: <every choice and assumption settled in the
      conversation — the document must carry them; flag any that are missing or
      contradicted>
  ```

- Disposition every finding: fix it in the artifact, or reject it with a stated reason. The
  reviewer holds no veto, but it raises nothing you may skip in silence. Recommendations are
  yours to take or leave. The dispositions go into this stage's task description: they travel in
  the handback, and a compaction must not be able to take them.
- All of it happens inside this stage — open no tasks for findings.
- Dispatch a review for a draft the reviewer has not seen. Arriving here after a re-validation
  that only carried out the fixes you already dispositioned, do not dispatch again — confirm
  every finding is dispositioned and leave.

**Approval.**

- Ask the user to read the proposal themselves:

  > "Proposal written to `<path>`. Please read it and tell me if you want any changes before we
  > move on to the specs."

- Arriving here at a bound — validation still failing — name it in that message; the user is
  deciding with it in view, not around it.
- Wait for their response. Cosmetic fixes: apply directly. Proceed only once they approve.

## Handback

`openspec status --json` reports whether an artifact's output files exist plus their resolved
paths, so the path is always recoverable and never belongs in a handback. What it cannot report,
only you can:

- that the **user approved** — `done` means "a file exists", never "we settled it";
- that validation came back **clean**, and at which round — `status` does not carry it;
- the **review dispositions**, rejected findings included, with their stated reasons.
