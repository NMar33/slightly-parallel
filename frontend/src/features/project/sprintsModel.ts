/*
 * What the sprint views share: the row, the three status groups, the pace
 * verdict, and the reads of one block (its day series, its detail). The
 * reads are keyed under 'sprints', so the freshness stamp (area "tasks")
 * brings them in again, and two views of one block are one request.
 */
import { useQueries, useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'
import type { EntryDetailLike } from '../../lib/entryText'
import type { SprintBoardRow } from '../tasks/data'
import { t } from '../../i18n/scope/project'

export type SprintRow = SprintBoardRow

/** One day of `/api/sprints/{id}/series`. */
export type SeriesDay = { date: string; scope: number; done: number; human_min: number; agent_min: number; events: number }

export const pct = (x: number) => Math.round(x * 100)
export const clamp01 = (x: number) => Math.max(0, Math.min(1, x))

/** Real statuses collapse into the three the sprint views speak. */
export function groupOf(status: string | undefined): 'doing' | 'done' | 'todo' {
  const s = (status ?? '').toLowerCase()
  return s === 'done' || s === 'done-archived' ? 'done' : s === 'doing' || s === 'review' ? 'doing' : 'todo'
}

export function verdictOf(s: SprintRow): { verdict: string; cls: string } {
  if (s.days_left != null && s.days_left < 0) return { verdict: `overdue ${-s.days_left}d`, cls: 'text-status-red' }
  const bet = Number(s.bet_days) || 0
  const timeF = bet > 0 && s.days_left != null ? (bet - s.days_left) / bet : 0
  const workF = s.tasks_total > 0 ? s.tasks_done / s.tasks_total : 0
  if (workF - timeF > 0.15) return { verdict: 'ahead', cls: 'text-status-green' }
  if (timeF - workF > 0.15) return { verdict: 'behind', cls: 'text-status-amber' }
  return { verdict: t('on pace'), cls: 'text-tertiary' }
}

const seriesQuery = (id: string) => ({
  queryKey: ['sprints', 'series', id] as const,
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    getJson<{ days?: SeriesDay[] }>(`/api/sprints/${encodeURIComponent(id)}/series`, signal)
      .then((d) => (Array.isArray(d?.days) ? d.days : [])),
})

/** One block's days; off until `enabled`. */
export function useSprintSeries(id: string | undefined, enabled = true) {
  return useQuery({ ...seriesQuery(id ?? ''), enabled: enabled && !!id })
}

/** Every block's days by id: undefined while a read is out, [] when it failed. */
export function useSprintsSeries(ids: string[]): Record<string, SeriesDay[] | undefined> {
  return useQueries({
    queries: ids.map(seriesQuery),
    combine: (results) => Object.fromEntries(ids.map((id, i) => {
      const r = results[i]
      return [id, r?.data ?? (r?.isError ? [] : undefined)]
    })),
  })
}

/** A task's stay on a sprint: the day it joined and the day it was done. */
export type SpanTask = { id: string; title: string; status: string; joined: string; done: string | null }

/** One sprint of `/api/sprints/timeline`. */
export type TimelineSprint = {
  id: string
  name: string
  status: string
  started: string
  ended: string | null
  bet_days?: number | null
  budget_h?: number | null
  tasks: SpanTask[]
  human_min: number
  agent_min: number
}

/** Every sprint of a project, settled ones too, with task spans and clocks. */
export const sprintsTimelineQuery = (project: string) => ({
  queryKey: ['sprints', 'timeline', project] as const,
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    getJson<{ sprints?: TimelineSprint[] }>(`/api/sprints/timeline?project=${encodeURIComponent(project)}`, signal),
})

/** The block's own entry: its goals (l3) and notes, as the lens detail holds them. */
export function useSprintDetail(id: string) {
  return useQuery({
    queryKey: ['sprints', 'detail', id],
    queryFn: ({ signal }) => getJson<EntryDetailLike>(`/api/sprints/${encodeURIComponent(id)}`, signal),
    enabled: !!id,
  })
}
