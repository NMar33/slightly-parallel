import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { useMemo, useState } from 'react'
import { getJson } from '../../lib/getJson'
import { api, qk } from '../../lib/api'
import { formatYYMMDD, stampMs, todayYYMMDD } from '../../utils/dateUtils'

import { t, locale } from '../../i18n/scope/views'
/**
 * A month of days with their numbers, counted by the server from the
 * ledgers and git (`GET /api/standups/calendar`). Every day of the month is
 * present; a day nobody worked on has zeros.
 */
export interface DayNumbers {
  messages_n: number
  chats_n: number
  agents: string[]
  session_minutes: number
  /** Of the session minutes, the agents working. */
  agent_minutes?: number
  tasks_created_n: number
  tasks_done_n: number
  tasks_moved_n: number
  commits_n: number
  files_n: number
  lines_add: number
  lines_del: number
  tracked_minutes: number
  decisions_n: number
  standup_id: string
}

interface MonthData { project: string; month: string; days: Record<string, DayNumbers> }

export const ZERO: DayNumbers = {
  messages_n: 0, chats_n: 0, agents: [], session_minutes: 0, tasks_created_n: 0, tasks_done_n: 0,
  tasks_moved_n: 0, commits_n: 0, files_n: 0, lines_add: 0, lines_del: 0, tracked_minutes: 0,
  decisions_n: 0, standup_id: '',
}

/** 'YYYY-MM' of today, or of a shift of `delta` months. */
export function monthKey(from: Date = new Date(), delta = 0): string {
  const d = new Date(from.getFullYear(), from.getMonth() + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** '2026-09' → 'September 2026'. */
export function monthLabel(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return new Date(y!, (m ?? 1) - 1, 1).toLocaleDateString(locale(), { month: 'long', year: 'numeric' })
}

/** 'YYYY-MM' → the YYMM-DD keys of its days, in order. */
export function daysOfMonth(month: string): string[] {
  const [y, m] = month.split('-').map(Number)
  const out: string[] = []
  for (let n = 1; n <= 31; n++) {
    const d = new Date(y!, (m ?? 1) - 1, n)
    if (d.getMonth() !== (m ?? 1) - 1) break
    out.push(`${String(y! % 100).padStart(2, '0')}${String(m).padStart(2, '0')}-${String(n).padStart(2, '0')}`)
  }
  return out
}

/** '2609-21' → 'YYYY-MM' */
export function monthOfDay(day: string): string {
  const m = /^(\d{2})(\d{2})-\d{2}$/.exec(day)
  return m ? `20${m[1]}-${m[2]}` : ''
}

/**
 * How far back a day book's feed has been read: the oldest month it draws.
 * A page asks for the full text of an entry only from there on — the feed
 * adds a month as the reader nears the bottom, and its entries then. Every
 * entry's text at once was one request a row, a thousand on a long project.
 */
export function useReach(month: string): [string, (oldest: string) => void] {
  const [oldest, setOldest] = useState('')
  return [oldest && oldest < month ? oldest : month, setOldest]
}

/** Whether an entry of `day` (YYMM-DD) is in a month the feed draws. */
export const inReach = (day: string | null | undefined, reach: string): boolean => monthOfDay(day ?? '') >= reach

export const todayKey = (): string => todayYYMMDD()

/** A day of the week for the grid: 0 = Monday … 6 = Sunday. */
export function weekday(day: string): number {
  const ms = stampMs(day, '12:00')
  if (!ms) return 0
  return (new Date(ms).getDay() + 6) % 7
}

/** The day before, in YYMM-DD. */
export function dayBefore(day: string): string {
  const ms = stampMs(day, '12:00')
  if (!ms) return ''
  return formatYYMMDD(new Date(ms - 86_400_000))
}

/** The query for one month of a project's day numbers: shared by the month band and the focus list. */
export function monthQuery(project: string, month: string) {
  return {
    queryKey: ['standups-calendar', project, month],
    queryFn: ({ signal }: { signal: AbortSignal }) => getJson<MonthData>(
      `/api/standups/calendar?project=${encodeURIComponent(project)}&month=${encodeURIComponent(month)}`, signal),
    enabled: Boolean(project && month),
    staleTime: 60_000,
  }
}

export function useMonth(project: string, month: string) {
  return useQuery({ ...monthQuery(project, month), placeholderData: keepPreviousData })
}

/** Five steps of intensity from the messages of the day, against the busiest day of the month. */
export function intensity(n: number, max: number): 0 | 1 | 2 | 3 | 4 {
  if (n <= 0) return 0
  if (max <= 0) return 1
  const r = n / max
  return r > 0.75 ? 4 : r > 0.5 ? 3 : r > 0.25 ? 2 : 1
}

export function minutesLabel(min: number): string {
  if (min < 60) return t('{n} min', { n: min })
  const h = Math.floor(min / 60), m = min % 60
  return m ? t('{h} h {m} min', { h, m }) : t('{n} h', { n: h })
}

/**
 * The projects that have an entry, the one worked on most recently first.
 * A day book opens on that one, because a month of a project nobody has
 * touched is an empty page.
 */
export function projectsByNewest<T>(items: T[], project: (t: T) => string, day: (t: T) => string): string[] {
  const newest = new Map<string, string>()
  for (const it of items) {
    const code = project(it)
    if (!code) continue
    const d = day(it) || ''
    if (d > (newest.get(code) ?? '')) newest.set(code, d)
  }
  return [...newest.entries()].sort((a, b) => b[1].localeCompare(a[1])).map(([code]) => code)
}

/** Every project the switch offers: the ones with an entry, newest first,
 *  then the rest in the order the app lists them — so a project with no
 *  entry yet is still one click away. */
export function useDayBookProjects(withEntries: string[]): string[] {
  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal) })
  return useMemo(() => {
    const all = (snapshot.data?.projects ?? []).map((p) => p.code)
    return [...withEntries, ...all.filter((c) => !withEntries.includes(c))]
  }, [withEntries, snapshot.data])
}
