/**
 * The calendar's data layer — one read per range, writes that invalidate it.
 *
 * Every variant calls `useCalendar(project, from, to)` and gets the same
 * payload; a variant that fetched its own tasks could disagree with the
 * one beside it. Writes go through `useCalendarWrites` so the cache is
 * refreshed the same way whichever page made the change.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, qk } from '../../lib/api'
import { getJson, postJson } from '../../lib/getJson'
import { persistPref, readPref } from '../../lib/uiPrefs'
import { OPERATOR_ACTOR } from '../project/types'
import { toSpDate, type CalEntry, type CalendarPayload, type Milestone } from './model'

import { t } from '../../i18n/scope/views'
const calendarKey = (project: string, from: string, to: string) => ['calendar', project, from, to] as const

export function useCalendar(project: string, from: string, to: string) {
  return useQuery({
    queryKey: calendarKey(project, from, to),
    queryFn: ({ signal }) => getJson<CalendarPayload>(`/api/calendar?project=${encodeURIComponent(project)}&from=${from}&to=${to}`, signal),
    enabled: !!project,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  })
}

/** The project codes the dashboard knows, for the picker. */
export function useProjectCodes(): string[] {
  const { data } = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal) })
  return (data?.projects ?? []).map((p) => p.code)
}

/** A saved Kanban board: a name over member projects, or a standalone
 *  board whose tasks live under its own data-only code. */
interface SavedBoard { id: string; name: string; projects: string[]; standalone?: boolean }

function useBoardsQuery() {
  return useQuery({
    queryKey: ['boards'],
    queryFn: ({ signal }) => getJson<{ boards: SavedBoard[] }>('/api/boards', signal),
    staleTime: 30_000,
  })
}
export function useBoards(): SavedBoard[] {
  return useBoardsQuery().data?.boards ?? []
}

/** The project the operator last wrote under from the calendar — the
 *  default when the scope is wide, instead of whichever code sorts first. */
const LAST_PROJECT_PREF = 'sp-calendar-project'
export function lastProject(choices: string[], fallback = ''): string {
  const last = readPref(LAST_PROJECT_PREF) ?? ''
  if (last && choices.includes(last)) return last
  return choices[0] ?? fallback
}
export function rememberProject(code: string): void {
  if (code) persistPref(LAST_PROJECT_PREF, code)
}

/**
 * What the calendar is looking at. `key` is what the API is asked for
 * (one code, a comma list, or `all`); `codes` are the projects behind it
 * once known; `value` is the picker's choice (`all` · code · `board:id`).
 */
export interface Scope { key: string; codes: string[]; multi: boolean; value: string; label: string }

export function useScope(hash: Record<string, string>, projectCode?: string): Scope {
  const boardsQ = useBoardsQuery()
  const boards = boardsQ.data?.boards ?? []
  if (projectCode) return { key: projectCode, codes: [projectCode], multi: false, value: projectCode, label: projectCode }
  const boardId = hash.board ?? ''
  if (boardId) {
    const b = boards.find((x) => x.id === boardId)
    const codes = b?.projects ?? []
    // Until the boards are known the key is empty and nothing is fetched —
    // no flash of the all-projects read before the board's own.
    const key = codes.length ? codes.join(',') : boardsQ.data ? 'all' : ''
    return { key, codes, multi: codes.length !== 1, value: `board:${boardId}`, label: b?.name ?? 'board' }
  }
  const raw = (hash.project ?? 'all').trim() || 'all'
  if (raw === 'all') return { key: 'all', codes: [], multi: true, value: 'all', label: t('all projects') }
  const codes = raw.split(',').map((c) => c.trim()).filter(Boolean)
  return { key: codes.join(','), codes, multi: codes.length !== 1, value: codes.length === 1 ? codes[0]! : raw, label: codes.join(', ') }
}

/** The hash patch for a picker choice. */
export function scopePatch(value: string): Record<string, string> {
  if (value.startsWith('board:')) return { board: value.slice(6), project: '' }
  return { project: value === 'all' ? '' : value, board: '' }
}

export interface EntryInput {
  /** The project the row is written under; the scope's when absent. */
  project?: string
  kind: string
  date: string
  title: string
  time?: string
  end_date?: string
  end_time?: string
  body?: string
  task_id?: string
  milestone_id?: string
  people?: string
  link?: string
  status?: string
}

export interface MilestoneInput {
  project?: string
  title: string
  proof?: string
  outcome?: string
  check?: string
  target_date?: string
  status?: string
  position?: number
  tasks?: string[]
}

export function useCalendarWrites(project: string) {
  const qc = useQueryClient()
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['calendar'] })
    void qc.invalidateQueries({ queryKey: ['milestones'] })
    void qc.invalidateQueries({ queryKey: ['milestone-tasks'] })
    void qc.invalidateQueries({ queryKey: ['tasks'] })
    void qc.invalidateQueries({ queryKey: ['lens', 'tasks'] })
  }
  const createEntry = useMutation({
    mutationFn: (input: EntryInput) => {
      rememberProject(input.project || project)
      return postJson<{ entry: CalEntry }>('/api/calendar/entries', { project, actor: OPERATOR_ACTOR, ...input })
    },
    onSuccess: refresh,
  })
  const updateEntry = useMutation({
    mutationFn: ({ id, ...patch }: Partial<EntryInput> & { id: string }) => postJson<{ entry: CalEntry }>(`/api/calendar/entries/${encodeURIComponent(id)}/update`, patch),
    onSuccess: refresh,
  })
  const deleteEntry = useMutation({
    mutationFn: (id: string) => postJson<{ deleted: string }>(`/api/calendar/entries/${encodeURIComponent(id)}/delete`, {}),
    onSuccess: refresh,
  })
  const createMilestone = useMutation({
    mutationFn: (input: MilestoneInput) => {
      rememberProject(input.project || project)
      return postJson<{ milestone: Milestone }>('/api/milestones', { project, actor: OPERATOR_ACTOR, ...input })
    },
    onSuccess: refresh,
  })
  const updateMilestone = useMutation({
    mutationFn: ({ id, ...patch }: Partial<MilestoneInput> & { id: string; reached_date?: string }) => postJson<{ milestone: Milestone }>(`/api/milestones/${encodeURIComponent(id)}/update`, patch),
    onSuccess: refresh,
  })
  const deleteMilestone = useMutation({
    mutationFn: (id: string) => postJson<{ deleted: string }>(`/api/milestones/${encodeURIComponent(id)}/delete`, {}),
    onSuccess: refresh,
  })
  const linkTasks = useMutation({
    mutationFn: ({ id, add = [], remove = [] }: { id: string; add?: string[]; remove?: string[] }) =>
      postJson<{ milestone: Milestone }>(`/api/milestones/${encodeURIComponent(id)}/tasks`, { add, remove, actor: OPERATOR_ACTOR }),
    onSuccess: refresh,
  })
  /** A task's own dates: due_date · today_on · resurface_on · status. The
   *  task window keeps `due_date` in Slightly Parallel's YYMM-DD form; an ISO day
   *  handed in here is converted, so every variant writes the same form. */
  const patchTask = useMutation({
    mutationFn: ({ id, ...patch }: { id: string } & Record<string, string>) => {
      const body: Record<string, string> = { ...patch, actor: OPERATOR_ACTOR }
      if (body.due_date !== undefined) body.due_date = toSpDate(body.due_date)
      return postJson<unknown>(`/api/tasks/${encodeURIComponent(id)}/update`, body)
    },
    onSuccess: refresh,
  })
  return { createEntry, updateEntry, deleteEntry, createMilestone, updateMilestone, deleteMilestone, linkTasks, patchTask, refresh }
}
