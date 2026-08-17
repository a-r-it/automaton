export const meta = {
  name: 'feature',
  description: 'Autonomous feature development from an approved spec: plan, cross-model plan review, task-by-task implementation with per-task review and commits, then whole-branch review.',
  whenToUse: 'Invoked with the path to an approved spec (optionally a slug), e.g. "/development:feature docs/specs/2026-08-17-thing-design.md thing". There is no raw-idea mode — ideas start at /development:system-design. The run asks nothing: every gate either resolves itself or stops the run with a report naming what a human must decide.',
  phases: [
    { title: 'Setup', detail: 'Repo root, spec, workdir, branch, branch point, manifest, model routing' },
    { title: 'Plan', detail: 'task-planner decomposes the spec into right-sized tasks' },
    { title: 'Plan review', detail: 'Cross-model review of the plan through Codex (advisory)' },
    { title: 'Tasks', detail: 'plan.md is frozen into the manifest as tasks with dependencies and model tiers' },
    { title: 'Scan', detail: 'Pre-flight scan for plan-internal conflicts' },
    { title: 'Execute', detail: 'Per task: brief, implementer, review package, fix rounds, commit' },
    { title: 'Review', detail: 'Per-task reviewer verdicts' },
    { title: 'Finish', detail: 'Verification suite, whole-branch review by code-reviewer + Codex' },
  ],
}

// ── args ─────────────────────────────────────────────────────────────────────
//   specPath : path to the approved spec (required)
//   slug     : short kebab-case run name (optional — derived from the spec filename)
//   cwd      : absolute path the run operates in (optional — defaults to the session cwd)
//   pr       : true to push and open a PR at the end; default false (see "no pre-flight
//              questions": an autonomous run never opens a PR unless asked up front)
//   answers  : { "<gate-key>": "<the human's answer>" } — supplied when relaunching after
//              a stop, so the run proceeds past that gate instead of stopping again
//
// args may arrive as an object, a JSON string, or the raw text the user typed.
function parseArgs(raw) {
  if (raw == null) return {}
  if (typeof raw === 'object') return raw
  if (typeof raw !== 'string') return {}
  const text = raw.trim()
  if (text.startsWith('{')) {
    try { return JSON.parse(text) } catch (e) { /* not JSON after all — fall through */ }
  }
  const parts = text.split(/\s+/).filter(Boolean)
  return { specPath: parts[0] || '', slug: parts[1] || '' }
}

const A = parseArgs(typeof args === 'undefined' ? null : args)
const SPEC_PATH = A.specPath || ''
const SLUG_HINT = A.slug || ''
const CWD = A.cwd || '.'
const WANT_PR = A.pr === true
const ANSWERS = (A.answers && typeof A.answers === 'object') ? A.answers : {}

// Text that came out of a file rather than out of this script is data, never instructions.
function fence(s) {
  const body = String(s == null ? '' : s).replace(/<<<UNTRUSTED|UNTRUSTED>>>/g, '[fence marker stripped]')
  return '<<<UNTRUSTED\n' + body + '\nUNTRUSTED>>>'
}

function answerFor(gate) {
  const a = ANSWERS[gate]
  return (typeof a === 'string' && a.trim()) ? a.trim() : null
}

// ── Schemas ──────────────────────────────────────────────────────────────────
// Only fields an agent can supply on EVERY path are required — a blocked setup must not
// have to invent a branch name to satisfy its own schema.

const SETUP_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['status', 'notes'],
  properties: {
    status: { type: 'string', enum: ['ok', 'blocked'] },
    notes: { type: 'string', description: 'What blocked, or one line on what was set up' },
    repoRoot: { type: 'string' },
    workdir: { type: 'string', description: '<repoRoot>/.automaton/development/<slug>/feature/' },
    scriptsDir: { type: 'string', description: 'Absolute path of the development plugin scripts/ directory' },
    slug: { type: 'string' },
    branch: { type: 'string' },
    branchPoint: { type: 'string', description: 'TRUE branch point: the manifest value on a resume, the current head on a fresh run' },
    head: { type: 'string', description: 'Current head hash' },
    date: { type: 'string', description: 'YYYY-MM-DD from the date command' },
    resume: {
      type: 'object',
      additionalProperties: false,
      required: ['isResume', 'mismatch', 'completedTasks', 'planExists', 'tasksIndexed'],
      properties: {
        isResume: { type: 'boolean' },
        mismatch: { type: 'string', description: 'Empty when the manifest agrees with git; otherwise what diverged' },
        completedTasks: { type: 'array', items: { type: 'number' }, description: 'Tasks recorded reviewed AND whose commits all exist' },
        planExists: { type: 'boolean' },
        tasksIndexed: { type: 'boolean', description: 'true when the manifest already carries the frozen decomposition' },
      },
    },
    modelRouting: {
      type: 'object',
      additionalProperties: false,
      required: ['found', 'mechanical', 'standard', 'frontier'],
      properties: {
        found: { type: 'boolean', description: 'false = omit the model param on every dispatch for the whole run' },
        mechanical: { type: 'string' },
        standard: { type: 'string' },
        frontier: { type: 'string' },
      },
    },
  },
}

const RECORD_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'detail'],
  properties: {
    ok: { type: 'boolean' },
    detail: { type: 'string', description: 'One line: what was done, or why it could not be' },
    path: { type: 'string', description: 'The file this call produced, when it produced one' },
    hash: { type: 'string', description: 'The commit hash this call recorded, when it recorded one' },
  },
}

const PLAN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['status'],
  properties: {
    status: { type: 'string', enum: ['DONE', 'NEEDS_CONTEXT', 'BLOCKED'] },
    planPath: { type: 'string' },
    taskCount: { type: 'number' },
    tierSplit: { type: 'string', description: 'e.g. "4 mechanical, 2 standard, 1 frontier"' },
    ambiguities: { type: 'array', items: { type: 'string' }, description: 'Ambiguities the planner resolved on its own, one line each' },
    blocker: { type: 'string', description: 'Specifics when NEEDS_CONTEXT or BLOCKED' },
  },
}

const CODEX_PLAN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['available', 'findings'],
  properties: {
    available: { type: 'boolean', description: 'false when the Codex MCP tool could not be reached' },
    reason: { type: 'string', description: 'Why Codex was unavailable' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['axis', 'severity', 'finding', 'planText'],
        properties: {
          axis: { type: 'string', enum: ['spec-coverage', 'decomposition', 'dependency-order', 'verify-realism'] },
          severity: { type: 'string', enum: ['material', 'minor'] },
          finding: { type: 'string' },
          planText: { type: 'string', description: 'The plan text the finding is about, quoted' },
          question: { type: 'string', description: 'For material findings: what the human must decide' },
        },
      },
    },
  },
}

const TASKS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['tasks', 'globalConstraints'],
  properties: {
    globalConstraints: { type: 'string', description: 'The plan header Global Constraints block, copied verbatim' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['n', 'subject', 'blockedBy', 'modelTier', 'files', 'verifyCommand'],
        properties: {
          n: { type: 'number' },
          subject: { type: 'string' },
          blockedBy: { type: 'array', items: { type: 'number' } },
          modelTier: { type: 'string', enum: ['mechanical', 'standard', 'frontier'] },
          files: { type: 'array', items: { type: 'string' } },
          verifyCommand: { type: 'string' },
        },
      },
    },
  },
}

const SCAN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['conflicts'],
  properties: {
    conflicts: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['kind', 'finding', 'planText', 'question'],
        properties: {
          kind: { type: 'string', enum: ['task-vs-task', 'task-vs-constraints', 'plan-mandates-defect', 'planner-self-resolution'] },
          finding: { type: 'string' },
          planText: { type: 'string' },
          question: { type: 'string' },
        },
      },
    },
  },
}

const IMPL_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['status'],
  properties: {
    status: { type: 'string', enum: ['DONE', 'DONE_WITH_CONCERNS', 'NEEDS_CONTEXT', 'BLOCKED'] },
    commits: { type: 'array', items: { type: 'string' }, description: 'Short hash + subject per commit created' },
    testSummary: { type: 'string' },
    concerns: { type: 'array', items: { type: 'string' } },
    reportPath: { type: 'string' },
    detail: { type: 'string', description: 'Specifics when NEEDS_CONTEXT or BLOCKED — the question or the blocker' },
  },
}

const FINDING_ITEMS = {
  type: 'object',
  additionalProperties: false,
  required: ['severity', 'file', 'line', 'issue'],
  properties: {
    severity: { type: 'string', enum: ['Critical', 'Important', 'Minor'] },
    file: { type: 'string' },
    line: { type: 'string' },
    issue: { type: 'string' },
    planMandated: { type: 'boolean', description: 'true when the plan or brief explicitly mandates what this finding calls a defect' },
    planText: { type: 'string', description: 'The mandating plan text, when planMandated' },
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verbatim', 'specCompliant', 'quality', 'findings', 'cannotVerify'],
  properties: {
    verbatim: { type: 'string', description: 'The complete verdict, exactly as written — persisted to disk unchanged' },
    specCompliant: { type: 'boolean' },
    quality: { type: 'string', enum: ['Approved', 'Needs fixes'] },
    findings: { type: 'array', items: FINDING_ITEMS },
    cannotVerify: { type: 'array', items: { type: 'string' }, description: 'Requirements not verifiable from this diff alone' },
  },
}

const SUITE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['passed', 'detail'],
  properties: {
    passed: { type: 'boolean' },
    detail: { type: 'string', description: 'What was run and what came back' },
    failures: { type: 'array', items: { type: 'string' }, description: 'One line per failing command' },
    operational: { type: 'boolean', description: 'true when the failure is tooling/auth, not the code' },
  },
}

const BRANCH_REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verbatim', 'findings'],
  properties: {
    verbatim: { type: 'string' },
    findings: { type: 'array', items: FINDING_ITEMS },
    available: { type: 'boolean', description: 'Codex arm only: false when the MCP tool could not be reached' },
    reason: { type: 'string', description: 'Codex arm only: why it was unavailable' },
  },
}

// ── Run state ────────────────────────────────────────────────────────────────

let REPO_ROOT = CWD
let WORKDIR = ''
let SCRIPTS_DIR = ''
let DATE = 'unknown-date'
let BRANCH = ''
let BRANCH_POINT = ''
let ROUTING = { found: false, mechanical: 'inherit', standard: 'inherit', frontier: 'inherit' }

// Decisions a human already made — carried into every implementer dispatch so a resolved
// gate never has to be resolved twice.
const HELD = []

const GIT_CONTRACT =
  'No broad staging — ever. No "git add -A", no "git add .", no "commit -a". Stage ONLY the ' +
  'files your task created or modified, by path. Your task ends with a commit of exactly ' +
  'those files. All git commands run noninteractively.'

// "inherit" and a missing routing file both mean: omit the model param entirely, so the
// dispatch runs on the session model.
function modelFor(tier) {
  if (!ROUTING.found) return null
  const name = ROUTING[tier] || ROUTING.standard
  return (!name || name === 'inherit') ? null : name
}

function routed(base, tier) {
  const model = modelFor(tier)
  return model ? Object.assign({}, base, { model }) : base
}

// The script has no filesystem and no shell: every durable side effect is an agent.
function record(instructions, label, phaseName) {
  return agent(
    'You are the bookkeeper for a feature-development run. Repo root: ' + REPO_ROOT + '. ' +
    'Run workdir: ' + WORKDIR + '.\n\n' +
    'Do exactly what is listed below and nothing else — no code changes, no commits of your ' +
    'own, no tidying. Every manifest write is atomic: write manifest.json.tmp, then rename it ' +
    'over manifest.json. All commands run noninteractively. If a step cannot be completed, ' +
    'report ok:false and say which one.\n\n' + instructions,
    routed({ label: label, phase: phaseName, schema: RECORD_SCHEMA, effort: 'low' }, 'mechanical')
  )
}

// A stop ends the run. It leaves a report behind naming what a human must decide, and
// returns the same question as data.
async function stop(gate, question, detail) {
  if (WORKDIR) {
    await record(
      'Write ' + WORKDIR + 'stop-' + gate + '.md describing why this run stopped.\n' +
      'Gate: ' + gate + '\n' +
      'Question for the human:\n' + fence(question) + '\n' +
      'Supporting detail:\n' + fence(JSON.stringify(detail || {}, null, 2)) + '\n' +
      'Also append one line to ' + WORKDIR + 'progress.md recording the stop.\n' +
      'End the file with how to resume: relaunch "/development:feature ' + SPEC_PATH +
      (SLUG_HINT ? ' ' + SLUG_HINT : '') + '" with the answer supplied as ' +
      'args.answers["' + gate + '"].',
      'stop:' + gate, 'Finish'
    )
  }
  log('STOPPED at gate "' + gate + '" — ' + question)
  return {
    status: 'stopped',
    gate: gate,
    question: question,
    detail: detail || null,
    workdir: WORKDIR || null,
    branch: BRANCH || null,
    branchPoint: BRANCH_POINT || null,
    specPath: SPEC_PATH,
    resumeWith: 'args.answers["' + gate + '"]',
  }
}

if (!SPEC_PATH) {
  return await stop(
    'no-spec',
    'This flow needs the path to an approved spec. There is no raw-idea mode — ideas start at /development:system-design.',
    { received: A }
  )
}

// ── Setup ────────────────────────────────────────────────────────────────────

phase('Setup')
const setup = await agent(
  'You are performing setup for a feature-development run in ' + CWD + '.\n\n' +
  'Spec path (as given): ' + SPEC_PATH + '\n' +
  'Slug hint (may be empty): ' + (SLUG_HINT || '(none — derive one)') + '\n\n' +
  'Report status "blocked" with an explanatory note the moment any step cannot be ' +
  'completed — never guess your way past a failure.\n\n' +
  '1. Repo root: "git rev-parse --show-toplevel". Failure = blocked.\n' +
  '2. Date: run "date +%F" and report it.\n' +
  '3. Read the spec at the given path in full. Missing or unreadable = blocked.\n' +
  '4. Slug: the hint if non-empty, else a short kebab-case slug from the spec filename. ' +
  'The workdir is ALWAYS <repoRoot>/.automaton/development/<slug>/feature/ — report it ' +
  'with its trailing slash.\n' +
  '5. Locate the development plugin scripts directory (it holds "task-brief" and ' +
  '"review-package"): try $CLAUDE_PLUGIN_ROOT/scripts, then any ' +
  '.../plugins/development/scripts under ~/.claude, then <repoRoot>/plugins/development/scripts. ' +
  'Report the first one that contains BOTH executables. None found = blocked.\n' +
  '6. Ensure the repo-root .gitignore contains the anchored line "/.automaton/", appending ' +
  'it if missing. Do this on EVERY run, resume included. Leave .gitignore UNCOMMITTED.\n' +
  '7. Resume check: if <workdir>/manifest.json exists, this is a resume. Read it, switch to ' +
  'its branch, and reconcile every commit hash it records against git ' +
  '("git rev-parse --verify --quiet <hash>"). completedTasks = the task numbers it records ' +
  'as "reviewed" AND whose commits all exist. Set mismatch to one line if the spec path ' +
  'differs, the branch is missing, or head drifted from lastRecordedHead — otherwise leave ' +
  'mismatch empty. Report planExists for <workdir>plan.md, and tasksIndexed = true when the ' +
  'manifest tasks array is non-empty AND its entries carry a "subject" (the frozen ' +
  'decomposition), false when it is empty or holds progress fields only.\n' +
  '8. branchPoint: on a resume this is the manifest\'s existing branchPoint, read as-is and ' +
  'NEVER overwritten. On a fresh run it is the current head. Report head separately.\n' +
  '9. Fresh run only: "mkdir -p" the workdir, create and switch to branch feature/<slug> ' +
  '(switch to it if it already exists), and write <workdir>manifest.json atomically ' +
  '(manifest.json.tmp, then rename) as: {"spec":{"path":...},"repoRoot":...,"slug":...,' +
  '"branch":...,"branchPoint":<branchPoint>,"lastRecordedHead":<head>,"globalConstraints":"",' +
  '"tasks":[],"finish":null}. On a resume: preserve spec, branchPoint, globalConstraints, ' +
  'tasks and finish exactly as they are, and refresh only lastRecordedHead.\n' +
  '10. Write or append <workdir>progress.md with a header line naming the run and the date.\n' +
  '11. Model routing: read <repoRoot>/.automaton/development/model-routing.json, else ' +
  '~/.automaton/development/model-routing.json — first found wins entirely. Report found=true ' +
  'plus the model each of the three tiers maps to (the literal string "inherit" means "use ' +
  'the session model"). Absent or unparseable = found:false and all three tiers "inherit".\n\n' +
  'Verify what you wrote: the workdir, manifest.json and progress.md must exist on disk ' +
  'before you report ok. All git commands run noninteractively.',
  { label: 'setup', phase: 'Setup', schema: SETUP_SCHEMA }
)

if (!setup || setup.status !== 'ok') {
  return await stop('setup', (setup && setup.notes) || 'Setup failed and reported nothing usable.', { setup: setup || null })
}

REPO_ROOT = setup.repoRoot || CWD
WORKDIR = (setup.workdir || '').replace(/\/*$/, '/')   // never trust the trailing slash
SCRIPTS_DIR = (setup.scriptsDir || '').replace(/\/*$/, '/')
DATE = setup.date || DATE
BRANCH = setup.branch || ''
BRANCH_POINT = setup.branchPoint || ''
ROUTING = setup.modelRouting || ROUTING
const RESUME = setup.resume || { isResume: false, mismatch: '', completedTasks: [], planExists: false, tasksIndexed: false }

if (!WORKDIR || !BRANCH_POINT || !SCRIPTS_DIR) {
  return await stop('setup', 'Setup reported ok but left the workdir, branch point, or scripts directory empty.', { setup: setup })
}

// A manifest that disagrees with the working tree is a human decision: continuing could
// re-implement completed work.
if (RESUME.isResume && RESUME.mismatch && !answerFor('resume-mismatch')) {
  return await stop('resume-mismatch', 'Resume state disagrees with the repository: ' + RESUME.mismatch, { resume: RESUME })
}
if (answerFor('resume-mismatch')) HELD.push('Resume mismatch resolved by the human: ' + answerFor('resume-mismatch'))

const PLAN_PATH = WORKDIR + 'plan.md'
const BRIEF_SCRIPT = '"' + SCRIPTS_DIR + 'task-brief"'
const PACKAGE_SCRIPT = '"' + SCRIPTS_DIR + 'review-package"'

log('Run ' + setup.slug + ' on ' + BRANCH + (RESUME.isResume ? ' (resume, ' + (RESUME.completedTasks || []).length + ' task(s) already done)' : ' (fresh)'))

// ── Plan ─────────────────────────────────────────────────────────────────────
// Never re-planned on a resume: a second decomposition would renumber tasks out from
// under the ones already committed.

let planAmbiguities = []

if (!RESUME.planExists) {
  phase('Plan')
  const plan = await agent(
    'Write the implementation plan for this feature-development run.\n\n' +
    'Spec path: ' + SPEC_PATH + '\n' +
    'Plan file path ([PLAN_FILE]): ' + PLAN_PATH + '\n' +
    'Decisions already held by the orchestrator: ' + (HELD.length ? HELD.join(' | ') : 'none') + '\n\n' +
    'Read the spec fully, explore the codebase, and write the plan to [PLAN_FILE]. Report ' +
    'NEEDS_CONTEXT or BLOCKED rather than guessing past unclear requirements — put the ' +
    'specifics in the blocker field.',
    { label: 'task-planner', phase: 'Plan', schema: PLAN_SCHEMA, agentType: 'development:task-planner' }
  )

  if (!plan || plan.status !== 'DONE') {
    return await stop('planner-blocked', (plan && plan.blocker) || 'The task-planner did not return a usable plan.', { plan: plan || null })
  }
  planAmbiguities = plan.ambiguities || []
  log('Plan written: ' + (plan.taskCount || '?') + ' tasks (' + (plan.tierSplit || 'tiers unreported') + ')')
}

// ── Plan review ──────────────────────────────────────────────────────────────
// Cross-model review of the plan, advisory. Material findings join the plan-conflict stop;
// minor ones go to the ledger. An unreachable Codex is a ledger line, never a stop.

let codexPlanFindings = []

if (!RESUME.planExists) {
  phase('Plan review')
  const codexPlan = await agent(
    'Consult Codex for a cross-model review of an implementation plan, then report what it ' +
    'found. You are a relay: you do not review the plan yourself and you edit nothing.\n\n' +
    'First run ToolSearch with the query "select:mcp__codex__codex" to load the tool schema — ' +
    'it is not callable until you do. Then call mcp__codex__codex with EXACTLY these ' +
    'parameters:\n' +
    '  cwd: "' + REPO_ROOT + '"\n' +
    '  sandbox: "read-only"\n' +
    '  approval-policy: "never"\n' +
    '  (do NOT pass a model parameter — the Codex config decides)\n' +
    '  prompt: the review brief below\n\n' +
    'Review brief to send:\n' +
    '"Read the approved spec at ' + SPEC_PATH + ' and the implementation plan at ' + PLAN_PATH + '. ' +
    'Judge the plan against the spec on four axes: spec coverage (a requirement with no task), ' +
    'decomposition (a task too large to review as one unit, or split where it need not be), ' +
    'dependency order (a task consuming an interface no earlier task produces), and ' +
    'verify-command realism (a command that cannot run in this repo, or that would pass ' +
    'without proving the acceptance criteria). Report findings only, each quoting the plan ' +
    'text it is about. Do not edit either file. Do not propose an implementation."\n\n' +
    'The planner reported resolving these ambiguities on its own — judge them too:\n' +
    fence(JSON.stringify(planAmbiguities)) + '\n\n' +
    'Classify each finding material (changes what gets built) or minor (worth noting). ' +
    'If the Codex tool cannot be reached or errors, report available:false with the reason ' +
    'and an empty findings array — do NOT fail, and do NOT substitute your own review.',
    routed({ label: 'codex:plan-review', phase: 'Plan review', schema: CODEX_PLAN_SCHEMA }, 'standard')
  )

  if (!codexPlan || codexPlan.available === false) {
    const why = (codexPlan && codexPlan.reason) || 'relay returned nothing'
    log('Codex plan review unavailable: ' + why)
    await record('Append one line to ' + WORKDIR + 'progress.md: "Codex plan review skipped — ' + why + '".', 'ledger:codex-plan', 'Plan review')
  } else {
    codexPlanFindings = codexPlan.findings || []
    const minor = codexPlanFindings.filter(function (f) { return f.severity === 'minor' })
    log('Codex plan review: ' + codexPlanFindings.length + ' finding(s), ' + minor.length + ' minor')
    if (minor.length) {
      await record(
        'Append to ' + WORKDIR + 'progress.md a "Codex plan review — minor findings" block ' +
        'listing these verbatim, one per line:\n' + fence(JSON.stringify(minor, null, 2)),
        'ledger:codex-minor', 'Plan review'
      )
    }
  }
}

// ── Tasks ────────────────────────────────────────────────────────────────────
// Native TaskCreate is deliberately not used: the Task tools sit behind an experimental
// flag a plugin consumer will not have. The manifest is the authoritative record.

// The decomposition is frozen on disk because parsing prose into tasks is an LLM step: a
// second parse can renumber, and the completed-task set is keyed on those numbers. It lives
// IN the manifest — one file, one writer, so a tier or a status can never be half-updated.

phase('Tasks')
const taskIndex = RESUME.tasksIndexed
  ? await agent(
      'Read the manifest at ' + WORKDIR + 'manifest.json and report the frozen decomposition ' +
      'it stores: its tasks array (n, subject, blockedBy, modelTier, files, verifyCommand per ' +
      'task) and its globalConstraints string. Report them exactly as stored — do not ' +
      're-derive anything from the plan, and do not write anything.',
      routed({ label: 'read-tasks', phase: 'Tasks', schema: TASKS_SCHEMA, effort: 'low' }, 'mechanical')
    )
  : await agent(
      'Read the implementation plan at ' + PLAN_PATH + ' and turn it into structured data.\n\n' +
      'For every "### Task N:" section extract: the task number, its subject, the task numbers ' +
      'it depends on (from the Interfaces "consumes" entries and any explicit ordering the plan ' +
      'states), its modelTier from the task json:metadata fence, its files list, and its verify ' +
      'command. A task whose metadata is absent or carries an invalid tier gets tier "standard".\n\n' +
      'Also copy the plan header Global Constraints block VERBATIM — it is passed to every ' +
      'reviewer as the binding project rules.\n\n' +
      'Then write that decomposition INTO ' + WORKDIR + 'manifest.json, atomically ' +
      '(manifest.json.tmp, then rename): set globalConstraints to the copied block, and set ' +
      'tasks to one entry per task carrying n, subject, blockedBy, modelTier, files, ' +
      'verifyCommand, plus phase "pending" and base/head null. Preserve every other manifest ' +
      'field. Read the file back to confirm it parses, then report the same task array you wrote.',
      routed({ label: 'index-tasks', phase: 'Tasks', schema: TASKS_SCHEMA }, 'standard')
    )

const TASKS = (taskIndex && taskIndex.tasks) || []
const GLOBAL_CONSTRAINTS = (taskIndex && taskIndex.globalConstraints) || ''

if (!TASKS.length) {
  return await stop('empty-plan', 'The plan at ' + PLAN_PATH + ' produced no tasks. Revise the spec or the plan.', { planPath: PLAN_PATH })
}

// ── Scan ─────────────────────────────────────────────────────────────────────
// Conflicts are surfaced, never resolved here: "which governs, the plan or the rubric?" is
// a human decision.

if (!RESUME.planExists) {
  phase('Scan')
  const scan = await agent(
    'Pre-flight conflict scan of the implementation plan at ' + PLAN_PATH + '.\n\n' +
    'Look for exactly four kinds of conflict and report nothing else:\n' +
    '- task-vs-task: two tasks that contradict each other (incompatible signatures, one undoing another).\n' +
    '- task-vs-constraints: a task that violates the plan\'s own Global Constraints.\n' +
    '- plan-mandates-defect: something the plan mandates that a code-quality review would ' +
    'treat as a defect (duplicated logic blocks, swallowed errors, tests asserting nothing).\n' +
    '- planner-self-resolution: an ambiguity the planner resolved on its own in a way that ' +
    'changes what the spec requires.\n\n' +
    'The planner reported resolving these ambiguities:\n' + fence(JSON.stringify(planAmbiguities)) + '\n' +
    'Judge each against the spec at ' + SPEC_PATH + '.\n\n' +
    'For each conflict, quote the plan text that mandates it and phrase the question the human ' +
    'must answer. Do NOT resolve conflicts yourself. A clean plan is an empty conflicts array.',
    routed({ label: 'conflict-scan', phase: 'Scan', schema: SCAN_SCHEMA }, 'standard')
  )

  const conflicts = ((scan && scan.conflicts) || []).concat(
    codexPlanFindings
      .filter(function (f) { return f.severity === 'material' })
      .map(function (f) {
        return { kind: 'planner-self-resolution', finding: '[codex/' + f.axis + '] ' + f.finding, planText: f.planText || '', question: f.question || 'Does the plan stand as written?' }
      })
  )

  if (conflicts.length && !answerFor('plan-conflicts')) {
    return await stop(
      'plan-conflicts',
      'The plan has ' + conflicts.length + ' unresolved conflict(s). For each: which governs — the plan as written, or the finding?',
      { conflicts: conflicts }
    )
  }
  if (conflicts.length) log('Plan conflicts carried by a human answer: ' + conflicts.length)
}

if (answerFor('plan-conflicts')) HELD.push('Plan conflicts resolved by the human: ' + answerFor('plan-conflicts'))

// ── Execute ──────────────────────────────────────────────────────────────────
// Implementers are strictly serial: one shared checkout cannot host concurrent writers.

phase('Execute')

const DONE = new Set(RESUME.completedTasks || [])

function nextTask() {
  for (const t of TASKS) {
    if (DONE.has(t.n)) continue
    const blocked = (t.blockedBy || []).some(function (b) { return !DONE.has(b) })
    if (!blocked) return t
  }
  return null
}

function heldBlock() {
  return HELD.length ? 'Decisions already made — treat these as binding:\n' + HELD.map(function (h) { return '- ' + h }).join('\n') + '\n\n' : ''
}

function implementerPrompt(task, briefPath, reportPath, extra) {
  return 'Task ' + task.n + ' of ' + TASKS.length + ' in the run on branch ' + BRANCH + ': ' + task.subject + '.\n\n' +
    'Read ' + briefPath + ' first — it is your requirements ([BRIEF_FILE]), with the exact ' +
    'values to use verbatim.\n\n' + heldBlock() + (extra || '') +
    'Write your full report to ' + reportPath + ' ([REPORT_FILE]); the short summary comes back ' +
    'to me. ' + GIT_CONTRACT
}

let task
while ((task = nextTask())) {
  const n = task.n
  const briefPath = WORKDIR + 'task-' + n + '-brief.md'
  const reportPath = WORKDIR + 'task-' + n + '-report.md'
  let tier = task.modelTier || 'standard'

  const start = await record(
    'Prepare task ' + n + ':\n' +
    '1. Run: ' + BRIEF_SCRIPT + ' ' + PLAN_PATH + ' ' + n + ' ' + WORKDIR + '\n' +
    '2. Record the current head hash and report it as "hash" — this is the task BASE.\n' +
    '3. In manifest.json set this task entry to phase "implementing" with base = that hash ' +
    '(create the entry if absent), and save the manifest atomically BEFORE reporting.\n' +
    'Report the brief file path as "path".',
    'task-' + n + ':start', 'Execute'
  )
  if (!start || !start.ok || !start.hash) {
    return await stop('operational', 'Could not prepare task ' + n + ': ' + ((start && start.detail) || 'the bookkeeper reported nothing usable.'), { task: n, start: start || null })
  }
  const base = start.hash

  // ── implement, with the escalation ladder on BLOCKED ──
  let impl = null
  let escalated = false
  for (;;) {
    impl = await agent(implementerPrompt(task, briefPath, reportPath, ''), routed({ label: 'task-' + n + ':implement', phase: 'Execute', schema: IMPL_SCHEMA, agentType: 'development:implementer' }, tier))

    if (impl && (impl.status === 'DONE' || impl.status === 'DONE_WITH_CONCERNS')) break

    const detail = (impl && impl.detail) || 'the implementer returned nothing usable'

    if (impl && impl.status === 'NEEDS_CONTEXT') {
      const answered = answerFor('task-' + n + '-context')
      if (!answered) {
        return await stop('task-' + n + '-context', 'Task ' + n + ' needs context the brief does not carry: ' + detail, { task: n, question: detail, briefPath: briefPath })
      }
      HELD.push('Task ' + n + ' context, supplied by the human: ' + answered)
      continue
    }

    // BLOCKED: try one tier escalation before involving a human.
    const answered = answerFor('task-' + n + '-blocked')
    if (answered) { HELD.push('Task ' + n + ' blocker resolved by the human: ' + answered); continue }
    if (!escalated && tier !== 'frontier') {
      escalated = true
      tier = (tier === 'mechanical') ? 'standard' : 'frontier'
      await record(
        'Task ' + n + ' is escalating to model tier "' + tier + '". Set modelTier on its entry ' +
        'in manifest.json, atomically, then report.',
        'task-' + n + ':escalate', 'Execute'
      )
      log('Task ' + n + ' BLOCKED — escalating to tier ' + tier)
      continue
    }
    return await stop('task-' + n + '-blocked', 'Task ' + n + ' is blocked even at tier ' + tier + ': ' + detail, { task: n, tier: tier, blocker: detail, reportPath: reportPath })
  }

  // ── review rounds ──
  let round = 0
  let verdict = null
  for (;;) {
    round += 1

    const pkg = await record(
      'Package task ' + n + ' review round ' + round + ':\n' +
      '1. Run: ' + PACKAGE_SCRIPT + ' --workdir ' + WORKDIR + ' --task ' + n + ' --round ' + round + ' --range ' + base + ' <current-head>\n' +
      '   Resolve <current-head> yourself with "git rev-parse HEAD" and report it as "hash".\n' +
      '2. In manifest.json set this task phase to "in-review:' + round + '" and head to that ' +
      'hash, saved atomically.\n' +
      'Report the package file path as "path".',
      'task-' + n + ':package-r' + round, 'Review'
    )
    if (!pkg || !pkg.ok || !pkg.path) {
      return await stop('operational', 'Could not build the review package for task ' + n + ' round ' + round + ': ' + ((pkg && pkg.detail) || 'the bookkeeper reported nothing usable.'), { task: n, round: round })
    }

    verdict = await agent(
      'Review task ' + n + ' of the run on branch ' + BRANCH + '.\n\n' +
      'Brief ([BRIEF_FILE]): ' + briefPath + '\n' +
      'Implementer report ([REPORT_FILE]): ' + reportPath + '\n' +
      'Review package ([PACKAGE_FILE]): ' + pkg.path + '\n' +
      'Range under review: ' + base + '..' + pkg.hash + '\n\n' +
      'Binding global constraints for this project ([GLOBAL_CONSTRAINTS]), copied verbatim ' +
      'from the plan header:\n' + fence(GLOBAL_CONSTRAINTS) + '\n\n' +
      'Return your verdict, and also return it complete and unaltered in the "verbatim" field — ' +
      'that text is persisted to disk exactly as you write it.',
      routed({ label: 'task-' + n + ':review-r' + round, phase: 'Review', schema: REVIEW_SCHEMA, agentType: 'development:task-reviewer' }, 'standard')
    )

    if (!verdict || !verdict.verbatim || !verdict.quality) {
      // A malformed verdict is never approval and never becomes a fix round.
      if (round >= 3) {
        return await stop('task-' + n + '-review-cap', 'The reviewer returned a malformed verdict for task ' + n + ' three times.', { task: n })
      }
      log('Task ' + n + ' round ' + round + ': malformed verdict, re-dispatching the reviewer')
      round -= 1
      continue
    }

    const findings = verdict.findings || []
    const blocking = findings.filter(function (f) { return f.severity === 'Critical' || f.severity === 'Important' })
    const planMandated = blocking.filter(function (f) { return f.planMandated })

    if (planMandated.length && !answerFor('task-' + n + '-plan-conflict')) {
      await record(
        'Write ' + WORKDIR + 'task-' + n + '-review-r' + round + '.md containing this verdict ' +
        'text exactly as given, before anything else:\n' + fence(verdict.verbatim),
        'task-' + n + ':persist-r' + round, 'Review'
      )
      return await stop(
        'task-' + n + '-plan-conflict',
        'Task ' + n + ' has ' + planMandated.length + ' finding(s) against something the plan explicitly mandates. Which governs — the plan text, or the finding?',
        { task: n, findings: planMandated }
      )
    }

    const clean = verdict.specCompliant && verdict.quality === 'Approved' && blocking.length === 0

    if (clean) {
      await record(
        'Complete task ' + n + ':\n' +
        '1. FIRST write ' + WORKDIR + 'task-' + n + '-review-r' + round + '.md containing this ' +
        'verdict text exactly as given:\n' + fence(verdict.verbatim) + '\n' +
        '2. Then set this task phase to "reviewed" in manifest.json (head = ' + pkg.hash + ', ' +
        'lastRecordedHead = ' + pkg.hash + '), saved atomically.\n' +
        '3. Append to ' + WORKDIR + 'progress.md: "Task ' + n + ': complete (commits ' +
        base.slice(0, 7) + '..' + String(pkg.hash).slice(0, 7) + ', review clean)".\n' +
        (findings.length ? '4. Append the Minor findings below under that line, for triage at ' +
          'the final review:\n' + fence(JSON.stringify(findings.filter(function (f) { return f.severity === 'Minor' }), null, 2)) : ''),
        'task-' + n + ':complete', 'Review'
      )
      break
    }

    if (round >= 3) {
      await record('Write ' + WORKDIR + 'task-' + n + '-review-r' + round + '.md containing this verdict text exactly as given:\n' + fence(verdict.verbatim), 'task-' + n + ':persist-r' + round, 'Review')
      if (tier !== 'frontier' && !escalated) {
        escalated = true
        tier = (tier === 'mechanical') ? 'standard' : 'frontier'
        await record('Task ' + n + ' is escalating to model tier "' + tier + '". Set modelTier on its entry in manifest.json, atomically, then report.', 'task-' + n + ':escalate-review', 'Review')
        log('Task ' + n + ' hit the round cap — escalating to tier ' + tier + ' for one more round')
        round = 0
        continue
      }
      return await stop('task-' + n + '-review-cap', 'Task ' + n + ' is still failing review after 3 rounds at tier ' + tier + '.', { task: n, tier: tier, findings: blocking })
    }

    // One fix dispatch carrying ALL blocking findings, then a fresh package and re-review.
    await record('Write ' + WORKDIR + 'task-' + n + '-review-r' + round + '.md containing this verdict text exactly as given:\n' + fence(verdict.verbatim), 'task-' + n + ':persist-r' + round, 'Review')

    const fixNote = 'A reviewer found the following in your work. Address ALL of them, re-run ' +
      'the tests covering the amended code, APPEND a fix report with those test results to ' +
      reportPath + ', and commit the fix.\n' +
      fence(JSON.stringify(blocking, null, 2)) + '\n' +
      (verdict.cannotVerify && verdict.cannotVerify.length
        ? 'The reviewer could not verify these from the diff alone; confirm each holds:\n' + fence(JSON.stringify(verdict.cannotVerify)) + '\n'
        : '') + '\n'

    const fix = await agent(implementerPrompt(task, briefPath, reportPath, fixNote), routed({ label: 'task-' + n + ':fix-r' + round, phase: 'Execute', schema: IMPL_SCHEMA, agentType: 'development:implementer' }, tier))
    if (!fix || (fix.status !== 'DONE' && fix.status !== 'DONE_WITH_CONCERNS')) {
      return await stop('task-' + n + '-blocked', 'The fix round for task ' + n + ' did not complete: ' + ((fix && fix.detail) || 'the implementer returned nothing usable'), { task: n, round: round })
    }
  }

  DONE.add(n)
  log('Task ' + n + ' complete (' + DONE.size + '/' + TASKS.length + ')')
}

if (DONE.size < TASKS.length) {
  const stuck = TASKS.filter(function (t) { return !DONE.has(t.n) }).map(function (t) { return t.n })
  // Only the stuck numbers travel back: the full decomposition is in the manifest, and
  // whatever comes back through `return` is spent from the calling session's context.
  return await stop('plan-conflicts', 'Tasks ' + stuck.join(', ') + ' can never start — their dependencies are circular or name tasks that do not exist.', { stuck: stuck, blockedBy: stuck.map(function (n) { const t = TASKS.find(function (x) { return x.n === n }); return n + ' <- ' + ((t && t.blockedBy) || []).join(',') }) })
}

// ── Finish ───────────────────────────────────────────────────────────────────

phase('Finish')

// 1. Full verification suite.
for (let attempt = 1; ; attempt++) {
  const suite = await agent(
    'Run the full verification suite for this run, from ' + REPO_ROOT + '.\n\n' +
    'Run every verify command the plan at ' + PLAN_PATH + ' names, plus any checks its Global ' +
    'Constraints require. Run them all — do not stop at the first failure. Change nothing.\n\n' +
    'Report passed=true only if every command succeeded. Set operational=true when a failure ' +
    'is tooling, auth, or a missing dependency rather than the code under test.',
    routed({ label: 'verify-suite-' + attempt, phase: 'Finish', schema: SUITE_SCHEMA }, 'standard')
  )

  if (suite && suite.passed) {
    await record('Set finish to {"state":"suite-green","head":"<current head from git rev-parse HEAD>"} in manifest.json, saved atomically, and report that head as "hash".', 'finish:suite-green', 'Finish')
    break
  }
  if (!suite || suite.operational) {
    return await stop('operational', 'The verification suite could not run: ' + ((suite && suite.detail) || 'the runner reported nothing usable'), { suite: suite || null })
  }
  if (attempt >= 3) {
    return await stop('suite-failed', 'The verification suite still fails after ' + attempt + ' fix attempts.', { failures: suite.failures || [], detail: suite.detail })
  }

  const fix = await agent(
    'The full verification suite is failing on branch ' + BRANCH + ' after all tasks completed.\n\n' +
    'Failures:\n' + fence(JSON.stringify(suite.failures || [suite.detail], null, 2)) + '\n\n' +
    heldBlock() +
    'Fix them, re-run the failing commands, append a fix report with the results to ' +
    WORKDIR + 'suite-fix-' + attempt + '.md, and commit. ' + GIT_CONTRACT,
    routed({ label: 'suite-fix-' + attempt, phase: 'Finish', schema: IMPL_SCHEMA, agentType: 'development:implementer' }, 'standard')
  )
  if (!fix || (fix.status !== 'DONE' && fix.status !== 'DONE_WITH_CONCERNS')) {
    return await stop('suite-failed', 'The suite fix attempt did not complete: ' + ((fix && fix.detail) || 'the implementer returned nothing usable'), { attempt: attempt, failures: suite.failures || [] })
  }
}

// 2. Whole-branch review: two arms in parallel, both re-run each round against the CURRENT
//    head, because fixes move it.
let finalRound = 0
for (;;) {
  finalRound += 1

  const headProbe = await record('Report the current head hash ("git rev-parse HEAD") as "hash". Change nothing.', 'finish:head-r' + finalRound, 'Finish')
  const head = (headProbe && headProbe.hash) || ''
  if (!head) {
    return await stop('operational', 'Could not read the current head before the final review.', { round: finalRound })
  }

  const arms = await parallel([
    function () {
      return agent(
        'Whole-branch review of a completed feature-development run.\n\n' +
        'Spec: ' + SPEC_PATH + '\n' +
        'Plan: ' + PLAN_PATH + '\n' +
        'Ledger: ' + WORKDIR + 'progress.md\n' +
        'Commit range: ' + BRANCH_POINT + '..' + head + ' — build your own diff from it.\n\n' +
        'Return your verdict, and also return it complete and unaltered in the "verbatim" ' +
        'field — that text is persisted to disk exactly as you write it. Triage the Minor ' +
        'findings the ledger carries from the per-task reviews.',
        { label: 'code-reviewer-r' + finalRound, phase: 'Finish', schema: BRANCH_REVIEW_SCHEMA, agentType: 'development:code-reviewer' }
      )
    },
    function () {
      return agent(
        'Consult Codex for a cross-model review of a finished branch, then report what it ' +
        'found. You are a relay: you do not review the code yourself and you edit nothing.\n\n' +
        'First run ToolSearch with the query "select:mcp__codex__codex" to load the tool ' +
        'schema — it is not callable until you do. Then call mcp__codex__codex with EXACTLY ' +
        'these parameters:\n' +
        '  cwd: "' + REPO_ROOT + '"\n' +
        '  sandbox: "read-only"\n' +
        '  approval-policy: "never"\n' +
        '  (do NOT pass a model parameter — the Codex config decides)\n' +
        '  prompt: the review brief below\n\n' +
        'Review brief to send:\n' +
        '"Whole-branch review. Spec: ' + SPEC_PATH + '. Plan: ' + PLAN_PATH + '. Commit range: ' +
        BRANCH_POINT + '..' + head + ' — inspect it with git yourself. Judge whether the branch ' +
        'implements the spec: requirements missing or misread, defects introduced across task ' +
        'boundaries that a task-scoped review could not see, and anything the plan mandated ' +
        'that you would block a merge over. Findings only, each with file:line. Do not edit ' +
        'anything. Do not open a pull request."\n\n' +
        'Return Codex\'s reply complete and unaltered in the "verbatim" field, plus its ' +
        'findings classified Critical / Important / Minor. If the Codex tool cannot be reached ' +
        'or errors, report available:false with the reason, an empty findings array, and the ' +
        'reason as "verbatim" — do NOT fail, and do NOT substitute your own review.',
        routed({ label: 'codex:branch-review-r' + finalRound, phase: 'Finish', schema: BRANCH_REVIEW_SCHEMA }, 'standard')
      )
    },
  ])

  const local = arms[0]
  const codex = arms[1]

  await record(
    'Persist the final review verdicts for round ' + finalRound + ', each exactly as given:\n' +
    '1. Write ' + WORKDIR + 'code-review-r' + finalRound + '.md:\n' + fence((local && local.verbatim) || 'The code-reviewer returned nothing.') + '\n' +
    '2. Write ' + WORKDIR + 'codex-review-r' + finalRound + '.md:\n' + fence((codex && codex.verbatim) || 'Codex was unavailable and reported no reason.'),
    'finish:persist-r' + finalRound, 'Finish'
  )

  if (!local) {
    return await stop('operational', 'The code-reviewer returned nothing on final review round ' + finalRound + '.', { round: finalRound, head: head })
  }
  if (!codex || codex.available === false) {
    log('Codex branch review unavailable on round ' + finalRound + ': ' + ((codex && codex.reason) || 'relay returned nothing'))
  }

  const merged = (local.findings || []).concat((codex && codex.findings) || [])
  const blocking = merged.filter(function (f) { return f.severity === 'Critical' || f.severity === 'Important' })
  const planMandated = blocking.filter(function (f) { return f.planMandated })

  if (planMandated.length && !answerFor('final-plan-conflict')) {
    return await stop('final-plan-conflict', 'The final review found ' + planMandated.length + ' finding(s) against something the plan explicitly mandates. Which governs — the plan text, or the finding?', { round: finalRound, findings: planMandated })
  }

  if (!blocking.length) {
    await record('Set finish to {"state":"reviewed","head":"' + head + '"} in manifest.json, saved atomically.', 'finish:reviewed', 'Finish')
    log('Final review clean at ' + head.slice(0, 7) + ' after ' + finalRound + ' round(s)')
    break
  }

  if (finalRound >= 3) {
    return await stop('final-review-cap', 'The branch is still failing the final review after 3 rounds.', { findings: blocking, head: head })
  }

  const fix = await agent(
    'The final whole-branch review found issues on branch ' + BRANCH + '.\n\n' +
    'Findings from both reviewers — address ALL of them:\n' + fence(JSON.stringify(blocking, null, 2)) + '\n\n' +
    heldBlock() +
    'Re-run the tests covering the amended code AND the plan\'s full verify suite, append a ' +
    'fix report with those results to ' + WORKDIR + 'final-fix-r' + finalRound + '.md, and ' +
    'commit the fix. ' + GIT_CONTRACT,
    routed({ label: 'final-fix-r' + finalRound, phase: 'Finish', schema: IMPL_SCHEMA, agentType: 'development:implementer' }, 'standard')
  )
  if (!fix || (fix.status !== 'DONE' && fix.status !== 'DONE_WITH_CONCERNS')) {
    return await stop('final-review-cap', 'The final fix round did not complete: ' + ((fix && fix.detail) || 'the implementer returned nothing usable'), { round: finalRound, findings: blocking })
  }
}

// 3. Finish. An autonomous run never pushes unless it was asked to up front.
let pr = 'kept'
if (WANT_PR) {
  const opened = await record(
    'Publish this branch:\n' +
    '1. "git push -u origin ' + BRANCH + '"\n' +
    '2. "gh pr create --fill"\n' +
    'Both noninteractively. Report the pull request URL as "detail". If either fails (auth, ' +
    'no remote, gh missing), report ok:false with the exact error — do not retry blindly.',
    'finish:open-pr', 'Finish'
  )
  if (!opened || !opened.ok) {
    return await stop('operational', 'The branch is complete and reviewed, but publishing it failed: ' + ((opened && opened.detail) || 'the bookkeeper reported nothing usable'), { branch: BRANCH })
  }
  pr = opened.detail
}

await record('Set finish to {"state":"done","head":"<current head>","pr":' + JSON.stringify(pr) + '} in manifest.json, saved atomically, and report that head as "hash".', 'finish:done', 'Finish')

return {
  status: 'done',
  branch: BRANCH,
  branchPoint: BRANCH_POINT,
  workdir: WORKDIR,
  specPath: SPEC_PATH,
  planPath: PLAN_PATH,
  tasksCompleted: TASKS.length,
  finalReviewRounds: finalRound,
  pr: pr,
}
