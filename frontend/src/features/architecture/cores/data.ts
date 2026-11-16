import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { getJson, postJson } from '../../../lib/getJson'
import { OPERATOR_ACTOR } from '../../project/types'

/**
 * Cores: the program's core elements the operator keeps in view, each with
 * its story (backend corelib.py, routers/cores.py). The wire shapes, the
 * reads and the operator's writes.
 */

export const CORE_TYPES = [
  'capability', 'feature', 'interface', 'store', 'integration', 'internals', 'workflow', 'experiment',
] as const
export type CoreType = (typeof CORE_TYPES)[number]

/** The colour of a type (tokens.css --core-*): the kind of thing, never its condition. */
export const coreColor = (type: string): string => `var(--core-${CORE_TYPES.includes(type as CoreType) ? type : 'internals'})`

export interface Tracking { on: boolean; until: string; days_left: number | null; expired: boolean }
export interface GridDay { day: string; story: number; nearby: number }

export interface CoreNote {
  id: string
  core_id: string
  at: string
  author: string
  kind: 'founding' | 'note' | 'auto' | string
  text: string
  comment: string
  task_id: string
  session_id: string
  turn: string
  approved_at: string
  approved_by: string
  approved: boolean
}

export interface CoreLink { id: string; core_id: string; kind: string; target: string; note: string; at: string; actor: string }

export interface CoreBase {
  id: string
  project: string
  name: string
  type: string
  reason: string
  status: 'view' | 'off' | string
  position: string
  tracking_on: string
  tracking_until: string
  created_at: string
  updated_at: string
  actor: string
  off_at: string
  tracking: Tracking
  grid: GridDay[]
}

export interface CoreSummary extends CoreBase {
  notes_n: number
  pending_n: number
  last_note: { at: string; text: string; comment: string; author: string; kind: string; approved: boolean } | null
  tasks_n: number
  open_n: number
  anchors: string[]
}

export interface CoreTask { id: string; title: string; status: string; archived_at: string; created_date: string }
/** A file the core's linked tasks changed: lines over all of them, and which tasks. */
export interface CoreFile { path: string; lines_add: number; lines_del: number; tasks?: string[] }
/** A commit of the core's linked tasks. `how`: signed (a Task: line), linked
 *  (task_commits) or chat (found in the task's stretch of a chat). */
export interface CoreCommit { sha: string; at: string; subject: string; how: 'signed' | 'linked' | 'chat' | string; agent: string; tasks: string[]; files: string[] }
/** An agent that worked on the core: its chats named the core's tasks, it made
 *  their commits, or it wrote notes on the core. */
export interface CoreAgent { agent_id: string; tasks: string[]; given?: string[]; commits: number; notes: number; turns: number; sessions: number; last_at: string }
export interface NearbyCommit { sha: string; at: string; subject: string; files: string[] }

/** A switch on the core itself: created · tracking_on (value: its end, or
 *  none) · tracking_off · off · view. */
export interface CoreEvent { id: string; core_id: string; at: string; kind: string; value: string; actor: string }

export interface CoreDetail extends CoreBase {
  notes: CoreNote[]
  links: CoreLink[]
  tasks: CoreTask[]
  files: CoreFile[]
  commits_n: number
  nearby: NearbyCommit[]
  events: CoreEvent[]
  /** Every commit of the linked tasks once, newest first. */
  commits: CoreCommit[]
  agents: CoreAgent[]
}

export const coresKey = (project: string) => ['cores', project] as const
export const coreKey = (id: string) => ['core', id] as const

export function useCores(project: string) {
  return useQuery({
    queryKey: coresKey(project),
    queryFn: ({ signal }) => getJson<{ cores: CoreSummary[]; types: string[] }>(`/api/cores?project=${encodeURIComponent(project)}`, signal),
    enabled: !!project,
  })
}

export function useCore(id: string) {
  return useQuery({
    queryKey: coreKey(id),
    queryFn: ({ signal }) => getJson<CoreDetail>(`/api/cores/${encodeURIComponent(id)}`, signal),
    enabled: !!id,
  })
}

/** The operator's writes on cores; each refreshes the list and the core. */
export function useCoreWrites(project: string, id?: string) {
  const qc = useQueryClient()
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: coresKey(project) })
    if (id) void qc.invalidateQueries({ queryKey: coreKey(id) })
  }
  const path = (tail: string) => `/api/cores/${encodeURIComponent(id ?? '')}${tail}`
  const op = { actor: OPERATOR_ACTOR }
  return {
    create: useMutation({
      mutationFn: (input: { name: string; type: string; reason?: string; text?: string; anchors?: string[] }) =>
        postJson<{ core: CoreBase; existing: boolean }>('/api/cores', { project, ...op, ...input }),
      onSuccess: refresh,
    }),
    note: useMutation({
      mutationFn: (input: { text: string; task_id?: string }) => postJson(path('/notes'), { ...op, ...input }),
      onSuccess: refresh,
    }),
    approve: useMutation({
      mutationFn: (noteId: string) => postJson(path(`/notes/${encodeURIComponent(noteId)}/approve`), op),
      onSuccess: refresh,
    }),
    tracking: useMutation({
      mutationFn: (input: { on: boolean; span?: 'day' | 'week'; until?: string }) => postJson(path('/tracking'), { ...op, ...input }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: (input: { name?: string; type?: string; reason?: string; position?: string; status?: 'view' | 'off' }) =>
        postJson(path('/update'), { ...op, ...input }),
      onSuccess: refresh,
    }),
    link: useMutation({
      mutationFn: (input: { kind: string; target: string; note?: string }) => postJson(path('/links'), { ...op, ...input }),
      onSuccess: refresh,
    }),
    unlink: useMutation({
      mutationFn: (linkId: string) => postJson(path('/links'), { ...op, remove: linkId }),
      onSuccess: refresh,
    }),
  }
}

/** The note a tile or a header shows: with "operator" on, the latest note
 *  the operator wrote or approved; else the latest of all. */
export function shownNote<N extends { author: string; approved: boolean }>(notes: N[], operatorOnly: boolean): N | null {
  const list = operatorOnly ? notes.filter((n) => n.approved) : notes
  return list.length ? list[list.length - 1]! : null
}

/** The grid as five weeks of seven days, oldest first, Monday on top:
 *  cells before the first day are null (the row is drawn blank). */
export function weeksOf(grid: GridDay[]): Array<Array<GridDay | null>> {
  if (grid.length === 0) return []
  const first = new Date(`${grid[0]!.day}T00:00:00`)
  const lead = (first.getDay() + 6) % 7   // Monday = 0
  const cells: Array<GridDay | null> = [...Array<null>(lead).fill(null), ...grid]
  while (cells.length % 7) cells.push(null)
  const weeks: Array<Array<GridDay | null>> = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}

// ---------------------------------------------------------------------------
// The timeline (GET /api/cores/timeline): one lane per core, day by day
// ---------------------------------------------------------------------------

export interface LaneNote { id: string; at?: string; kind: string; operator: boolean; approved: boolean; text: string; author: string }
export interface LaneTask { id: string; title: string; at?: string }
export interface LaneCommit { sha: string; at: string; subject: string; task_id?: string; files?: string[] }
export interface LaneDay { notes?: LaneNote[]; made?: LaneTask[]; done?: LaneTask[]; commits?: LaneCommit[]; nearby?: LaneCommit[] }
export interface Lane {
  id: string
  name: string
  type: string
  reason: string
  tracking: Tracking
  tracking_spans: Array<{ from: string; to: string }>
  created: string
  days: Record<string, LaneDay>
  totals: { notes: number; made: number; done: number; commits: number; nearby: number }
}
export interface Timeline {
  project: string
  first: string
  last: string
  days: string[]
  standups: Record<string, { id: string; summary: string }>
  releases: Array<{ name: string; day: string }>
  lanes: Lane[]
}

export function useTimeline(project: string, days: number) {
  return useQuery({
    queryKey: ['cores', project, 'timeline', days],
    queryFn: ({ signal }) => getJson<Timeline>(`/api/cores/timeline?project=${encodeURIComponent(project)}&days=${days}`, signal),
    enabled: !!project,
  })
}

// ---------------------------------------------------------------------------
// Cores over the map (GET /api/cores/map)
// ---------------------------------------------------------------------------

export type ClaimHow = 'linked' | 'files' | 'tasks'
export interface MapClaimRow { kind: string; name: string; what: string; where: string; cores: Array<{ id: string; how: ClaimHow; link_id?: string }> }
export interface CoresMap {
  project: string
  version: number | null
  template: string
  rows: MapClaimRow[]
  cores: Array<{ id: string; name: string; type: string; rows: number }>
  unclaimed: number
}

export function useCoresMap(project: string) {
  return useQuery({
    queryKey: ['cores', project, 'map'],
    queryFn: ({ signal }) => getJson<CoresMap>(`/api/cores/map?project=${encodeURIComponent(project)}`, signal),
    enabled: !!project,
  })
}

// ---------------------------------------------------------------------------
// Tasks and cores
// ---------------------------------------------------------------------------

export interface TaskCore { id: string; name: string; type: string; status: string; link_id: string }

/** Task id → its cores, for the board's cards. */
export function useCoreTaskIndex(project: string) {
  return useQuery({
    queryKey: ['cores', project, 'tasks'],
    queryFn: ({ signal }) => getJson<{ tasks: Record<string, Array<{ id: string; name: string; type: string }>> }>(
      `/api/cores/tasks?project=${encodeURIComponent(project)}`, signal),
    enabled: !!project,
  })
}

export function useTaskCores(taskId: string) {
  return useQuery({
    queryKey: ['core', 'task', taskId],
    queryFn: ({ signal }) => getJson<{ task_id: string; cores: TaskCore[] }>(`/api/tasks/${encodeURIComponent(taskId)}/cores`, signal),
    enabled: !!taskId,
  })
}

/** The operator sets the task's cores; the lists that show them refresh. */
export function useSetTaskCores(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (cores: string[]) => postJson<{ cores: TaskCore[] }>(`/api/tasks/${encodeURIComponent(taskId)}/cores`, { actor: OPERATOR_ACTOR, cores }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['core'] })
      void qc.invalidateQueries({ queryKey: ['cores'] })
    },
  })
}
