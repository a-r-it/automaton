export const meta = {
  name: 'consilium',
  description: 'Runs ONE round of the architect consilium: routes the expert panel by proposal content, dispatches every routed lens in parallel, persists the verdict packs verbatim, and reports whether the panel converged.',
  whenToUse: 'Called from the architect flow at the Consilium stage with the proposal path and the run workdir. One invocation = exactly one panel round: a new round can only follow a change to the proposal, and the proposal only changes through conversation with the user, which a workflow cannot hold.',
  phases: [
    { title: 'Route', detail: 'Pick the panel lenses from the proposal content; security is unconditional' },
    { title: 'Brief', detail: 'Write the per-agent dispatch packets as the audit of inputs' },
    { title: 'Consilium', detail: 'Every routed expert consulted in parallel, one retry for a malformed pack' },
    { title: 'Record', detail: 'Packs saved verbatim, round record appended, convergence evaluated' },
  ],
}

// ── args (supplied by the architect flow) ────────────────────────────────────
//   proposalPath  : path to the proposal the panel is consulted on (required)
//   workdir       : the run's working directory, <project>/.automaton/development/<slug>/
//   round         : round number, 1-based (default 1)
//   decisions     : decisions taken so far, one line each
//   baselineSpecs : baseline spec paths for every capability the proposal marks modified
//   policy        : project policy relevant to the panel, or a path to it
//   entryPoints   : existing contracts or files each lens should read first
//   forceAgents   : lenses to invoke regardless of routing — a previous round's handoffs
function parseArgs(raw) {
  if (raw == null) return {}
  if (typeof raw === 'object') return raw
  if (typeof raw !== 'string') return {}
  const text = raw.trim()
  if (text.startsWith('{')) {
    try { return JSON.parse(text) } catch (e) { /* not JSON after all */ }
  }
  return { proposalPath: text.split(/\s+/)[0] || '' }
}

const A = parseArgs(typeof args === 'undefined' ? null : args)
const PROPOSAL = A.proposalPath || ''
const ROUND = Number(A.round) > 0 ? Number(A.round) : 1
const DECISIONS = Array.isArray(A.decisions) ? A.decisions : []
const BASELINES = Array.isArray(A.baselineSpecs) ? A.baselineSpecs : []
const ENTRY_POINTS = Array.isArray(A.entryPoints) ? A.entryPoints : []
const POLICY = A.policy || ''
const FORCED = Array.isArray(A.forceAgents) ? A.forceAgents : []
const WORKDIR = (A.workdir || '').replace(/\/*$/, '/')

function fence(s) {
  const body = String(s == null ? '' : s).replace(/<<<UNTRUSTED|UNTRUSTED>>>/g, '[fence marker stripped]')
  return '<<<UNTRUSTED\n' + body + '\nUNTRUSTED>>>'
}

if (!PROPOSAL || !WORKDIR) {
  return {
    status: 'blocked',
    reason: 'consilium needs proposalPath and workdir. It is called from the architect flow at the Consilium stage, not on its own.',
    received: A,
  }
}

// The panel roster. `always` is a policy the script enforces, not advice a router may weigh:
// the security gate is unconditional for every proposal that reaches this stage.
const PANEL = [
  {
    agent: 'development:security-analyst',
    always: true,
    trigger: 'ALWAYS — the security gate is unconditional',
  },
  {
    agent: 'development:api-designer',
    trigger: 'any externally consumed contract appears or changes — HTTP/GraphQL/event schemas, webhooks, CLI interface, config/file format, plugin public surface',
  },
  {
    agent: 'development:devops-engineer',
    trigger: 'CI/CD, release/distribution, packaging, IaC/containers, lifecycle hooks, cron/launchd, environments/secrets, observability',
  },
  {
    agent: 'development:automotive-engineer',
    trigger: 'AAOS / Android Auto / AOSP / vehicle / HAL / VHAL / RRO',
  },
  {
    agent: 'development:android-performance-engineer',
    trigger: 'any Android runtime surface — app/module, UI, startup, background work, memory/battery',
  },
]

// ── Schemas ──────────────────────────────────────────────────────────────────

const ROUTE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['invoke', 'skipped'],
  properties: {
    invoke: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['agent', 'reason'],
        properties: {
          agent: { type: 'string', description: 'Exactly one of the roster names, verbatim' },
          reason: { type: 'string', description: 'One line: what in the proposal triggers this lens' },
        },
      },
    },
    skipped: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['agent', 'reason'],
        properties: {
          agent: { type: 'string' },
          reason: { type: 'string', description: 'One line: why this lens does not apply' },
        },
      },
    },
  },
}

// Requirements deliberately do NOT ride in this schema. A pack's requirement text has exactly
// one durable home — its pack file — and the file name is its attribution. A second copy in
// the return value would be free to drift from it.
const PACK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verbatim', 'direction'],
  properties: {
    verbatim: { type: 'string', description: 'The complete verdict pack, exactly as written, conversational wrapper dropped. Persisted to disk unchanged.' },
    direction: { type: 'string', enum: ['OK', 'Needs Decision', 'Objection'] },
    objection: { type: 'string', description: 'When Objection: the reason plus what would lift it' },
    mustCount: { type: 'number', description: 'How many MUST requirements the pack states' },
    openQuestions: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['question', 'basis', 'options', 'impact'],
        properties: {
          question: { type: 'string', description: 'What needs the user decision' },
          basis: { type: 'string', description: 'Why it matters' },
          options: { type: 'string', description: 'Defensible answers considered' },
          impact: { type: 'string', description: 'Which MUSTs or spec parts hinge on the answer' },
          unblockedWhen: { type: 'string' },
        },
      },
    },
    handoffs: { type: 'array', items: { type: 'string' }, description: 'Panel lenses this pack hands off to — a routing signal for the next round' },
  },
}

const RECORD_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'detail'],
  properties: {
    ok: { type: 'boolean' },
    detail: { type: 'string' },
    hash: { type: 'string', description: 'The proposal hash, when this call computed one' },
  },
}

function record(instructions, label, phaseName) {
  return agent(
    'You are the recorder for one round of an architect consilium. Run workdir: ' + WORKDIR + '.\n\n' +
    'Do exactly what is listed below and nothing else — write no analysis of your own, change ' +
    'no source, and never alter text you are told to save verbatim. Create directories as ' +
    'needed. If a step cannot be completed, report ok:false naming which one.\n\n' + instructions,
    { label: label, phase: phaseName, schema: RECORD_SCHEMA, effort: 'low' }
  )
}

// ── Route ────────────────────────────────────────────────────────────────────
// Routing is by the proposal's CONTENT, never by repo type.

phase('Route')
const routed = await agent(
  'Route the expert panel for an architect consilium.\n\n' +
  'Read the proposal at ' + PROPOSAL + ' in full, then decide which of these lenses it calls ' +
  'for. Judge by what the proposal actually says — never by the repository type.\n\n' +
  PANEL.map(function (p) { return '- ' + p.agent + ' — ' + p.trigger }).join('\n') + '\n\n' +
  'Rules: when unsure whether a lens applies, INVOKE it — a false positive costs one read-only ' +
  'pass, a missed lens costs a hole in every spec that lens would have shaped. Co-triggering is ' +
  'normal (an AAOS change triggers automotive AND android-performance). Use the roster names ' +
  'above verbatim. Give one line of reason for every lens you invoke AND every lens you skip.',
  { label: 'route-panel', phase: 'Route', schema: ROUTE_SCHEMA }
)

// The roster's `always` entries and the caller's handoff carry-overs are added here, in code.
// A prose instruction to "always invoke security" is something a model can reason its way
// around; a concatenation is not.
const selected = []
function select(name, reason) {
  if (!name) return
  if (selected.some(function (s) { return s.agent === name })) return
  if (!PANEL.some(function (p) { return p.agent === name })) return  // never dispatch an off-roster name
  selected.push({ agent: name, reason: reason })
}

PANEL.filter(function (p) { return p.always }).forEach(function (p) { select(p.agent, p.trigger) })
;((routed && routed.invoke) || []).forEach(function (r) { select(r.agent, r.reason) })
FORCED.forEach(function (name) { select(name, 'carried over: a previous round handed off to this lens') })

if (!selected.length) {
  return { status: 'blocked', reason: 'Routing selected no lenses and the unconditional security gate did not apply — the roster names in this script and the installed agent names have diverged.', routed: routed || null }
}

log('Round ' + ROUND + ': ' + selected.length + ' lens(es) — ' + selected.map(function (s) { return s.agent.replace('development:', '') }).join(', '))

// ── Brief ────────────────────────────────────────────────────────────────────
// The dispatch packet is the audit of what each expert was sent. The script knows exactly
// what it sent, so one recorder writes them all.

phase('Brief')

const packetBody =
  'Proposal: ' + PROPOSAL + '\n' +
  'Round: ' + ROUND + '\n' +
  'Decisions taken so far:\n' + (DECISIONS.length ? DECISIONS.map(function (d) { return '- ' + d }).join('\n') : '- none') + '\n' +
  'Baseline specs for the capabilities this proposal modifies:\n' + (BASELINES.length ? BASELINES.map(function (b) { return '- ' + b }).join('\n') : '- none') + '\n' +
  'Entry-point pointers:\n' + (ENTRY_POINTS.length ? ENTRY_POINTS.map(function (e) { return '- ' + e }).join('\n') : '- none supplied; locate anchors with read-only search') + '\n' +
  'Project policy:\n' + (POLICY || '- none supplied; use your own baselines as review lenses') + '\n'

await record(
  'Write one dispatch packet per lens, each to ' + WORKDIR + 'dispatch/<agent>.md where <agent> ' +
  'is the lens name with its "development:" prefix removed. Every file holds this text, plus a ' +
  'first line naming its lens and the routing reason:\n' + fence(packetBody) + '\n' +
  'The lenses and their routing reasons:\n' +
  selected.map(function (s) { return '- ' + s.agent + ': ' + s.reason }).join('\n') + '\n' +
  'Write nothing else into these files — they are the audit of inputs, not a place for notes.',
  'dispatch-packets', 'Brief'
)

// ── Panel ────────────────────────────────────────────────────────────────────
// Every routed lens, in parallel. An expert is never dropped from a round: a malformed or
// empty pack is retried once, and a lens that fails twice blocks the round.

phase('Consilium')

function ask(entry, attempt) {
  return agent(
    'Consult on the brief at ' + PROPOSAL + ' and return your standard verdict pack.\n\n' +
    'Start from the entry-point pointers below; where none are supplied, locate the anchors ' +
    'yourself with read-only search.\n\n' + packetBody + '\n' +
    'Frame your consultation around what that document actually says — read it for yourself.\n\n' +
    'Return the complete pack, in your own required format, unaltered in the "verbatim" field: ' +
    'that text is saved to disk exactly as you write it and is the only durable home of every ' +
    'requirement you state. Then report your Direction, your open questions, and any panel lens ' +
    'you hand off to.' +
    (attempt > 1 ? '\n\nYour previous pack came back empty or malformed. Return the full format this time.' : ''),
    { label: entry.agent.replace('development:', '') + (attempt > 1 ? ':retry' : ''), phase: 'Consilium', schema: PACK_SCHEMA, agentType: entry.agent }
  )
}

function usable(p) {
  return !!(p && p.verbatim && String(p.verbatim).trim() && p.direction)
}

let packs = await parallel(selected.map(function (entry) { return function () { return ask(entry, 1) } }))

const retryIdx = []
packs.forEach(function (p, i) { if (!usable(p)) retryIdx.push(i) })

if (retryIdx.length) {
  log('Retrying ' + retryIdx.length + ' lens(es) that returned an unusable pack')
  const retried = await parallel(retryIdx.map(function (i) { return function () { return ask(selected[i], 2) } }))
  retryIdx.forEach(function (i, k) { packs[i] = retried[k] })
}

const failed = selected.filter(function (s, i) { return !usable(packs[i]) }).map(function (s) { return s.agent })

// ── Record ───────────────────────────────────────────────────────────────────

phase('Record')

const saved = selected
  .map(function (s, i) { return { agent: s.agent, pack: packs[i] } })
  .filter(function (x) { return usable(x.pack) })

const rec = await record(
  'Save this round of the panel.\n' +
  '1. Write each pack VERBATIM to ' + WORKDIR + 'packs/r' + ROUND + '-<agent>.md, where <agent> ' +
  'is the lens name without its "development:" prefix. Save the text exactly as given — no ' +
  'reformatting, no summarising, no headings of your own:\n\n' +
  saved.map(function (x) {
    return '--- ' + x.agent + ' ---\n' + fence(x.pack.verbatim)
  }).join('\n\n') + '\n\n' +
  '2. Compute the proposal hash: shasum -a 256 ' + PROPOSAL + ' | cut -d\' \' -f1 — report it as ' +
  '"hash". Convergence holds only while that hash matches the file on disk, so it is what a ' +
  'later round compares against.\n' +
  '3. Append one line to ' + WORKDIR + 'consilium-rounds.jsonl recording this round as JSON: ' +
  'round, the proposal hash, the lenses dispatched, and each lens direction:\n' +
  fence(JSON.stringify(saved.map(function (x) { return { agent: x.agent, direction: x.pack.direction } }))),
  'save-packs', 'Record'
)

// ── Convergence ──────────────────────────────────────────────────────────────
// Evaluated in code: every routed lens returned OK, and nobody raised a question.

const openQuestions = []
const objections = []
const handoffs = []

saved.forEach(function (x) {
  ;(x.pack.openQuestions || []).forEach(function (q) { openQuestions.push(Object.assign({ agent: x.agent }, q)) })
  if (x.pack.direction === 'Objection') objections.push({ agent: x.agent, objection: x.pack.objection || 'stated in the pack' })
  ;(x.pack.handoffs || []).forEach(function (h) {
    if (PANEL.some(function (p) { return p.agent === h }) && !selected.some(function (s) { return s.agent === h })) handoffs.push(h)
  })
})

const converged = !failed.length && !objections.length && !openQuestions.length &&
  saved.every(function (x) { return x.pack.direction === 'OK' })

log('Round ' + ROUND + ': ' + (converged ? 'converged' : objections.length + ' objection(s), ' + openQuestions.length + ' open question(s)'))

return {
  status: failed.length ? 'blocked' : (converged ? 'converged' : 'needs-decision'),
  round: ROUND,
  proposalHash: (rec && rec.hash) || '',
  packsDir: WORKDIR + 'packs/',
  dispatched: selected,
  skipped: (routed && routed.skipped) || [],
  directions: saved.map(function (x) { return { agent: x.agent, direction: x.pack.direction, mustCount: x.pack.mustCount || 0 } }),
  // These are the only pack contents that travel back: they are what a human must act on.
  // Requirements stay in the pack files, read from there by Partition and Drafting.
  openQuestions: openQuestions,
  objections: objections,
  handoffsToRouteNextRound: handoffs,
  failedLenses: failed,
}
