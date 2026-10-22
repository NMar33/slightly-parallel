/*
 * The numbers of the new home page (tk_f5eb92ff): a year of sessions, read
 * once, turned into the day's curve against a usual working day, the
 * day's counts, the year grid, the streak and the month against the month
 * before. Pure functions over the session rows, so the tests feed them rows.
 */
import { useMemo } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'
import { useDayStart } from '../../lib/clock'
import { formatYYMMDD, parseYYMMDD } from '../../utils/dateUtils'

export interface YearSession {
  id: string
  project: string
  agent_id: string
  created_date: string
  start_time: string
  end_time: string
  agent_min: number
  turns_n: number
  tasks?: number
  l1: string
  produced?: Record<string, number>
  git?: { commits?: number; add?: number; del?: number }
  agent?: { chat_title?: string }
}

/** Minutes in one step of the day curve. */
export const STEP = 10
const STEPS = 1440 / STEP
/** Entries an agent writes, as the day's count (the architecture rows are bookkeeping). */
const ENTRY_KINDS = ['decisions', 'scans', 'standups', 'visions', 'entrypoints', 'problems', 'rules', 'skills', 'artifacts', 'evidence']

function clock(hhmm: string): number {
  const [h, m] = String(hhmm || '').split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

export function dayKey(offset = 0, now = new Date()): string {
  return formatYYMMDD(new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset))
}

/** A day's agent minutes, spread evenly over each session, as a running total per step. */
export function dayCurve(sessions: YearSession[]): number[] {
  const per = new Array<number>(STEPS).fill(0)
  for (const s of sessions) {
    const min = Number(s.agent_min) || 0
    if (!min) continue
    const a = clock(s.start_time)
    let b = clock(s.end_time || s.start_time)
    if (b < a) b = 1440
    if (b - a < STEP) b = a + STEP
    const from = Math.floor(a / STEP)
    const to = Math.min(STEPS, Math.ceil(b / STEP))
    for (let i = from; i < to; i += 1) per[i]! += min / (to - from)
  }
  let run = 0
  return per.map((v) => (run += v))
}

export interface DayCounts { minutes: number; commits: number; tasks: number; entries: number; chats: number }

export function countsOf(sessions: YearSession[]): DayCounts {
  const out: DayCounts = { minutes: 0, commits: 0, tasks: 0, entries: 0, chats: 0 }
  const chats = new Set<string>()
  for (const s of sessions) {
    out.minutes += Number(s.agent_min) || 0
    out.commits += Number(s.git?.commits) || 0
    out.tasks += Number(s.tasks) || 0
    for (const k of ENTRY_KINDS) out.entries += Number(s.produced?.[k]) || 0
    chats.add(s.agent_id)
  }
  out.chats = chats.size
  return out
}

function byDay(sessions: YearSession[]): Map<string, YearSession[]> {
  const out = new Map<string, YearSession[]>()
  for (const s of sessions) {
    const row = out.get(s.created_date) ?? []
    row.push(s)
    out.set(s.created_date, row)
  }
  return out
}

export interface Usual { curve: number[]; counts: DayCounts; days: number }

/** The mean working day of the `n` days before `day`: days with agent time only. */
export function usualDay(days: Map<string, YearSession[]>, day: string, n = 30): Usual {
  const base = parseYYMMDD(day)
  const curves: number[][] = []
  const counts: DayCounts[] = []
  for (let i = 1; i <= n; i += 1) {
    const key = formatYYMMDD(new Date(base.getFullYear(), base.getMonth(), base.getDate() - i))
    const rows = days.get(key)
    if (!rows) continue
    const c = countsOf(rows)
    if (!c.minutes) continue
    curves.push(dayCurve(rows))
    counts.push(c)
  }
  const k = curves.length || 1
  const curve = new Array<number>(STEPS).fill(0).map((_, i) => curves.reduce((s, cv) => s + cv[i]!, 0) / k)
  const mean = (f: (c: DayCounts) => number) => counts.reduce((s, c) => s + f(c), 0) / k
  return {
    curve,
    days: curves.length,
    counts: { minutes: mean((c) => c.minutes), commits: mean((c) => c.commits), tasks: mean((c) => c.tasks), entries: mean((c) => c.entries), chats: mean((c) => c.chats) },
  }
}

/** Agent minutes per day, every day of the last `weeks` weeks (Monday first), oldest first. */
export function yearGrid(days: Map<string, YearSession[]>, now = new Date(), most = 53, least = 26): Array<{ day: string; date: Date; minutes: number; future: boolean }> {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const monday = new Date(today)
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
  // From the first week with agent time (at least `least` weeks, at most `most`).
  const first = [...days.keys()].sort()[0]
  const firstDate = first ? parseYYMMDD(first) : today
  const span = Math.ceil((monday.getTime() - firstDate.getTime()) / (7 * 86_400_000)) + 1
  const weeks = Math.max(least, Math.min(most, span))
  const start = new Date(monday)
  start.setDate(monday.getDate() - (weeks - 1) * 7)
  const out = []
  for (let i = 0; i < weeks * 7; i += 1) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
    const key = formatYYMMDD(d)
    out.push({ day: key, date: d, minutes: (days.get(key) ?? []).reduce((s, x) => s + (Number(x.agent_min) || 0), 0), future: d > today })
  }
  return out
}

/** Days in a row with agent time, ending today (or yesterday, while today is still empty). */
export function streak(days: Map<string, YearSession[]>, now = new Date()): number {
  const has = (off: number) => countsOf(days.get(dayKey(off, now)) ?? []).minutes > 0
  let off = has(0) ? 0 : -1
  let n = 0
  while (has(off)) { n += 1; off -= 1 }
  return n
}

export interface Period { minutes: number; commits: number; added: number; tasks: number; entries: number; activeDays: number }

/** Totals of the `n` days ending `offset` days before today. */
export function period(days: Map<string, YearSession[]>, n: number, offset = 0, now = new Date()): Period {
  const out: Period = { minutes: 0, commits: 0, added: 0, tasks: 0, entries: 0, activeDays: 0 }
  for (let i = offset; i < offset + n; i += 1) {
    const rows = days.get(dayKey(-i, now)) ?? []
    const c = countsOf(rows)
    out.minutes += c.minutes
    out.commits += c.commits
    out.tasks += c.tasks
    out.entries += c.entries
    out.added += rows.reduce((s, x) => s + (Number(x.git?.add) || 0), 0)
    if (c.minutes) out.activeDays += 1
  }
  return out
}

/** The most chats the year asks for; a fuller year shows its latest this many. */
export const YEAR_LIMIT = 5000

/** A year of rows by day; `truncated` when the server stopped at the limit. */
export function yearOf(sessions: YearSession[] | undefined) {
  const days = byDay(sessions ?? [])
  return { ready: !!sessions, sessions: sessions ?? [], days, truncated: (sessions?.length ?? 0) >= YEAR_LIMIT }
}

export function useYear() {
  const dayStart = useDayStart()
  const from = useMemo(() => dayKey(-371, new Date(dayStart)), [dayStart])
  const q = useQuery({
    queryKey: ['overview', 'year', from],
    queryFn: ({ signal }) => getJson<{ sessions: YearSession[] }>(`/api/sessions?limit=${YEAR_LIMIT}&from_date=${from}`, signal),
    staleTime: 30_000,
    refetchInterval: 60_000,
    // At midnight `from` moves a day: keep showing the old year until the new one arrives.
    placeholderData: keepPreviousData,
  })
  const sessions = q.data?.sessions
  return useMemo(() => yearOf(sessions), [sessions])
}

export type Year = ReturnType<typeof useYear>
