export const meta = {
  name: 'delta-specs',
  description: 'Renders the consilium packs into per-capability delta specs: assigns every raised requirement to exactly one capability, drafts one spec file per capability in parallel, then validates and re-drafts what fails.',
  whenToUse: 'Called from the architect flow once the consilium has converged, with the run workdir holding the packs. Covers the Partition, Drafting and Validation stages — none of them involves the user. Stops instead of guessing when a requirement fits no declared capability.',
  phases: [
    { title: 'Partition', detail: 'Every raised requirement assigned to exactly one capability, with its delta operation' },
    { title: 'Drafting', detail: 'One renderer per capability, in parallel — requirement bodies copied verbatim' },
    { title: 'Validation', detail: 'openspec validate plus a coverage check; failures go back to drafting, bound 3' },
  ],
}

// ── args (supplied by the architect flow) ────────────────────────────────────
//   slug          : the OpenSpec change slug (required)
//   workdir       : the run's working directory holding packs/ (required)
//   proposalPath  : the approved proposal (required)
//   storeId       : OpenSpec store id, when the surface is a store
//   round         : which pack round to render (default: the highest present)
//   capabilities  : capability names the proposal declares — derived from the proposal if absent
//   decisions     : decisions agreed with the user, one line each
function parseArgs(raw) {
  if (raw == null) return {}
  if (typeof raw === 'object') return raw
  if (typeof raw !== 'string') return {}
  const text = raw.trim()
  if (text.startsWith('{')) {
    try { return JSON.parse(text) } catch (e) { /* not JSON after all */ }
  }
  return { slug: text.split(/\s+/)[0] || '' }
}

const A = parseArgs(typeof args === 'undefined' ? null : args)
const SLUG = A.slug || ''
const WORKDIR = (A.workdir || '').replace(/\/*$/, '/')
const PROPOSAL = A.proposalPath || ''
const STORE = A.storeId ? ' --store ' + A.storeId : ''
const ROUND = Number(A.round) > 0 ? Number(A.round) : 0
const DECLARED = Array.isArray(A.capabilities) ? A.capabilities : []
const DECISIONS = Array.isArray(A.decisions) ? A.decisions : []

function fence(s) {
  const body = String(s == null ? '' : s).replace(/<<<UNTRUSTED|UNTRUSTED>>>/g, '[fence marker stripped]')
  return '<<<UNTRUSTED\n' + body + '\nUNTRUSTED>>>'
}

if (!SLUG || !WORKDIR || !PROPOSAL) {
  return {
    status: 'blocked',
    reason: 'delta-specs needs slug, workdir and proposalPath. It is called from the architect flow after the consilium converged, not on its own.',
    received: A,
  }
}

const INSTRUCTIONS_CMD = 'openspec instructions specs --change ' + SLUG + STORE + ' --json'
const VALIDATE_CMD = 'openspec validate ' + SLUG + STORE

// ── Schemas ──────────────────────────────────────────────────────────────────

// Requirement TEXT never travels through this script. A requirement's only durable home is its
// pack file; an assignment references it by pack plus locator, so no second copy exists to
// drift from the first.
const PARTITION_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['capabilities', 'unassignable'],
  properties: {
    capabilities: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['capability', 'assignments'],
        properties: {
          capability: { type: 'string', description: 'A capability name the proposal declares, verbatim' },
          baselinePath: { type: 'string', description: 'Path of this capability baseline spec, empty when the capability is new' },
          assignments: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['packFile', 'locator', 'operation'],
              properties: {
                packFile: { type: 'string', description: 'File name under packs/ that states this requirement' },
                locator: { type: 'string', description: 'The requirement first words, enough to find it in the pack — NOT its full text' },
                operation: { type: 'string', enum: ['ADDED', 'MODIFIED', 'REMOVED', 'RENAMED'] },
                crossReferenceFrom: { type: 'string', description: 'Capability that also plausibly fits and gets a cross-reference instead of a copy' },
              },
            },
          },
        },
      },
    },
    unassignable: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['packFile', 'locator', 'why'],
        properties: {
          packFile: { type: 'string' },
          locator: { type: 'string' },
          why: { type: 'string', description: 'Why no declared capability owns it' },
        },
      },
    },
  },
}

const DRAFT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['capability', 'path', 'rendered'],
  properties: {
    capability: { type: 'string' },
    path: { type: 'string', description: 'The spec file written' },
    rendered: { type: 'number', description: 'How many requirements were rendered into it' },
    notes: { type: 'string', description: 'Anything the renderer could not do as instructed' },
  },
}

const VALIDATE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['passed', 'detail'],
  properties: {
    passed: { type: 'boolean', description: 'true only when the CLI is clean AND coverage is complete' },
    detail: { type: 'string', description: 'What was run and what came back' },
    failingCapabilities: { type: 'array', items: { type: 'string' }, description: 'Capabilities whose files must be re-drafted' },
    coverageGaps: { type: 'array', items: { type: 'string' }, description: 'Declared capability with no file, file for an undeclared capability, or a raised requirement that landed nowhere' },
    operational: { type: 'boolean', description: 'true when the CLI itself could not run' },
  },
}

// ── Partition ────────────────────────────────────────────────────────────────

phase('Partition')
const partition = await agent(
  'Assign every requirement the expert panel raised to exactly one capability.\n\n' +
  'Packs (the panel verdicts): every file under ' + WORKDIR + 'packs/' +
  (ROUND ? ' whose name starts with "r' + ROUND + '-"' : ' from the HIGHEST round number present — earlier rounds are superseded') + '.\n' +
  'Proposal (declares the capabilities this artifact may use): ' + PROPOSAL + '\n' +
  (DECLARED.length ? 'The proposal declares exactly these capabilities: ' + DECLARED.join(', ') + '\n' : 'Read the declared capabilities off the proposal.\n') +
  'Existing baselines: read openspec/specs/ for each capability that already exists, and report ' +
  'its baseline spec path — a MODIFIED delta is rendered against that block.\n\n' +
  'For every MUST requirement in every pack:\n' +
  '- Assign it to exactly ONE declared capability. One that plausibly fits two gets an owner ' +
  'plus a cross-reference from the other — never a copy in both.\n' +
  '- Decide its delta operation against the baseline you read: ADDED, MODIFIED, REMOVED, RENAMED.\n' +
  '- Identify it by its pack file name and a short locator (its first words). Do NOT copy the ' +
  'requirement text into your answer — it stays in the pack, which is where the renderer reads it.\n\n' +
  'A requirement that fits no declared capability goes in "unassignable" with the reason. Do NOT ' +
  'stretch a capability to fit it and do NOT invent a capability: that case means the proposal ' +
  'contract is wrong, which is decided elsewhere.\n' +
  'Only MUST items are requirements. A pack SHOULD item and its Angle narrative are advice and ' +
  'bind nothing — never assign them.\n' +
  'Write nothing to disk.',
  { label: 'partition', phase: 'Partition', schema: PARTITION_SCHEMA }
)

if (!partition) {
  return { status: 'blocked', gate: 'partition', question: 'Partition returned nothing usable.' }
}

if ((partition.unassignable || []).length) {
  return {
    status: 'stopped',
    gate: 'unassignable-requirements',
    question: 'Requirements the panel raised fit no capability the proposal declares. The proposal contract is wrong — widen it, or drop the requirements. This is the guardrail, not a fix the specs may make.',
    unassignable: partition.unassignable,
    slug: SLUG,
  }
}

const CAPS = (partition.capabilities || []).filter(function (c) { return c.capability && (c.assignments || []).length })
if (!CAPS.length) {
  return { status: 'blocked', gate: 'partition', question: 'Partition assigned no requirements to any capability — the packs are empty or unreadable.', packsDir: WORKDIR + 'packs/' }
}

log('Partitioned into ' + CAPS.length + ' capability file(s): ' + CAPS.map(function (c) { return c.capability + ' (' + c.assignments.length + ')' }).join(', '))

// ── Drafting ─────────────────────────────────────────────────────────────────
// One renderer per capability, in parallel: the files are independent by construction.

const VERBATIM_RULE =
  'The requirement body goes in VERBATIM, RFC keyword intact — no rewording, no tightening, no ' +
  'improving. Rewording is where meaning is lost, and the expert who wrote it will never see ' +
  'this file. The acceptance criterion becomes the scenario: that derivation IS interpretive ' +
  '(WHEN/THEN imposes event structure the criterion may not state literally), which is exactly ' +
  'why the requirement body itself stays untouched. A stated assumption becomes an explicit ' +
  'precondition.\n' +
  'Verbatim governs the requirement own text, not the boundary of the block around it: a ' +
  'MODIFIED delta carries the ENTIRE baseline requirement block, edited — take the boundary ' +
  'from the authoring instructions, the text from the pack.\n' +
  'Author WHAT the system does, observably; HOW it is built belongs to the design.\n' +
  'Source attribution NEVER appears in a spec file — it is the pack file name and stays in the workdir.'

function draft(cap, only) {
  const assignments = (cap.assignments || []).filter(function (a) { return !only || only.indexOf(a.locator) >= 0 })
  return agent(
    'Render the delta spec for capability "' + cap.capability + '" of change ' + SLUG + '.\n\n' +
    'Pull the authoring instructions first and follow them — the format lives in the CLI, not ' +
    'in this dispatch:\n  ' + INSTRUCTIONS_CMD + '\n\n' +
    'Your requirements, each identified by the pack that states it and its opening words. Read ' +
    'each one out of its pack file under ' + WORKDIR + 'packs/ and render it under the delta ' +
    'operation given:\n' + fence(JSON.stringify(assignments, null, 2)) + '\n\n' +
    (cap.baselinePath ? 'Baseline spec for this capability: ' + cap.baselinePath + '\n' : 'This capability has no baseline — every requirement is ADDED.\n') +
    (DECISIONS.length ? 'Decisions agreed with the user, which the document must carry:\n' + DECISIONS.map(function (d) { return '- ' + d }).join('\n') + '\n' : '') +
    '\n' + VERBATIM_RULE + '\n\n' +
    'Write the file the instructions name for this capability inside the change, and report its ' +
    'path plus how many requirements you rendered. Touch no other capability file.',
    { label: 'draft:' + cap.capability, phase: 'Drafting', schema: DRAFT_SCHEMA }
  )
}

phase('Drafting')
let drafted = (await parallel(CAPS.map(function (c) { return function () { return draft(c, null) } }))).filter(Boolean)

if (drafted.length < CAPS.length) {
  const missing = CAPS.filter(function (c) { return !drafted.some(function (d) { return d.capability === c.capability }) }).map(function (c) { return c.capability })
  return { status: 'blocked', gate: 'drafting', question: 'These capability files were not rendered: ' + missing.join(', '), drafted: drafted.map(function (d) { return d.path }) }
}

// ── Validation ───────────────────────────────────────────────────────────────
// The CLI decides, and fixing is drafting's work — so a failure re-enters Drafting for the
// named capabilities only, never for all of them.

phase('Validation')
let validation = null
let round = 0

for (;;) {
  round += 1

  validation = await agent(
    'Validate the delta specs of change ' + SLUG + '.\n\n' +
    '1. Run once:\n  ' + VALIDATE_CMD + '\n' +
    '2. Then check coverage yourself, because the CLI cannot: every capability the proposal at ' +
    PROPOSAL + ' declares has a file; no file exists for a capability it does not declare; and ' +
    'every requirement the packs under ' + WORKDIR + 'packs/ raise landed somewhere. ' +
    '"openspec status" marks the plural specs artifact done on the FIRST matching file — it ' +
    'cannot see a missing sibling or a dropped requirement.\n\n' +
    'The capabilities in play: ' + CAPS.map(function (c) { return c.capability }).join(', ') + '\n\n' +
    'Report passed=true only when the CLI is clean AND coverage is complete. Name the ' +
    'capabilities whose files must be re-drafted. Set operational=true if the CLI itself could ' +
    'not run. Fix nothing — fixing is the renderer job.',
    { label: 'validate-r' + round, phase: 'Validation', schema: VALIDATE_SCHEMA }
  )

  if (validation && validation.passed) break

  if (!validation || validation.operational) {
    return { status: 'blocked', gate: 'operational', question: 'openspec validate could not run: ' + ((validation && validation.detail) || 'the validator reported nothing usable'), slug: SLUG }
  }

  if (round >= 3) {
    return {
      status: 'stopped',
      gate: 'validation-cap',
      question: 'The delta specs still fail validation after 3 rounds. Present them with the outstanding findings named; the user decides.',
      detail: validation.detail,
      coverageGaps: validation.coverageGaps || [],
      failingCapabilities: validation.failingCapabilities || [],
      specs: drafted.map(function (d) { return d.path }),
    }
  }

  const failing = (validation.failingCapabilities || []).length
    ? CAPS.filter(function (c) { return validation.failingCapabilities.indexOf(c.capability) >= 0 })
    : CAPS

  log('Validation round ' + round + ' failed; re-drafting ' + failing.length + ' capability file(s)')

  const redrafted = (await parallel(failing.map(function (c) {
    return function () {
      return agent(
        'Re-render the delta spec for capability "' + c.capability + '" of change ' + SLUG + '. ' +
        'Validation rejected the current file.\n\n' +
        'What validation reported:\n' + fence(validation.detail) + '\n' +
        ((validation.coverageGaps || []).length ? 'Coverage gaps:\n' + fence(JSON.stringify(validation.coverageGaps, null, 2)) + '\n' : '') +
        '\nPull the authoring instructions and follow them:\n  ' + INSTRUCTIONS_CMD + '\n\n' +
        'Your requirements, read each out of its pack file under ' + WORKDIR + 'packs/:\n' +
        fence(JSON.stringify(c.assignments, null, 2)) + '\n' +
        (c.baselinePath ? 'Baseline: ' + c.baselinePath + '\n' : '') +
        '\n' + VERBATIM_RULE + '\n\n' +
        'Fix what validation named. A finding that would reword an expert requirement is a ' +
        'RENDERING question, never a wording one: the body stays verbatim. Touch no other ' +
        'capability file.',
        { label: 'redraft:' + c.capability + ':r' + round, phase: 'Validation', schema: DRAFT_SCHEMA }
      )
    }
  }))).filter(Boolean)

  if (!redrafted.length) {
    return { status: 'blocked', gate: 'drafting', question: 'The re-draft after validation round ' + round + ' produced nothing.', detail: validation.detail }
  }

  redrafted.forEach(function (r) {
    const i = drafted.findIndex(function (d) { return d.capability === r.capability })
    if (i >= 0) drafted[i] = r; else drafted.push(r)
  })
}

log('Delta specs validated: ' + drafted.length + ' capability file(s) after ' + round + ' validation round(s)')

return {
  status: 'ok',
  slug: SLUG,
  validationRounds: round,
  specs: drafted.map(function (d) { return { capability: d.capability, path: d.path, rendered: d.rendered } }),
  // Rendering notes are the one thing a renderer could not do as told — the architect
  // dispositions them; they are not findings and they block nothing.
  notes: drafted.filter(function (d) { return d.notes }).map(function (d) { return { capability: d.capability, note: d.notes } }),
}
