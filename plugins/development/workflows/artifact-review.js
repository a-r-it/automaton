export const meta = {
  name: 'artifact-review',
  description: 'Dispatches fresh eyes at one artifact of an OpenSpec change — a reviewer per target file plus an unconditional cross-model Codex reader — and returns the findings for the architect to disposition.',
  whenToUse: 'Called from the architect flow at a Review stage, for proposal, specs (one reviewer per capability file) or design. Codex always participates; a Codex that cannot be reached is reported as an absent reader, never hidden. Returns findings only: it never edits an artifact and never dispositions anything — disposition is the architect job and travels in the handback.',
  phases: [
    { title: 'Review', detail: 'Every reader dispatched in parallel against the current draft' },
    { title: 'Collect', detail: 'Findings merged, unreachable readers named rather than hidden' },
  ],
}

// ── args (supplied by the architect flow) ────────────────────────────────────
//   artifact   : 'proposal' | 'specs' | 'design'   (required)
//   slug       : the OpenSpec change slug          (required)
//   paths      : the file(s) under review — one per reviewer (required)
//   others     : the change other artifact paths, for context
//   decisions  : every choice and assumption settled with the user
//   storeId    : OpenSpec store id, when the surface is a store
//
// Codex is NOT an argument: every artifact gets the cross-model read. A second opinion the
// caller may forget to ask for is a second opinion that stops happening.
function parseArgs(raw) {
  if (raw == null) return {}
  if (typeof raw === 'object') return raw
  if (typeof raw !== 'string') return {}
  const text = raw.trim()
  if (text.startsWith('{')) {
    try { return JSON.parse(text) } catch (e) { /* not JSON after all */ }
  }
  return {}
}

const A = parseArgs(typeof args === 'undefined' ? null : args)
const ARTIFACT = A.artifact || ''
const SLUG = A.slug || ''
const PATHS = Array.isArray(A.paths) ? A.paths.filter(Boolean) : (A.paths ? [A.paths] : [])
const OTHERS = Array.isArray(A.others) ? A.others : []
const DECISIONS = Array.isArray(A.decisions) ? A.decisions : []
const STORE = A.storeId ? ' --store ' + A.storeId : ''

function fence(s) {
  const body = String(s == null ? '' : s).replace(/<<<UNTRUSTED|UNTRUSTED>>>/g, '[fence marker stripped]')
  return '<<<UNTRUSTED\n' + body + '\nUNTRUSTED>>>'
}

if (!ARTIFACT || !SLUG || !PATHS.length) {
  return {
    status: 'blocked',
    reason: 'artifact-review needs artifact, slug and at least one path. It is called from the architect flow at a Review stage.',
    received: A,
  }
}

const CONTRACT_CMD = 'openspec instructions ' + ARTIFACT + ' --change ' + SLUG + STORE + ' --json'

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verbatim', 'findings'],
  properties: {
    verbatim: { type: 'string', description: 'The complete review, exactly as written — persisted unchanged' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'finding'],
        properties: {
          severity: { type: 'string', enum: ['finding', 'recommendation'] },
          finding: { type: 'string' },
          where: { type: 'string', description: 'File and section or line the finding is about' },
          rewordsRequirement: { type: 'boolean', description: 'specs only: true when acting on this would reword an expert requirement body' },
        },
      },
    },
    available: { type: 'boolean', description: 'Codex reader only: false when the MCP tool could not be reached' },
    reason: { type: 'string', description: 'Codex reader only: why it was unavailable' },
  },
}

const decisionsBlock = DECISIONS.length
  ? DECISIONS.map(function (d) { return '- ' + d }).join('\n')
  : '- none recorded'

// ── Review ───────────────────────────────────────────────────────────────────
// Readers run together: they answer the same question from different angles, and running
// them in one round costs one round instead of several.

phase('Review')

const readers = PATHS.map(function (p) {
  return {
    kind: 'artifact-reviewer',
    target: p,
    run: function () {
      return agent(
        'Artifact: ' + ARTIFACT + '\n' +
        'Change: ' + SLUG + '\n' +
        'Path: ' + p + '\n' +
        'Contract: run exactly this command, and no others —\n  ' + CONTRACT_CMD + '\n' +
        'Other artifacts of this change: ' + (OTHERS.length ? OTHERS.join(', ') : 'none yet') + '\n' +
        'Decisions agreed with the user — the document must carry them; flag any that are ' +
        'missing or contradicted:\n' + fence(decisionsBlock) + '\n\n' +
        'Return your review complete and unaltered in the "verbatim" field, and list your ' +
        'findings separately from your recommendations.' +
        (ARTIFACT === 'specs'
          ? '\nMark rewordsRequirement on any finding whose fix would change an expert ' +
            'requirement body: that is a rendering question, not a wording one.'
          : ''),
        { label: 'review:' + p.split('/').slice(-2).join('/'), phase: 'Review', schema: FINDINGS_SCHEMA, agentType: 'development:artifact-reviewer' }
      )
    },
  }
})

// Unconditional, for every artifact: two readers answer the same question from different
// models, and running them together costs one round instead of two.
readers.push({
  kind: 'codex',
  target: PATHS[0],
  run: function () {
    return agent(
        'Consult Codex for a cross-model read of an OpenSpec artifact, then report what it ' +
        'found. You are a relay: you do not review the document yourself and you edit nothing.\n\n' +
        'First run ToolSearch with the query "select:mcp__codex__codex" to load the tool schema — ' +
        'it is not callable until you do. Then call mcp__codex__codex with EXACTLY these ' +
        'parameters:\n' +
        '  sandbox: "read-only"\n' +
        '  approval-policy: "never"\n' +
        '  (do NOT pass a model parameter — the Codex config decides)\n' +
        '  prompt: the ask below\n\n' +
        'Ask to send:\n' +
        '"Read-only review of an implementation ' + ARTIFACT + '. Paths: ' + PATHS.join(', ') +
        (OTHERS.length ? '; supporting artifacts: ' + OTHERS.join(', ') : '') + '. ' +
        'The other artifacts of this change are approved and fixed — do not propose changes to ' +
        'them. Report against the ' + ARTIFACT + ' only: requirements no decision covers, ' +
        'decisions that contradict each other or the specs, risks and failure modes the ' +
        'approach does not address, and anything the codebase makes unworkable as written."\n\n' +
        'Return the reply complete and unaltered in the "verbatim" field, plus its findings ' +
        'separated from its recommendations. If the tool cannot be reached or errors, report ' +
        'available:false with the reason and an empty findings array — do NOT fail, and do NOT ' +
        'substitute a review of your own.',
      { label: 'review:codex', phase: 'Review', schema: FINDINGS_SCHEMA }
    )
  },
})

const results = await parallel(readers.map(function (r) { return r.run }))

// ── Collect ──────────────────────────────────────────────────────────────────
// A reader that never ran is a hole, not a formality: it is named, never quietly dropped.

phase('Collect')

const ran = []
const absent = []

readers.forEach(function (r, i) {
  const res = results[i]
  const reached = !!(res && res.verbatim && res.available !== false)
  if (reached) ran.push({ reader: r.kind, target: r.target, result: res })
  else absent.push({ reader: r.kind, target: r.target, why: (res && res.reason) || 'the reader returned nothing' })
})

if (!ran.length) {
  return {
    status: 'blocked',
    gate: 'no-reader',
    question: 'No reader returned a review of ' + ARTIFACT + '. An artifact nobody read is not an artifact that passed.',
    absent: absent,
  }
}

await agent(
  'Persist these artifact reviews, each exactly as given — write the files and nothing else, ' +
  'and alter no text:\n\n' +
  ran.map(function (x) {
    const base = x.reader === 'codex' ? 'codex' : x.target.split('/').slice(-2).join('-').replace(/\.md$/, '')
    return 'File: ' + (A.workdir ? String(A.workdir).replace(/\/*$/, '/') : '') + 'reviews/' + ARTIFACT + '-' + base + '.md\n' + fence(x.result.verbatim)
  }).join('\n\n') +
  (absent.length ? '\n\nAlso record the readers that never ran, one line each, in the same directory as ' + ARTIFACT + '-absent.md:\n' + fence(JSON.stringify(absent, null, 2)) : ''),
  { label: 'persist-reviews', phase: 'Collect', effort: 'low' }
)

const findings = []
const recommendations = []
ran.forEach(function (x) {
  ;(x.result.findings || []).forEach(function (f) {
    const item = { reader: x.reader, target: x.target, where: f.where || '', finding: f.finding, rewordsRequirement: !!f.rewordsRequirement }
    if (f.severity === 'recommendation') recommendations.push(item); else findings.push(item)
  })
})

log(ARTIFACT + ' review: ' + findings.length + ' finding(s), ' + recommendations.length + ' recommendation(s)' + (absent.length ? ', ' + absent.length + ' reader(s) unreachable' : ''))

return {
  status: 'ok',
  artifact: ARTIFACT,
  slug: SLUG,
  readersRan: ran.map(function (x) { return x.reader + ' @ ' + x.target }),
  // Named, not hidden: a design one reader saw is not a design that passed two, and the gap
  // belongs in the approval message.
  readersAbsent: absent,
  findings: findings,
  recommendations: recommendations,
}
