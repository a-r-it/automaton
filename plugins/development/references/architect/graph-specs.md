# Graph: specs

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
Exploration → Consilium  [ baseline specs and the approved proposal read; authoring contract
                           pulled ]

Consilium   → Consilium  [ answers or an objection rework folded into the proposal, and panel
                           rounds < 3 — the next round runs the full panel
                         | 3 panel rounds reached and the user chose to amend the proposal and
                           carry on — the amendment restarts the count ]
Consilium   → Partition  [ the panel converged — every routed expert returned `Direction: OK`
                           with no open question, against the proposal as it stands now
                         | 3 panel rounds reached and the user chose to overrule the panel —
                           what did not converge travels in the handback ]

Partition   → Drafting   [ every requirement the packs raise has exactly one owning capability,
                           and every capability the proposal declares has requirements
                           assigned to it ]

Drafting    → Validation [ delta specs drafted or revised ]

Validation  → Drafting   [ `openspec validate` failed or coverage is incomplete, and
                           validation rounds < 3 ]
Validation  → Review     [ `openspec validate` clean, and coverage complete ]
Validation  → Approval   [ 3 validation rounds reached and still failing or incomplete — present the
                           specs with the outstanding findings named; the user decides ]

Review      → Validation [ a finding was fixed in the specs, so they have changed since they
                           were last validated ]
Review      → Advisor    [ every finding dispositioned, and the specs have not changed since
                           they were last validated ]

Advisor     → Validation [ a cosmetic or rendering finding applied, and advisor loops < 3 ]
Advisor     → Consilium  [ a material finding the proposal already covers — the panel owns
                           requirements, so a new round produces it, not you ]
Advisor     → Approval   [ every finding dispositioned, and nothing was edited since the last
                           validation
                         | 3 advisor loops reached — carry what is still open into the
                           approval message
                         | the advisor is unavailable — its absence travels to the user in
                           the approval message ]

Approval    → Drafting   [ rework the packs already cover, and neither the owning capability
                           nor the delta operation moves — anything else reopens Partition ]
Approval    → Consilium  [ the user wants behaviour the panel never ruled on ]
```

Entry: Exploration on a first pass. Returning from the router, enter at the stage the change
demands — Exploration if the proposal's capabilities moved, Consilium if any requirement-bearing
part of it did, Drafting if only the wording did. Entry is the router's call and is not an
edge: the rule above governs movement inside the graph, not arrival at it.

Exit: Approval with the user's approval — hand control back to the router, carrying what
OpenSpec cannot tell it (see Handback).

Guardrails:
- Editing an artifact, asking the user a question, or calling a tool does not itself change the
  current stage.
- **Rounds are counted only where you run or dispatch something**, and each count lives in that
  stage's task description, announced on the edge that opens the round. This graph has three:
  - `Drafting → Validation → Drafting` — a **validation round** is the **pair**, not one edge
    (bound: 3). At the bound resolve rather than loop: take `Validation → Approval` and put the
    outstanding findings in front of the user.
  - `Consilium → Consilium` — one **panel round** is one dispatch of the whole panel (bound: 3).
    At the bound the user decides, and both of their continuing answers have an edge: amend and
    carry on, or overrule the panel. Dropping the change is the third answer and is an abort.
  - `Advisor → Validation → Review → Advisor` — one **advisor loop** is one consultation of the
    advisor (bound: 3).
  - `Review → Validation → Review` is not a loop of its own: the return either leaves for
    Advisor or passes through Drafting, which the validation bound already counts.
    `Advisor → Consilium → …` is not an advisor loop either — it reopens the panel, so every
    pass is a panel round and Consilium counts it.
- **Working with the user is not counted at all.** Answer their open questions, rework the
  proposal with them, take the rework at Approval as many times as they ask for it. None of it
  has a round number, and none of it has a bound.
- **Re-entering Consilium invalidates everything it feeds.** Reopen Partition, Drafting,
  Validation, Review, Advisor and Approval along with it — the advisor's comparison and the
  user's approval rest on the panel's requirements exactly as the specs do. A completed task
  below a reopened Consilium claims work whose input has since changed.
- Out of reach here: anything that moves the change's purpose, scope, or the capabilities the
  proposal declares. Record it, stop, and hand back to the router naming the artifact it
  belongs to —
  amending the proposal on those axes is the router's call, not this graph's.
- **The one upstream edit this graph makes** is folding a user's answer into the proposal. It
  is not the move above — an answer records a decision without moving purpose, scope, or the
  declared capabilities, so the proposal is not re-entered. It is not free either: an answer
  can settle observable behaviour, which the design rests on. Say so at handback. It invalidates
  the panel too — see the round record.
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

- Read `openspec/specs/` before anything else — existing capability names, the requirements
  already defined, and what the system does today. Everything downstream depends on it: the
  panel consults against current behaviour, and a MODIFIED requirement that misquotes its
  baseline block silently fails to merge on archive.
- Read the approved proposal in full. The capabilities it declares are the contract this
  artifact fulfils — exactly those, no others. Read them off the document; where they are
  written is the schema's business, not this graph's.
- Pull the authoring instructions and follow them — the format lives in the CLI, not here:

  ```
  Bash:
    command: openspec instructions specs --change <slug> [--store <id>] --json
  ```

**Consilium.**

A routed panel of read-only expert agents consulted on the **proposal**, and never on the specs.
The panel's job is to *raise* requirements — each expert reads the change through one
specialized lens and returns what the system MUST do that the proposal does not yet say. Their
requirements are what the delta specs are made of.

*Workdir.* This stage writes into the run's working directory, resolved at routing and governed
by the operating rules there:

    <project>/.automaton/development/<slug>/
      dispatch/<agent>.md        ← what each expert was sent (audit of inputs)
      packs/r<round>-<agent>.md  ← verbatim verdict packs, one per agent per round

The packs are where the panel's output lives while this graph works — the only durable carrier
of what it raised, and the reason no second copy of it exists.

*Round record.* This stage's task `description` carries the round number and the proposal's hash,
both re-recorded every round: `shasum -a 256 <proposal> | cut -d' ' -f1`. Convergence holds only
while that hash matches the file on disk — any edit to the proposal, a recorded answer included,
opens a new round. The task list survives a compaction; the conversation does not.

*Routing.* Route by the proposal's CONTENT, not by repo type. Say which agents you are invoking
and which you are not, one line of reason each, as you dispatch.

| Agent | Trigger signals in the proposal |
|---|---|
| `development:security-analyst` | ALWAYS — see the security gate below |
| `development:api-designer` | any externally consumed contract appears or changes — HTTP/GraphQL/event schemas, webhooks, CLI interface, config/file format, plugin public surface |
| `development:devops-engineer` | CI/CD, release/distribution, packaging, IaC/containers, lifecycle hooks, cron/launchd, environments/secrets, observability |
| `development:automotive-engineer` | AAOS / Android Auto / AOSP / vehicle / HAL / VHAL / RRO |
| `development:android-performance-engineer` | any Android runtime surface — app/module, UI, startup, background work, memory/battery |

- When unsure whether a lens applies — invoke. A false positive costs one read-only pass; a
  missed lens costs a hole in every spec that lens would have shaped.
- Co-triggering is normal — an AAOS change triggers automotive AND android-performance.
- Dispatch every selected agent in ONE message (parallel block).
- A pack that hands off to a panel lens you did not route is a routing signal: invoke that agent
  next round and record the reason. Handoffs to owners outside the panel (safety, legal,
  kernel/BSP, platform) stay notes.

*Security gate.* For every proposal that reaches this stage, invoke
`development:security-analyst`. Unconditional: do not self-assess "no security surface", do not
apply a docs-only exemption, do not substitute skip evidence. A request that never produces an
implementation-bound change is outside this flow entirely; once it is here, security
participates.

*Dispatch packet.* Save a copy to `dispatch/<agent>.md`. It contains ONLY: the proposal path,
the decisions taken so far, the baseline spec paths for every capability the proposal marks
modified, project policy relevant to the lens, and entry-point pointers — the existing contracts
or files this lens should read first. No unrelated session history.

The ask: consult on the brief at the proposal path, starting from the named entry-point pointers
— if none are supplied, locate anchors with read-only search — and return the standard verdict
pack. Frame it around what that document actually says, which the expert reads for itself. Name
no section of it in the ask: you would be describing one schema to an expert working from
another.

*Rounds.*

1. Dispatch all routed agents in parallel. Save each returned pack VERBATIM to
   `packs/r<N>-<agent>.md` (drop only the conversational wrapper). Each requirement's only
   durable home is its pack file: the text is never copied into a second document, and the file
   name is its attribution.
2. Write the round number and the proposal's hash into this stage's task description.
3. Evaluate:
   - All `Direction: OK` and zero open questions → the panel has converged. Done.
   - Open questions → `AskUserQuestion`, one question at a time, carrying each pack's
     basis/options/impact into the option descriptions. Fold the answers verbatim into the
     proposal — the experts read that document and nothing else, so an answer left out of it
     never reaches them → full re-run, ALL routed agents, new round.
   - `Objection` → rework the proposal with the user. A rework that moves what the change does,
     or which capabilities it touches, is the guardrail. Anything smaller: amend, re-run.
- A malformed or empty pack → retry that expert once, then escalate to the user. Never drop an
  expert from a round.
- Three rounds without convergence is not a stage to sit in: name what did not converge and put
  it to the user. Experts still disagreeing after three rounds disagree about something the
  proposal has not settled, so the call is theirs — amend the proposal and run the panel again,
  overrule the panel and carry the disagreement forward, or drop the change. Do not hand it to
  the router: its table re-enters the proposal only for purpose, scope, or capabilities, so a
  behavioural disagreement would be routed straight back here.

*What the packs carry.* Everything the panel raised stays in the pack files, read directly by
the stages that need it — Partition to assign, Drafting to render. There is no intermediate
document: one would only be a second copy of the same text, free to drift from it.

- A requirement is the expert's text VERBATIM with its RFC keyword intact, its acceptance
  criterion, and its stated assumption when it has one. Attribution is the pack's file name and
  never enters a spec file.
- A pack's recommendations and its Angle narrative are advice. They bind nothing and nothing
  downstream reads them: only what an expert stated as a requirement enters a spec, and only the
  specs travel onward.
- NEVER merge requirements. Near-duplicates are each rendered, with a cross-reference; conflicts
  of intent go to the user. You never arbitrate between experts.
- Drift guard: on a re-run, a requirement citing nothing from what actually changed in the
  proposal goes to the user. Escalate-only — drift may ADD user attention, never remove a
  review.

*Never:* skip or soften the security invocation · merge, paraphrase, or "improve" an expert's
requirement · arbitrate an expert conflict without the user · re-dispatch the panel onto the
written specs.

**Partition.**

- Read the round's packs and assign every requirement they raise to exactly one capability the
  proposal declares. One that plausibly fits two gets an owner and a cross-reference from the
  other — never a copy in both.
- Decide each requirement's delta operation against the baseline you read: ADDED, MODIFIED,
  REMOVED, RENAMED.
- A requirement that fits no declared capability means the proposal's contract is wrong — the
  guardrail, not a fix you make here.
- No spec file is written in this stage; the files land at Drafting, one per capability, at
  `specs/<capability>/spec.md` inside the change. The assignments themselves go into this
  stage's task description — Drafting reads them there, and a compaction cannot take them.

**Drafting.**

- Render the packs, following Partition's assignments. The requirement body goes in VERBATIM,
  RFC keyword intact — no rewording, no tightening, no improving. Rewording is where meaning is
  lost, and the expert who wrote it will never see the file.
- The acceptance criterion becomes the scenario. That derivation is interpretive: WHEN/THEN
  imposes event structure the criterion may not state literally. That is allowed, and it is
  exactly why the requirement body itself stays untouched. A stated assumption becomes an
  explicit precondition.
- Verbatim governs the requirement's own text, not the boundary of the block it sits in. A
  MODIFIED delta carries the **entire** baseline requirement block, edited — render only the
  expert's body and whatever the baseline said and this change does not touch is dropped, a loss
  that lands at archive. Take the boundary from the guide's delta rules, the text from the pack.
- Author WHAT the system does, observably. HOW it is built belongs to the design.
- Source attribution never appears in a spec file. It is the pack's file name and stays in the
  workdir.

**Validation.**

- Run it once per entry into this stage. What it reports decides the edge — fixing is Drafting's
  work, not this stage's:

  ```
  Bash:
    command: openspec validate <slug> [--store <id>]
  ```

- Then check coverage yourself: every capability the proposal declares has a file, no file
  exists for a capability it does not declare, and every requirement the packs raise landed
  somewhere. `openspec status` marks the plural `specs` artifact done on the first matching file
  — it cannot see a missing sibling or a dropped requirement.

**Review.**

- You do not review your own draft — dispatch fresh eyes, one reviewer per capability file, all
  in a single message:

  ```
  Agent:
    subagent_type: development:artifact-reviewer
    description: "Review delta spec: <capability>"
    prompt: |
      Artifact: specs
      Change: <slug>
      Path: <path to specs/<capability>/spec.md>
      Contract: run exactly this command, and no others —
      `openspec instructions specs --change <slug> [--store <id>] --json`
      Other artifacts of this change: <proposal path; the sibling delta spec paths>
      Decisions agreed with the user: <every choice and assumption settled in the
      conversation — the document must carry them; flag any that are missing or
      contradicted>
  ```

- Disposition every finding: fix it in the artifact, or reject it with a stated reason. The
  reviewer holds no veto, but it raises nothing you may skip in silence. Recommendations are
  yours to take or leave. The dispositions go into this stage's task description: they travel in
  the handback, and a compaction must not be able to take them.
- A finding that would reword an expert's requirement is a rendering question, not a wording
  one: the body stays verbatim, and a genuine defect in it goes to the user.
- All of it happens inside this stage — open no tasks for findings.
- Dispatch a review for a draft the reviewers have not seen. Arriving here after a
  re-validation that only carried out fixes you already dispositioned — your own, or the
  advisor's on its way back — do not dispatch again: confirm every finding is dispositioned
  and leave. Every clean validation lands here, so passing straight through is a normal
  outcome of this stage, not a skipped one.

**Advisor.**

The change's first advisor thread — none was opened during the proposal. It is the only reader
that compares the specs against the packs they were built from, since the panel never sees them.

```
mcp__codex__codex:
  prompt: <the ask below>
  sandbox: read-only
```

Leave `model` unset; `mcp__codex__codex-reply(threadId, …)` continues the thread. The advisor
never edits — everything it returns is advice you disposition.

- Give it the delta specs, the proposal as the intent source, and the round's pack paths. Ask,
  read-only, for: requirements from the packs that are missing or distorted in the specs, gaps,
  contradictions, unmet intent, risks.
- Disposition every finding by class — cosmetic or rendering (wording outside a requirement
  body, formatting, a scenario that misreads its criterion); material and already covered by
  the proposal; material and moving scope or capabilities; rejected, which the user signs off,
  since you do not reject an advisor finding alone. The dispositions go into this stage's task
  description: they travel in the handback, and a compaction must not be able to take them.
- Three advisor loops without terminal dispositions: stop looping and take `Advisor → Approval`
  on its bound condition, naming what is still open.
- **An unavailable advisor is a hole, not a formality.** Name the tool and the error in the
  approval message: these specs were never compared against the requirements they were built
  from. Advice never blocks, but a gap the user is not told about is not a disclosure.
- Say what this buys honestly: a fresh thread buys context-independence, not model-independence.
  The genuine cross-model check is the advisor against the Claude panel, and agreement from an
  advisor you handed the panel's conclusions to is not independent confirmation.

**Approval.**

- One capability file at a time, section by section, scaled to complexity; ask after each
  whether it looks right.
- Arriving here at a bound — validation still failing, or the advisor never ran — name it in
  that message; the user decides with it in view, not around it.
- Cosmetic fixes: apply directly. Proceed only once they approve.
- Approved, cosmetic fixes applied: commit this artifact through the project's version control
  — `docs(openspec): specify <what it settles>`; every delta spec of this change goes in the one
  commit. Then leave. Committing before the fixes would put a text into history that is not the
  one the user approved.

## Handback

`openspec status --json` reports whether an artifact's output files exist plus their resolved
paths, so the path is always recoverable and never belongs in a handback. What it cannot report,
only you can:

- that the **user approved**, and per capability file — `done` means "a file exists", never
  "we settled it";
- whether a recorded answer settled **observable behaviour** — the design rests on it, and this
  graph is the only place that knows it happened;
- that validation came back **clean and complete**, and at which round — `status` cannot see a
  missing sibling or a dropped requirement, so its verdict on the plural `specs` artifact is not
  the coverage answer;
- the **review and advisor dispositions**, rejected findings included, with their reasons, and
  whether the advisor ran at all.

Nothing from the workdir travels: the delta specs are the only thing this graph hands onward,
and what comes after this artifact reads them, the proposal, and the code — nothing else.
