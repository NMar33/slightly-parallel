import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { getJson, postJson } from '../../../lib/getJson'

/**
 * Entry points: the topics the operator comes back to (backend
 * entrypointlib.py, routers/entrypoints.py). The wire shapes, the reads
 * and the operator's writes. Every write invalidates the entry point reads.
 */

export type TopicState = 'active' | 'paused' | 'dead'
export const STATES: TopicState[] = ['active', 'paused', 'dead']
export type WayKind = 'page' | 'site' | 'app' | 'file' | 'folder' | 'script' | 'artifact'
export const WAY_KINDS: WayKind[] = ['page', 'site', 'app', 'file', 'folder', 'script', 'artifact']

export interface Way {
  id: string
  name: string
  kind: WayKind | string
  url: string
  path: string
  command: string
  folder: string
  note: string
  port: number | null
  actor: string
  updated_at: string
}

export interface Stop { id: string; at: string; author: string; text: string; task_id: string; turn: number }

export interface Shot {
  id: string
  way_id: string
  caption: string
  at: string
  author: string
  /** The chat it was taken in; "" when the operator set it by hand. */
  agent_id: string
  width: number
  height: number
  src: string
}

export interface Topic {
  id: string
  project: string
  /** The operator's name; "" until one is written. */
  name: string
  /** The #entrypoint message's first line. */
  title: string
  state: TopicState
  no_project: boolean
  home: string
  /** The record's What, first paragraph. */
  what: string
  has_record: boolean
  versions: number
  created: string
  agent_id: string
  ways: Way[]
  /** The last five, newest first. */
  stops: Stop[]
  stops_n: number
  /** Oldest first. */
  shots: Shot[]
  open_tasks: number
  chats: number
  last_at: string
}

export interface Desk { topics: Topic[]; projects: string[] }

export interface ChatLine { who: 'you' | 'agent'; at: string; text: string; turn: number; unanswered?: boolean }

export interface TopicChat {
  id: string
  name: string
  tool: string
  session_ref: string
  cwd: string
  first: string
  last: string
  messages: number
  turns: number[]
  origin: boolean
  did: string
  tail: ChatLine[]
  commits: number
  live: boolean
  from: { id: string; how: 'handoff' | 'branch' } | null
  waiting: boolean
  waiting_text: string
  waiting_at: string
}

export interface OpenTask { id: string; title: string; status: string }
export interface DoneTask { id: string; title: string; done: string; chat: string; report: string }
export interface Decision { id: string; at: string; weight: 'minor' | 'normal' | 'major' | string; title: string; chat: string }
export interface Commit { sha: string; at: string; subject: string; chat: string; files: number; add: number; del: number; tasks: string[] }
export interface Touched { path: string; add: number; del: number }
export interface Made { id: string; kind: 'artifact' | 'card'; name: string; at: string; chat: string; sub: string }
export interface Spend { tokens: number; dollars: number; by_chat: Record<string, { tokens: number; dollars: number; turns: number }> }

export interface Context {
  id: string
  chats: TopicChat[]
  open: OpenTask[]
  done: DoneTask[]
  decisions: Decision[]
  commits: Commit[]
  commits_n: number
  files: Touched[]
  files_n: number
  made: Made[]
  spend: Spend | null
  tasks_n: number
  tasks_truncated: boolean
  briefing: string
}

export interface PortState { id: string; port: number | null; up: boolean | null; why: string }

export interface RecordVersion { n: number; at: string; how: string; note: string; text: string }
export interface Kept { message: string; versions: RecordVersion[]; current: RecordVersion | null }

const KEY = ['entrypoints'] as const

export const displayName = (tp: Pick<Topic, 'name' | 'title' | 'id'>) => tp.name || tp.title || tp.id

export function useDesk(project?: string) {
  return useQuery({
    queryKey: [...KEY, 'desk', project ?? ''],
    queryFn: ({ signal }) => getJson<Desk>(`/api/entrypoints/desk?project=${encodeURIComponent(project ?? '')}`, signal),
  })
}

export function useTopicContext(id: string) {
  return useQuery({
    queryKey: [...KEY, 'context', id],
    queryFn: ({ signal }) => getJson<Context>(`/api/entrypoints/${encodeURIComponent(id)}/context`, signal),
    enabled: !!id,
  })
}

/** Whether each way in is up: its own query, so the page never waits for it. */
export function usePorts(id: string, enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'ports', id],
    queryFn: ({ signal }) => getJson<{ ways: PortState[] }>(`/api/entrypoints/${encodeURIComponent(id)}/ports`, signal),
    enabled: !!id && enabled,
    staleTime: 15_000,
    refetchInterval: 60_000,
  })
}

export function useRecord(id: string) {
  return useQuery({
    queryKey: [...KEY, 'record', id],
    queryFn: ({ signal }) => getJson<{ kept?: Kept; l4?: string }>(`/api/entrypoints/${encodeURIComponent(id)}`, signal),
    enabled: !!id,
  })
}

export interface BoardTask { id: string; title: string; status: string; archived_at?: string | null }

/** The project's tasks, for setting a task's topic. */
export function useProjectTasks(project: string, enabled: boolean) {
  return useQuery({
    queryKey: ['tasks', 'ep-picker', project],
    queryFn: ({ signal }) => getJson<{ tasks: BoardTask[] }>(`/api/tasks?project=${encodeURIComponent(project)}`, signal),
    enabled: !!project && enabled,
  })
}

const at = (id: string, rest: string) => `/api/entrypoints/${encodeURIComponent(id)}/${rest}`

/** The operator's writes, each refreshing what the page reads. */
export function useEntryWrites(id: string) {
  const qc = useQueryClient()
  const done = () => { void qc.invalidateQueries({ queryKey: KEY }) }
  const opts = { onSuccess: done }
  return {
    addStop: useMutation({ mutationFn: (text: string) => postJson(at(id, 'stops'), { text }), ...opts }),
    removeStop: useMutation({ mutationFn: (stopId: string) => postJson(at(id, `stops/${encodeURIComponent(stopId)}/remove`), {}), ...opts }),
    setState: useMutation({ mutationFn: (state: TopicState) => postJson(at(id, 'state'), { state }), ...opts }),
    setName: useMutation({ mutationFn: (name: string) => postJson(at(id, 'name'), { name }), ...opts }),
    putWay: useMutation({
      mutationFn: (v: { way: Partial<Way>; id?: string }) => postJson(at(id, 'ways'), v.id ? { id: v.id, way: v.way } : { way: v.way }),
      ...opts,
    }),
    removeWay: useMutation({ mutationFn: (wayId: string) => postJson(at(id, `ways/${encodeURIComponent(wayId)}/remove`), {}), ...opts }),
    addShot: useMutation({
      mutationFn: (v: { way_id: string; data_base64: string; caption: string; replaces?: string }) => postJson(at(id, 'shots'), v),
      ...opts,
    }),
    setTaskTopic: useMutation({
      mutationFn: (v: { task: string; topic: string }) =>
        postJson(`/api/tasks/${encodeURIComponent(v.task)}/topic`, { entrypoint_id: v.topic }),
      onSuccess: () => { done(); void qc.invalidateQueries({ queryKey: ['tasks'] }) },
    }),
  }
}

/** A picked image file as base64 (without the data: prefix). */
export function fileToBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result ?? '').replace(/^data:[^,]*,/, ''))
    r.onerror = () => reject(r.error ?? new Error('read failed'))
    r.readAsDataURL(file)
  })
}

/* ---------------------------------------------------------------- reading */

export const newestFirst = (stops: Stop[]) => [...stops].sort((a, b) => b.at.localeCompare(a.at))

const STATE_ORDER: Record<TopicState, number> = { active: 0, paused: 1, dead: 2 }

/** Topics in reading order: active first, then the most recently written to. */
export function byStateThenRecent(list: Topic[]): Topic[] {
  return [...list].sort((a, b) => (STATE_ORDER[a.state] ?? 0) - (STATE_ORDER[b.state] ?? 0) || b.last_at.localeCompare(a.last_at))
}

/** Ways in that run on this computer: a port, or a local URL. */
export const isLocal = (w: Way) => !!w.port || /^https?:\/\/(localhost|127\.|0\.0\.0\.0|\[::1\])/i.test(w.url)

/** The topic's servers, one per port. */
export function serversByPort(tp: Topic): Way[] {
  const seen = new Set<string>()
  return tp.ways.filter(isLocal).filter((w) => {
    const k = String(w.port ?? w.url)
    return seen.has(k) ? false : (seen.add(k), true)
  })
}

/** The topic's shots of one way in, oldest first. */
export const shotsOfWay = (tp: Topic, way: string) => tp.shots.filter((s) => s.way_id === way)

/** Whether the words in the find box occur in a topic: name, what, ways, stops, captions, project. */
export function matches(tp: Topic, query: string, extra = ''): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = [
    tp.name, tp.title, tp.what, tp.project, tp.id,
    ...tp.ways.flatMap((w) => [w.name, w.url, w.path, w.command, w.folder, w.port ? `:${w.port}` : '', w.port ? String(w.port) : '']),
    ...tp.stops.map((m) => m.text),
    ...tp.shots.map((s) => s.caption),
    extra,
  ].join('\n').toLowerCase()
  return q.split(/\s+/).every((word) => hay.includes(word))
}

/** The resume command of a chat (AgentDrill.resumeCommand, with the chat's own folder). */
export { resumeCommand } from '../../project/AgentDrill'
