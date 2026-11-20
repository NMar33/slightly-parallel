/**
 * What the record cards over the terminal read and do (IdCards.tsx), each
 * through the route its own page reads, and the operator's own routes only:
 *
 * - a decision: GET /api/decisions/{id} (the Decisions page);
 * - a Publish card: GET /api/publishing/cards/{id} (the Publish page);
 * - a core: GET /api/cores/{id}; a note on it, POST /api/cores/{id}/notes as
 *   the operator (Architecture › cores, useCoreWrites);
 * - a skill: GET /api/skills/{id}; installing it into the terminal's project,
 *   POST /api/skills/{id}/install as the operator (the Skills page);
 * - an entry point: the Entry points desk (GET /api/entrypoints/desk);
 * - a chat: GET /api/agent/{id}, its tasks from the task mentions
 *   (GET /api/tasks/mentions/by-agent), its terminal from the terminal list;
 *   resume and branch through the terminal window's own routes;
 * - a commit: GET /api/git/commit?repo=<project>&sha= (read only), which
 *   also says whether a hash printed in the terminal is a commit at all.
 *
 * The mapping from each answer to what its card shows is a pure function
 * here, so it is tested on its own.
 */

import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../../lib/getJson'
import { entryText, type EntryDetailLike } from '../../../lib/entryText'
import { agentLabel } from '../../../utils/agentLabel'
import { parseAlternative, type Alternative } from '../../decisions/data'
import { monthOfDay } from '../../daybook/data'
import { splitSkillMd } from '../../skills/frontmatter'
import type { Card as PublishCardWire } from '../../publish/data'
import type { CoreDetail } from '../../architecture/cores/data'
import type { Topic } from '../../entrypoints/desk/data'

const once = { staleTime: 15_000, retry: false } as const

/* ------------------------------------------------------------ links to the pages */

const hash = (parts: Record<string, string>) =>
  Object.entries(parts).filter(([, v]) => v).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')

/** Where each record is on its own page (lib/searchHits' routes, with the page's hash keys). */
export const pageOf = {
  decision: (project: string, day: string) => `/decisions#${hash({ project, month: monthOfDay(day), day })}`,
  publish: (project: string) => `/publish#${hash({ project })}`,
  core: (project: string, id: string) => `/architecture#${hash({ project, core: id })}`,
  skill: (id: string) => `/skills#${hash({ skill: id })}`,
  entrypoint: (id: string) => `/entrypoints?topic=${encodeURIComponent(id)}`,
  agent: (id: string) => `/agent/${encodeURIComponent(id)}`,
}

/* ------------------------------------------------------------ a decision */

interface DecisionWire extends EntryDetailLike {
  metadata: { id: string; decision_text?: string | null; rationale?: string | null; weight?: string | null; created_date?: string | null; created_time?: string | null; project?: string | null; agent_id?: string | null }
}

export interface DecisionView {
  decision: string
  why: string
  /** The options not taken (and any in no shape); the chosen one is the decision. */
  rejected: Alternative[]
  weight: string
  day: string
  time: string
  project: string
  agent: string
}

export function decisionView(d: DecisionWire): DecisionView {
  const held = entryText(d)
  const m = d.metadata
  return {
    decision: (held.line || m.decision_text || '').trim(),
    why: (held.text || m.rationale || '').trim(),
    rejected: held.list.map(parseAlternative).filter((a) => a.verdict !== 'chosen'),
    weight: (m.weight ?? '').trim(),
    day: m.created_date ?? '',
    time: m.created_time ?? '',
    project: m.project ?? '',
    agent: m.agent_id ?? '',
  }
}

export function useDecision(id: string) {
  return useQuery({
    queryKey: ['msgmenu', 'decision', id],
    queryFn: ({ signal }) => getJson<DecisionWire>(`/api/decisions/${encodeURIComponent(id)}`, signal).then(decisionView),
    ...once,
  })
}

/* ------------------------------------------------------------ a Publish card */

export interface PublishView {
  id: string
  project: string
  at: string
  text: string
  context: string
  /** Everything attached: tasks, notes, cores, commits, pictures, links, files. */
  attachments: number
  placed: number
}

export function publishView(c: PublishCardWire): PublishView {
  const n = (x?: unknown[]) => x?.length ?? 0
  return {
    id: c.id,
    project: c.project,
    at: c.at,
    text: (c.text || c.message || '').trim(),
    context: (c.context ?? '').trim(),
    attachments: n(c.tasks) + n(c.notes) + n(c.cores) + n(c.commits) + n(c.images) + n(c.links) + n(c.files),
    placed: n(c.placements),
  }
}

export function usePublishCard(id: string) {
  return useQuery({
    queryKey: ['msgmenu', 'publish', id],
    queryFn: ({ signal }) => getJson<PublishCardWire>(`/api/publishing/cards/${encodeURIComponent(id)}`, signal).then(publishView),
    ...once,
  })
}

/* ------------------------------------------------------------ a core */

export interface CoreView {
  id: string
  project: string
  name: string
  type: string
  reason: string
  off: boolean
  /** The last three notes, newest first. */
  notes: Array<{ id: string; at: string; author: string; text: string }>
  notesN: number
  tasks: Array<{ id: string; title: string; status: string }>
}

export function coreView(d: CoreDetail): CoreView {
  const notes = [...(d.notes ?? [])].sort((a, b) => b.at.localeCompare(a.at))
  return {
    id: d.id,
    project: d.project,
    name: d.name,
    type: d.type,
    reason: (d.reason ?? '').trim(),
    off: d.status === 'off',
    notes: notes.slice(0, 3).map((x) => ({ id: x.id, at: x.at, author: x.author, text: (x.text || x.comment || '').trim() })),
    notesN: notes.length,
    tasks: (d.tasks ?? []).filter((x) => !x.archived_at).map((x) => ({ id: x.id, title: x.title, status: x.status })),
  }
}

export function useCoreCard(id: string) {
  return useQuery({
    // The core page's own key (cores/data coreKey): its note write refreshes this card too.
    queryKey: ['core', id],
    queryFn: ({ signal }) => getJson<CoreDetail>(`/api/cores/${encodeURIComponent(id)}`, signal),
    ...once,
  })
}

/* ------------------------------------------------------------ a skill */

interface SkillWire {
  metadata: { id: string; name?: string | null; description?: string | null; status?: string | null; l1?: string | null }
  skill?: { current: { n: number; skill_md: string } | null; installs: Array<{ project: string; status: string }> }
}

export interface SkillView {
  id: string
  name: string
  description: string
  status: string
  version: number
  /** SKILL.md without its `---` block: what is rendered. */
  body: string
  installedIn: string[]
}

export function skillView(d: SkillWire): SkillView {
  const cur = d.skill?.current ?? null
  const md = cur ? splitSkillMd(cur.skill_md) : null
  return {
    id: d.metadata.id,
    name: (d.metadata.name || md?.name || d.metadata.l1 || d.metadata.id).trim(),
    description: (d.metadata.description || md?.description || '').trim(),
    status: d.metadata.status || 'draft',
    version: cur?.n ?? 0,
    body: (md?.body ?? '').trim(),
    installedIn: (d.skill?.installs ?? []).filter((i) => i.status !== 'missing').map((i) => i.project),
  }
}

export function useSkillCard(id: string) {
  return useQuery({
    queryKey: ['msgmenu', 'skill', id],
    queryFn: ({ signal }) => getJson<SkillWire>(`/api/skills/${encodeURIComponent(id)}`, signal).then(skillView),
    ...once,
  })
}

/* ------------------------------------------------------------ an entry point */

export interface EntryView {
  id: string
  project: string
  name: string
  /** The #entrypoint message's first line: the question it opened with. */
  question: string
  what: string
  state: string
  /** Where it stopped: the last answers, newest first. */
  stops: Array<{ at: string; author: string; text: string }>
  shots: Array<{ id: string; src: string; caption: string }>
  openTasks: number
}

export function entryView(tp: Topic): EntryView {
  return {
    id: tp.id,
    project: tp.project,
    name: tp.name || tp.title || tp.id,
    question: tp.title,
    what: (tp.what ?? '').trim(),
    state: tp.state,
    stops: (tp.stops ?? []).slice(0, 3).map((s) => ({ at: s.at, author: s.author, text: s.text })),
    shots: (tp.shots ?? []).slice(-4).map((s) => ({ id: s.id, src: s.src, caption: s.caption })),
    openTasks: tp.open_tasks ?? 0,
  }
}

export function useEntryCard(id: string) {
  return useQuery({
    queryKey: ['msgmenu', 'entrypoint', id],
    queryFn: async ({ signal }) => {
      const d = await getJson<{ topics: Topic[] }>('/api/entrypoints/desk?project=', signal)
      const tp = d.topics.find((x) => x.id === id)
      if (!tp) throw new Error('not found')
      return entryView(tp)
    },
    ...once,
  })
}

/* ------------------------------------------------------------ a chat */

interface AgentWire {
  agent: { agent_id: string; agent_name?: string; chat_title?: string; created_date?: string; tool?: string; session_ref?: string; project?: string; last_active?: string; message_count?: number; helper?: boolean }
}

export interface AgentView {
  id: string
  name: string
  project: string
  tool: string
  lastActive: string
  messages: number
  /** The terminal window can resume it: its tool and session are recorded. */
  canResume: boolean
  /** Claude Code and Codex can branch a chat. */
  canBranch: boolean
}

const RESUMABLE = new Set(['claude-code', 'codex', 'opencode'])
// The same check the server makes (termlib.resume_command): a session id that is no option.
const SAFE_REF = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/

export function agentView(d: AgentWire): AgentView {
  const a = d.agent
  const tool = a.tool ?? ''
  const ref = SAFE_REF.test(a.session_ref ?? '')
  return {
    id: a.agent_id,
    name: agentLabel(a),
    project: a.project ?? '',
    tool,
    lastActive: a.last_active || a.created_date || '',
    messages: a.message_count ?? 0,
    canResume: ref && RESUMABLE.has(tool),
    canBranch: ref && (tool === 'claude-code' || tool === 'codex'),
  }
}

export function useAgentCard(id: string) {
  return useQuery({
    queryKey: ['msgmenu', 'agent', id],
    queryFn: ({ signal }) => getJson<AgentWire>(`/api/agent/${encodeURIComponent(id)}`, signal).then(agentView),
    ...once,
  })
}

interface Mention { task_id: string; title: string; at: string }

/** The tasks a chat named, each once, the last named first. */
export function agentTasks(byAgent: Record<string, Mention[]>, id: string): Array<{ id: string; title: string }> {
  const seen = new Map<string, { id: string; title: string; at: string }>()
  for (const m of byAgent[id] ?? []) seen.set(m.task_id, { id: m.task_id, title: m.title, at: m.at })
  return [...seen.values()].sort((a, b) => b.at.localeCompare(a.at)).map(({ id: tid, title }) => ({ id: tid, title }))
}

export function useAgentTasks(id: string, project: string) {
  return useQuery({
    queryKey: ['msgmenu', 'agent-tasks', project, id],
    queryFn: ({ signal }) => getJson<{ agents: Record<string, Mention[]> }>(`/api/tasks/mentions/by-agent?project=${encodeURIComponent(project)}`, signal)
      .then((d) => agentTasks(d.agents ?? {}, id)),
    enabled: !!project,
    ...once,
  })
}

/* ------------------------------------------------------------ a commit */

export interface CommitWire {
  sha: string
  short: string
  project: string
  subject: string
  author: string
  at: string
  files: Array<{ path: string; add: number; del: number }>
  files_n: number
  add: number
  del: number
  tasks: string[]
  agent: string
  diff?: string
  diff_cut?: boolean
}

export const commitUrl = (project: string, sha: string, diff = false) =>
  `/api/git/commit?repo=${encodeURIComponent(project)}&sha=${encodeURIComponent(sha)}${diff ? '&diff=1' : ''}`

export function useCommit(project: string, sha: string) {
  return useQuery({
    queryKey: ['msgmenu', 'commit', project, sha],
    queryFn: ({ signal }) => getJson<CommitWire>(commitUrl(project, sha), signal),
    enabled: !!project && !!sha,
    ...once,
    staleTime: Infinity,
  })
}

export function useCommitDiff(project: string, sha: string, on: boolean) {
  return useQuery({
    queryKey: ['msgmenu', 'commit-diff', project, sha],
    queryFn: ({ signal }) => getJson<CommitWire>(commitUrl(project, sha, true), signal),
    enabled: on && !!project && !!sha,
    ...once,
    staleTime: Infinity,
  })
}

/**
 * Which hashes printed in one terminal are commits of its project: asked
 * once per hash (a 404 is "no"), the answer kept for the terminal's life.
 * `known` answers at once from what is kept; `check` asks when not.
 */
export class CommitCheck {
  private kept = new Map<string, boolean | Promise<boolean>>()
  constructor(private project: string, private ask: (url: string) => Promise<unknown> = (u) => getJson(u)) {}

  known(sha: string): boolean | undefined {
    const v = this.kept.get(sha)
    return typeof v === 'boolean' ? v : undefined
  }

  check(sha: string): Promise<boolean> {
    if (!this.project) return Promise.resolve(false)
    const v = this.kept.get(sha)
    if (v !== undefined) return Promise.resolve(v)
    // A 404 is the answer "no commit"; any other failure is asked again next time.
    const p = this.ask(commitUrl(this.project, sha)).then(
      () => { this.kept.set(sha, true); return true },
      (e: unknown) => {
        if ((e as { status?: number } | null)?.status === 404) this.kept.set(sha, false)
        else this.kept.delete(sha)
        return false
      },
    )
    this.kept.set(sha, p)
    return p
  }
}

/* ------------------------------------------------------------ a record's page address */

/**
 * The page of Slightly Parallel a record is on, as a path ('' for a commit:
 * it has none). A decision, a Publish card and a core are read first: their
 * page is their project's (and a decision's day).
 */
export async function pageAddress(kind: string, id: string, ask: <T>(url: string) => Promise<T> = getJson): Promise<string> {
  const q = encodeURIComponent(id)
  switch (kind) {
    case 'task': return `/kanban?task=${q}`
    case 'note': return `/notes?note=${q}`
    case 'decision': { const d = decisionView(await ask<DecisionWire>(`/api/decisions/${q}`)); return pageOf.decision(d.project, d.day) }
    case 'publish': return pageOf.publish((await ask<PublishCardWire>(`/api/publishing/cards/${q}`)).project)
    case 'core': return pageOf.core((await ask<CoreDetail>(`/api/cores/${q}`)).project, id)
    case 'skill': return pageOf.skill(id)
    case 'entrypoint': return pageOf.entrypoint(id)
    case 'agent': return pageOf.agent(id)
    default: return ''
  }
}
