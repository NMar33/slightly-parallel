/**
 * Lens registry — one entry per entity table the backend serves.
 *
 * A "lens" is one entity read as a ledger (`GET /api/<base>` +
 * `GET /api/<base>/{id}`). Each has its own page now — the generic page
 * component is gone — and this registry holds what they share: the title
 * and icon the sidebar and the Guide show, the question the lens answers
 * (those three live in `heads.ts`, which is all the app shell loads),
 * how its entries come into existence, and what an entry holds.
 *
 * Each entry says what it holds (`holds`): the named fields an agent writes
 * for that lens, the same names the server publishes on GET /api/schema
 * (backend/backend/entry_fields.py). The agent prompts and the Guide page
 * are built from them, so the two cannot drift apart.
 */

import type { LucideIcon } from 'lucide-react'

import { LENS_HEAD } from './heads'
import { t, tn } from '../i18n/scope/shell'
import type { LensRow } from '../lib/api'

export type BadgeTone = 'neutral' | 'green' | 'amber' | 'red' | 'blue' | 'purple'

interface LensBadge {
  label: string
  tone?: BadgeTone
}

interface LensFacet {
  /** Query param sent to the backend (matches routers/lenses.py FILTERS). */
  param: string
  /** Row field the chip values are collected from. */
  field: string
  label: string
}

/** One named field of an entry, and what goes in it. */
interface Hold {
  name: string
  line: string
}

export interface LensConfig {
  /** Route segment and API base: `/decisions` ↔ `/api/decisions`. */
  base: string
  /** Key wrapping the row array in the list response. */
  listKey: string
  title: string
  tagline: string
  icon: LucideIcon
  /** The question this lens answers about the project. */
  question: string
  /** How entries come into existence (who writes, when, triggered by what). */
  workflow: string
  /** Slash command that produces entries, when one exists. */
  command?: string
  /** What an entry of this lens holds, by name. */
  holds: Hold[]
  /** The row's one-line headline. */
  l1: (row: LensRow) => string
  /** Compact badges rendered next to the headline. */
  badges?: (row: LensRow) => LensBadge[]
  /** Facet chip filters (server-side params). */
  facets?: LensFacet[]
  /** Copy-pasteable instructions for an agent that writes this entity. */
  agentPrompt: string
  emptyHint: string
}

const str = (v: unknown): string => (v == null ? '' : String(v))
const num = (v: unknown): number | null => {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

const STATUS_TONES: Record<string, BadgeTone> = {
  done: 'green', shipped: 'green', resolved: 'green', hit: 'green',
  active: 'blue', in_progress: 'blue', open: 'blue',
  planned: 'neutral', unknown: 'neutral',
  blocked: 'red', miss: 'red', critical: 'red', high: 'red',
  mixed: 'amber', medium: 'amber', investigating: 'amber',
}

const toneFor = (value: string): BadgeTone =>
  STATUS_TONES[value.toLowerCase()] ?? 'neutral'

function statusBadge(row: LensRow, field: string): LensBadge[] {
  const v = str(row[field])
  return v ? [{ label: v, tone: toneFor(v) }] : []
}

/** `one` and `other` are tn()'s: '{n} file', '{n} files'. */
function countBadge(row: LensRow, field: string, one: string, other: string): LensBadge[] {
  const n = num(row[field])
  return n != null && n > 0 ? [{ label: tn(n, one, other) }] : []
}

/** The lens name write_entry takes: `decisions` → `decision`, `sessions` → `session`. */
function lensName(base: string): string {
  return base.replace(/-/g, '_').replace(/ies$/, 'y').replace(/s$/, '')
}

/**
 * Build the agent prompt from what the entry holds and an example, so the
 * text shown on the Guide page and the instructions given to agents are the
 * same text.
 */
function post(
  base: string,
  holds: Hold[],
  example: Record<string, unknown>,
): string {
  const lens = lensName(base)
  return [
    `MCP tool write_entry {lens: "${lens}", fields: {…}}`,
    '',
    'What the entry holds. Put each under its name in `fields`. A field you',
    'have nothing for is left out.',
    ...holds.map((h) => `  ${h.name}: ${h.line}`),
    '',
    'Example:',
    '',
    JSON.stringify({ lens, fields: example }, null, 2),
    '',
    'Project, agent id, date and time are stamped by the tool. Do not send them.',
    'A field the lens does not have is refused by name. The same entry written',
    'twice is one entry. The answer may list warnings. Fix them and write again.',
  ].join('\n')
}

export const LENSES: Record<string, LensConfig> = {}

function lens(
  cfg: Omit<LensConfig, 'agentPrompt'> &
    ({ example: Record<string, unknown> } | { agentPrompt: string }),
): void {
  if ('agentPrompt' in cfg) {
    LENSES[cfg.base] = cfg
    return
  }
  const { example, ...rest } = cfg
  LENSES[cfg.base] = { ...rest, agentPrompt: post(cfg.base, cfg.holds, example) }
}

// ---------------------------------------------------------------------------
// Lenses
// ---------------------------------------------------------------------------

lens({
  ...LENS_HEAD.scans,
  listKey: 'scans',
  tagline: t('Changes since the last scan.'),
  workflow:
    t('You type #scan when work is shipped, before a risky change, or at the end of a chat. The agent writes what it changed since its own last scan, committed or not. The numbers (files, lines, decisions) are counted by Slightly Parallel.'),
  command: '#scan',
  holds: [
    { name: 'summary', line: 'one line: what changed since the last scan' },
    { name: 'why', line: 'why it changed: what was intended and what happened' },
    { name: 'deltas', line: 'one line per file or area, with numbers' },
    { name: 'proof', line: 'diff excerpts, commands run, test output' },
  ],
  l1: (r) => str(r.l1),
  badges: (r) => [
    ...countBadge(r, 'files_n', '{n} file', '{n} files'),
    ...(num(r.lines_add) != null && (num(r.lines_add) || num(r.lines_del))
      ? [{ label: `+${num(r.lines_add) ?? 0}/−${num(r.lines_del) ?? 0}` }]
      : []),
    ...countBadge(r, 'decisions_n', '{n} decision', '{n} decisions'),
  ],
  example: {
    summary: 'Auth flow shipped; rate limiting half-done',
    why: 'The goal was auth and rate limiting in this chat. Auth is done as planned; rate limiting is blocked on the Redis settings.',
    deltas: ['src/auth/* +90/−12: token refresh and tests', 'src/middleware.py +30/−18: rate limit skeleton, unwired'],
    proof: 'pytest: 34 passed. Redis connection refused on staging.',
    files_n: 4, lines_add: 120, lines_del: 30, decisions_n: 1, scope: 'src/auth',
  },
  emptyHint: t('Type #scan in the chat to record the first scan.'),
})

lens({
  ...LENS_HEAD.standups,
  listKey: 'standups',
  tagline: t('One standup per project per day, from every chat of that day.'),
  command: '#standup',
  workflow:
    t('The first agent of a new day is told that yesterday has no standup. It asks you: write it now, or postpone. A helper agent on the model set in Settings reads every message of that day and writes it. #standup asks for it by hand. The skill daily-standup holds the steps.'),
  holds: [
    { name: 'summary', line: 'one sentence: the one or two changes that matter most' },
    { name: 'deviation', line: 'at most three lines: what broke, was redone, or was corrected' },
    { name: 'movement', line: 'at most six lines: one outcome a user or an agent can see, each' },
    { name: 'detail', line: 'needs an answer, next, state' },
  ],
  l1: (r) => str(r.l1),
  badges: (r) => [
    ...countBadge(r, 'goals_open_n', '{n} open', '{n} open'),
    ...countBadge(r, 'goals_closed_n', '{n} closed', '{n} closed'),
    ...countBadge(r, 'blockers_n', '{n} blocked', '{n} blocked'),
    ...(num(r.hours_today) ? [{ label: t('{h}h', { h: num(r.hours_today) ?? 0 }) }] : []),
  ],
  example: {
    for_date: '2608-18',
    summary: 'Login with tokens works. Rate limiting is not started: the staging Redis credentials are missing.',
    deviation: ['Rate limiting was planned and did not start. The staging Redis credentials are missing.'],
    movement: ['Token login (tk_5d2c1a90): users stay signed in for 30 days.', 'Rate limiting (tk_91530f2f). Left: all of it. It waits on the Redis credentials.'],
    detail: '**Needs an answer:** who can issue the staging Redis credentials.\n**Next:** rate limiting.\n**State:** tests pass; pushed.',
    goals_open_n: 3, goals_closed_n: 1, blockers_n: 1, hours_today: 4.0,
  },
  emptyHint: t('The first agent of a new day asks to write the standup for the day before.'),
})

lens({
  ...LENS_HEAD.decisions,
  listKey: 'decisions',
  tagline: t('Choices agents logged, each with a weight, the reason and the options turned down.'),
  workflow:
    t('Agents log decisions when a piece of work is done, or on #decision: each point where you chose between options or the agent reversed its own work, if the product would be different had it gone the other way. Each has a weight: minor, normal or major. The skill log-a-decision holds the steps.'),
  command: '#decision',
  holds: [
    { name: 'decision', line: 'one sentence: what was chosen, as how it is now' },
    { name: 'weight', line: 'minor, normal or major: what undoing it would cost' },
    { name: 'why', line: 'one or two sentences: the reason, then the state' },
    { name: 'alternatives', line: 'only options someone proposed: "<option> — rejected: <reason>"' },
    { name: 'excerpt', line: 'for a major decision: the lines of chat where it was decided' },
  ],
  l1: (r) => str(r.decision_text),
  badges: (r) => [
    ...(str(r.source)
      ? [{ label: str(r.source), tone: (str(r.source).startsWith('explicit') ? 'blue' : 'neutral') as BadgeTone }]
      : []),
    ...countBadge(r, 'alternatives_n', '{n} alternative', '{n} alternatives'),
  ],
  facets: [{ param: 'source', field: 'source', label: t('Source') }],
  example: {
    decision: 'Chose Redis over in-process cache for rate limiting',
    why: 'Workers must share counters, so in-process caching undercounts. Revisit if we go single-worker or if Redis costs more than an hour a week to run.',
    alternatives: ['in-process LRU — rejected: undercounts across workers', 'Postgres counters — rejected: hot-row contention at target RPS'],
    excerpt: 'user: we run two workers\nagent: then the counters must be shared',
    source: 'explicit', alternatives_n: 2,
  },
  emptyHint: t('Log decisions with #decision in a chat with an agent.'),
})

lens({
  ...LENS_HEAD.sprints,
  listKey: 'sprints',
  tagline: t('Blocks of work, each with a length in days, an hour budget and a retro.'),
  workflow:
    t('Opened at sprint planning with a name, a length in days and an optional budget in hours. Tasks join it from the board through sprint_id. It ends with the counts of tasks done and a retro of the plan against what happened.'),
  holds: [
    { name: 'headline', line: 'one line: the name or theme of the block of work' },
    { name: 'retro', line: 'when it ends: what happened against the plan' },
    { name: 'points', line: 'the tasks in it, and what happened to each' },
    { name: 'detail', line: 'planning notes' },
  ],
  l1: (r) => str(r.name) || str(r.theme),
  badges: (r) => [
    ...statusBadge(r, 'status'),
    ...(num(r.time_budget_h) ? [{ label: t('{h}h budget', { h: num(r.time_budget_h) ?? 0 }) }] : []),
    ...(num(r.goals_shipped_n) != null && num(r.goals_declared_n)
      ? [{ label: t('{done}/{all} shipped', { done: num(r.goals_shipped_n) ?? 0, all: num(r.goals_declared_n) ?? 0 }) }]
      : []),
  ],
  facets: [{ param: 'status', field: 'status', label: t('Status') }],
  example: {
    headline: 'Sprint 12: Hardening',
    name: 'Sprint 12', theme: 'Hardening', projects: 'my-project',
    started_date: '2608-12', time_budget_h: 20, status: 'active', confidence_pct: 75,
    goals_declared_n: 5, goals_shipped_n: 0,
    points: ['rate limiting: 80%', 'audit logging: 70%', 'docs: 90%'],
  },
  emptyHint: t('Open a sprint to group tasks into one block of work.'),
})

lens({
  ...LENS_HEAD.sessions,
  listKey: 'sessions',
  tagline: t('Every chat with an agent: when it ran, what was said, what came out of it.'),
  workflow:
    t('Slightly Parallel builds the chats from the recorded messages. Each turn has a time, and turns with pauses shorter than the chat gap (Settings → Chats) form one chat. The durations are measured from those times.'),
  holds: [
    { name: 'headline', line: 'made from the first and the last turn' },
    { name: 'turns and minutes', line: 'counted from the turn times' },
    { name: 'turns', line: 'one line per turn' },
    { name: 'chat', line: 'the part of the chat this block covers' },
  ],
  l1: (r) => str(r.l1),
  badges: (r) => [
    ...(num(r.turns_n) ? [{ label: tn(num(r.turns_n) ?? 0, '{n} turn', '{n} turns') }] : []),
    ...(num(r.duration_min) ? [{ label: num(r.agent_min) ? `${num(r.duration_min)} min · agent ${num(r.agent_min)}` : `${num(r.duration_min)} min` }] : []),
  ],
  agentPrompt: [
    'Slightly Parallel builds the chats from the recorded messages.',
    '',
    'Chats are recorded automatically by the hooks Setup installs.',
    'Recorded turns are grouped into chats by their times, and the',
    'dashboard computes hours, heatmaps and quiet projects from',
    'them.',
  ].join('\n'),
  emptyHint: t('Chats appear after an agent\'s first message in this project.'),
})
lens({
  ...LENS_HEAD.visions,
  listKey: 'visions',
  tagline: t('Your ideas about where the product should go.'),
  command: '#vision',
  workflow:
    t('Kept from the chat when you type #vision, so it is still there after the chat ends. Visions are read again when planning.'),
  holds: [
    { name: 'message', line: 'your words, kept as written' },
    { name: 'context', line: 'the turns around the message' },
    { name: 'interpretation', line: 'the message read with its context; every change is a version' },
    { name: 'sets', line: 'the named sets it belongs to, and the projects they are written into' },
  ],
  l1: (r) => str(r.l1),
  badges: (r) => [
    ...(str(r.category) ? [{ label: str(r.category) }] : []),
    ...(str(r.impact) ? [{ label: t('impact: {v}', { v: str(r.impact) }), tone: toneFor(str(r.impact)) }] : []),
    ...(str(r.effort) ? [{ label: t('effort: {v}', { v: str(r.effort) }) }] : []),
  ],
  facets: [
    { param: 'category', field: 'category', label: t('Category') },
    { param: 'impact', field: 'impact', label: t('Impact') },
  ],
  agentPrompt: [
    'Nothing to write for the message itself.',
    '',
    'You type #vision in the chat. The server keeps the message as written,',
    'and the capture hook names the id. Write the interpretation: the message',
    'read with the turns around it, in plain words.',
    '',
    '  MCP tool interpret {lens: "vision", id, text}',
    '',
    'Every write is a version. You edit it on the page afterwards.',
  ].join('\n'),
  emptyHint: t('Type #vision in the chat to keep a directional idea.'),
})

lens({
  ...LENS_HEAD.skills,
  listKey: 'skills',
  tagline: t('Instructions an agent loads when a task matches.'),
  command: '#skill',
  workflow:
    t('Written from a chat: you type #skill and the agent writes SKILL.md from what was just done. You keep or edit it, then install it into a project (.claude/skills and .agents/skills) or into the home folders every agent on the machine reads. Slightly Parallel keeps every version, watches the installed copies for hand edits, and counts the turns each skill ran in.'),
  holds: [
    { name: 'name', line: 'the folder agents see' },
    { name: 'description', line: 'what the skill does and when to use it' },
    { name: 'SKILL.md', line: 'the steps, the exact commands and the check' },
    { name: 'files', line: 'the files beside SKILL.md' },
  ],
  l1: (r) => str(r.name) || str(r.l1),
  badges: (r) => [
    ...statusBadge(r, 'status'),
    ...countBadge(r, 'versions_n', '{n} version', '{n} versions'),
  ],
  facets: [{ param: 'status', field: 'status', label: t('Status') }],
  agentPrompt: [
    'Skills are not posted like other entries.',
    '',
    'You type #skill in the chat. The capture hook names the id and',
    'asks for the draft:',
    '',
    '  MCP tool skill_draft {id, skill_md, files}',
    '  files: {"scripts/check.sh": "…"}. Leave it out to keep the files the skill has.',
    '',
    'SKILL.md starts with a --- block holding name (lowercase letters, digits',
    'and single hyphens) and description (what the skill does and when to use',
    'it, at most 1,024 characters. Agents read only the description when they',
    'choose a skill). The body holds the steps in order, the exact commands,',
    'the check that proves it worked, and the mistakes made in that chat.',
    'Long reference text and scripts go in files and are linked from SKILL.md.',
    '',
    'The answer lists checks: fix every error and write again. Installing a',
    'skill is yours to do; agents write drafts.',
  ].join('\n'),
  emptyHint: t('Type #skill in the chat when the work is done.'),
})

lens({
  ...LENS_HEAD.artifacts,
  listKey: 'artifacts',
  tagline: t('Folders an agent made for you: datasets, documents, pages, apps.'),
  command: '#artifact',
  workflow:
    t('You type #artifact in the chat and say what you want. The agent writes the folder itself, under the project in the Slightly Parallel folder, with ARTIFACT.md on top, then writes the entry with one MCP call. The page previews each artifact by kind: a dataset shows its fields and a sample, a document renders, a page opens in a frame, an app shows its files and the line that runs it.'),
  holds: [
    { name: 'name', line: 'the folder' },
    { name: 'kind', line: 'dataset, document, page, app or other' },
    { name: 'description', line: 'what is inside and what it is for' },
    { name: 'files', line: 'what the folder holds' },
  ],
  l1: (r) => str(r.name) || str(r.l1),
  badges: (r) => [
    ...statusBadge(r, 'status'),
    ...(str(r.kind) ? [{ label: str(r.kind) }] : []),
    ...countBadge(r, 'files_n', '{n} file', '{n} files'),
  ],
  facets: [
    { param: 'kind', field: 'kind', label: t('Kind') },
    { param: 'status', field: 'status', label: t('Status') },
  ],
  agentPrompt: [
    'Artifacts are not posted like other entries.',
    '',
    'You type #artifact in the chat. The capture hook names the id and',
    'the folder: <data_root>/projects/<project>/artifacts/<name>/. Write the',
    'folder with your own file tools: ARTIFACT.md on top (a --- block with',
    'name, kind and description, then a short text), the files beside it.',
    'Kinds: dataset (jsonl or csv with a header), document (one .md), page',
    '(index.html with everything inline), app (sources only, a run: line),',
    'other.',
    '',
    'Then make the record with the MCP tool:',
    '',
    '  artifact_write {id, name, kind, description}',
    '',
    'The same call after editing the folder is the update. The built-in skill',
    'make-an-artifact holds the same steps.',
  ].join('\n'),
  emptyHint: t('Type #artifact in the chat and say what you want.'),
})

lens({
  ...LENS_HEAD.entrypoints,
  listKey: 'entrypoints',
  tagline: t('The way into a topic, for whoever comes back to it.'),
  command: '#entrypoint',
  workflow:
    t('Kept when you type #entrypoint about a topic: the film, the launch, a migration. The agent writes five sections from the chat: what the topic is, where its files and links are, how to run it, where the work stopped, what comes next. A second #entrypoint on the same topic is a new version. Close the topic when it is done.'),
  holds: [
    { name: 'what', line: 'what the topic is and what for' },
    { name: 'where', line: 'the files, folders, artifacts and links, one per line' },
    { name: 'how', line: 'how to run or repeat it: commands, pages, the skill' },
    { name: 'state', line: 'where the work stopped' },
    { name: 'next', line: 'what comes next' },
  ],
  l1: (r) => str(r.topic) || str(r.l1),
  badges: (r) => [...statusBadge(r, 'status')],
  facets: [
    { param: 'status', field: 'status', label: t('Status') },
  ],
  example: {
    what: 'The install film: the first how-to of the channel, 4:08, made with the tour generator.',
    where: 'brand/channel/videos/install-voiced.mp4 · brand/channel/install-voice.md · launch.html, Upload 4',
    how: 'Studio → Install, and connect a project → 1920px → render MP4; the skill make-a-how-to-film.',
    state: 'Voiced MP4 done; not uploaded.',
    next: 'Upload as Public; the link into the README.',
    status: 'open',
  },
  emptyHint: t('Type #entrypoint about a topic you will come back to.'),
})

lens({
  ...LENS_HEAD.problems,
  listKey: 'problems',
  tagline: t('Blockers and risks, kept until resolved.'),
  command: '#problem',
  workflow:
    t('Logged the moment an agent is blocked or spots a risk, while the cause is still known. It is re-posted with a status as attempts accumulate, and resolved_date closes it. Old open problems sort to the top of this page.'),
  holds: [
    { name: 'problem', line: 'one line: what is blocked' },
    { name: 'impact', line: 'what it affects, and who or what owns the fix' },
    { name: 'attempts', line: 'one line per attempt: "<tried> — <result>"' },
    { name: 'excerpt', line: 'the error, the log, the chat excerpt' },
  ],
  l1: (r) => str(r.l1),
  badges: (r) => [
    ...statusBadge(r, 'severity'),
    ...statusBadge(r, 'status'),
  ],
  facets: [
    { param: 'severity', field: 'severity', label: t('Severity') },
    { param: 'status', field: 'status', label: t('Status') },
  ],
  example: {
    problem: 'Staging Redis refuses connections from CI runners',
    impact: 'Blocks load-testing of rate limiting and so the sprint exit. The fix belongs to whoever holds the staging security-group config.',
    attempts: ['VPC peering checked — routes fine', 'Auth string rotated — no change', 'Client library version — ruled out'],
    excerpt: 'redis.exceptions.ConnectionError: Error 111 connecting to staging-redis:6379',
    severity: 'high', status: 'open',
  },
  emptyHint: t('Log blockers so they are visible across chats.'),
})

lens({
  ...LENS_HEAD.rules,
  listKey: 'rules',
  tagline: t('Rules agents follow, written after something went wrong.'),
  command: '#rule',
  workflow:
    t('A rule is written after something went wrong, or after a lesson repeated. Agents read the rules for their project before they start work. Each rule keeps the message or the problem it came from.'),
  holds: [
    { name: 'message', line: 'your words, kept as written' },
    { name: 'context', line: 'the turns around the message, or the problem it came from' },
    { name: 'interpretation', line: 'the rule as agents read it; every change is a version' },
    { name: 'reach', line: 'for all agents, or the sets and projects it is written into' },
  ],
  l1: (r) => str(r.l1),
  badges: (r) => [
    ...(str(r.kind) ? [{ label: str(r.kind) }] : []),
    ...statusBadge(r, 'severity'),
    ...statusBadge(r, 'status'),
  ],
  facets: [
    { param: 'kind', field: 'kind', label: t('Kind') },
    { param: 'severity', field: 'severity', label: t('Severity') },
  ],
  agentPrompt: [
    'Nothing to write for the message itself.',
    '',
    'You type #rule in the chat. The server keeps the message as written,',
    'and the capture hook names the id. Write the interpretation: the message',
    'read with the turns around it, in plain words.',
    '',
    '  MCP tool interpret {lens: "rule", id, text}',
    '',
    'Every write is a version. You edit it on the page afterwards.',
  ].join('\n'),
  emptyHint: t('Type #rule in the chat to turn a repeated lesson into a rule.'),
})

lens({
  ...LENS_HEAD.files,
  listKey: 'files',
  tagline: t('Which files changed, and why each matters.'),
  workflow:
    t('The second part of #scan. After posting the scan the agent posts a file entry, with trigger_id set to the scan id and one record per file it changed: how important the file is, how far a change to it reaches, whether it is tested, how new it is, and why. Git fills the action, the line counts and the diff; the agent supplies the judgement. Entries chain per project through prev_file_id, so the page can replay any interval and the paths feed the heatmap. Three things keep it reproducible: the contract, the scan response (files_entry: null with a warning until it is posted), and a one-time [slightly-parallel] notice on the next turn.'),
  holds: [
    { name: 'summary', line: 'one line: N files · +X/−Y · the theme' },
    { name: 'narrative', line: 'the overall story, then a line per file' },
    { name: 'per_file', line: 'one line per file: the functions and classes touched' },
    { name: 'diff', line: 'the diff; git fills it when left empty' },
    { name: 'paths', line: 'one record per file: how important, how far it reaches, whether it is tested, how new, and why' },
  ],
  l1: (r) => str(r.l1),
  badges: (r) => [
    ...(str(r.trigger_lens) ? [{ label: t('via {lens}', { lens: str(r.trigger_lens) }) }] : []),
    ...countBadge(r, 'files_important_n', '{n} important', '{n} important'),
  ],
  facets: [{ param: 'trigger_lens', field: 'trigger_lens', label: t('Trigger') }],
  example: {
    summary: '3 files · +187/−4 · Redis rate-limit middleware',
    narrative: 'A Redis rate limiter now runs on every request. High blast radius; test coverage went up with it.',
    per_file: ['app/middleware/rate_limit.py: RateLimitMiddleware.dispatch, an INCR+EXPIRE pipeline, 429 with Retry-After',
               'app/main.py: stack order CORS → Auth → RateLimit → router'],
    trigger_lens: 'scan', trigger_id: 'sn_1a2b3c4d', files_important_n: 2, files_ignored_n: 1,
    paths: [
      { path: 'app/middleware/rate_limit.py', importance: 4, blast_radius: 10,
        test_coverage: 'covered', novelty: 'new', security_surface: true,
        why: 'Every request passes through it; a bug here is an outage.' },
      { path: 'app/main.py', importance: 2, blast_radius: 6, test_coverage: 'covered',
        why: 'Middleware order: auth must run before the limiter.' },
    ],
  },
  emptyHint: t('File entries are written as the second part of every #scan.'),
})

lens({
  ...LENS_HEAD.architecture,
  listKey: 'architecture',
  tagline: t('Three parts: a page of claims with evidence, a map of the parts of the program, and a list of what each scan changed.'),
  command: '#architecture',
  workflow:
    t('Three parts. The page is one document per project, written at the end of a scan, or with #page. Slightly Parallel computes its top band from the folder, the agent writes the rest as claims, each with where it lives and how the agent knows, and Slightly Parallel checks every path. The skill keep-the-architecture-page holds the steps. The map is every part of the program as a row of one kind, and what connects to what, written by a helper agent at the standup when you choose write and map, or with #map; the skill map-the-program holds the steps. The architecture form is the third part of #scan: one form per scan, covering the whole window since the previous scan. The agent goes through eight groups (does, owes, runs, stores, talks, built with, faces, holds) and for each either lists it in `checked`, meaning it looked and the group is unchanged, or posts its changes: op (add, change or remove) on a typed, named entity with 1 to 5 paths in the repository. The answer is recorded, so an unchanged group counts as checked. Debt and action-needed rows stay on the page until they are removed.'),
  holds: [
    { name: 'changes', line: 'one entry per change: op, type, name, path, note, and the fields of that type' },
    { name: 'checked', line: 'the groups you looked at where nothing changed' },
    { name: 'trigger_id', line: 'the scan this form belongs to' },
  ],
  l1: (r) => str(r.name) || str(r.l1),
  badges: (r) => [
    ...(str(r.type) ? [{ label: str(r.type) }] : []),
    ...(str(r.op) && str(r.op) !== 'add' ? [{ label: str(r.op) }] : []),
    ...(str(r.task) ? [{ label: str(r.task) }] : []),
  ],
  facets: [],
  example: {
    trigger_id: 'sn_1a2b3c4d',
    checked: ['owes', 'runs', 'built with', 'faces', 'holds'],
    changes: [
      { op: 'add', type: 'feature', name: 'report a task done, with evidence',
        path: ['backend/routers/evidence.py'], surface: 'kanban card',
        task: 'tk_5d2c1a90', note: 'agent reports; the card shows a badge' },
      { op: 'add', type: 'endpoint', name: 'GET /api/tasks/{id}/work',
        path: ['backend/routers/evidence.py:task_work'], method: 'GET',
        note: 'what the repository saw in the turns that named the task' },
      { op: 'add', type: 'database', name: 'task_evidence',
        path: ['backend/entities.py'], engine: 'csv',
        note: 'what an agent showed for a finished task' },
    ],
  },
  emptyHint: t('The form is the third part of every #scan. All eight groups checked and unchanged is a valid answer.'),
})

// ---------------------------------------------------------------------------
// Library — durable storage, not projections. The body is the point, and it
// lives in the detail document.
// ---------------------------------------------------------------------------

/** The lenses in use. */
export const LENS_LIST: LensConfig[] = Object.values(LENSES)
