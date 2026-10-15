/**
 * Task statistics, read (backend statslib.py, GET /api/stats/tasks).
 *
 * The server sends one row per task; every page aggregates here. A row's
 * `stretch` says whether its messages are exact (#done) or estimated.
 */

import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'
import { isoDay } from '../../utils/dateUtils'

export interface TaskStat {
  id: string
  title: string
  project: string
  status: string
  done: boolean
  sprint_id: string
  created: string
  first: string
  done_at: string
  lead_hours: number | null
  work_hours: number | null
  messages: number
  chats: number
  minutes: number
  agents: string[]
  commits: number
  files: number
  add: number
  del: number
  closed: '' | '#done' | 'board'
  stretch: 'done' | 'estimated' | 'none'
  reopened: number
  reports: number
}

export function useTaskStats() {
  return useQuery({
    queryKey: ['tasks', 'stats'],
    queryFn: ({ signal }) => getJson<{ total: number; tasks: TaskStat[] }>('/api/stats/tasks', signal),
    staleTime: 60_000,
  })
}

export const CLOSED_COLOR = { '#done': 'var(--s-done)', board: 'var(--s-board)' } as const

export type Period = '30' | '90' | 'all'

export interface Cut { project: string; period: Period }

export function cut(rows: TaskStat[], c: Cut, now: Date = new Date()): TaskStat[] {
  // The first day of the period, counted in local days as done_at is written.
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - Number(c.period))
  const from = c.period === 'all' ? '' : isoDay(start)
  return rows.filter((r) => (!c.project || r.project === c.project) && r.done && (!from || r.done_at.slice(0, 10) >= from))
}

export function median(xs: Array<number | null | undefined>): number | null {
  const v = xs.filter((x): x is number => x != null && Number.isFinite(x)).sort((a, b) => a - b)
  if (!v.length) return null
  const m = Math.floor(v.length / 2)
  return v.length % 2 ? v[m]! : (v[m - 1]! + v[m]!) / 2
}

/** Hours as a person says them. */
export function hours(h: number | null | undefined): string {
  if (h == null) return '—'
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`
  if (h < 48) return `${h < 10 ? h.toFixed(1).replace(/\.0$/, '') : Math.round(h)} h`
  return `${Math.round(h / 24)} days`
}

export const mins = (m: number | null | undefined) => (m == null ? '—' : hours(m / 60))

/** What every page leads with. */
export function summary(rows: TaskStat[]) {
  const seen = rows.filter((r) => r.stretch !== 'none')
  return {
    done: rows.length,
    inChat: seen.length,
    exact: rows.filter((r) => r.stretch === 'done').length,
    byDone: rows.filter((r) => r.closed === '#done').length,
    messages: median(seen.map((r) => r.messages)),
    minutes: median(seen.map((r) => r.minutes)),
    commits: median(seen.map((r) => r.commits)),
    lead: median(rows.map((r) => r.lead_hours)),
    work: median(rows.map((r) => r.work_hours)),
    reopened: rows.filter((r) => r.reopened > 0).length,
  }
}
