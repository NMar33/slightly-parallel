/**
 * The Timer page's numbers, from the time entries of every project: per
 * project and per block (today, the last 7 days, the period, what is
 * running) and per day. Attributed time is the entry's active seconds
 * times its share, the way the project's tracker counts it; an entry
 * belongs to the day it started on.
 */

import { isoDay } from '../../utils/dateUtils'
import { liveElapsed, type TimeEntry } from '../project/timeEntry'

export type Period = '7' | '30' | '90'

export interface ProjectTime {
  code: string
  todaySec: number
  weekSec: number
  periodSec: number
  /** Open timers you started. */
  running: TimeEntry[]
  /** The smart timer's open span, if it is counting. */
  auto: TimeEntry | null
}

export interface TimeModel {
  /** Day keys (YYYY-MM-DD), oldest first, ending today. */
  days: string[]
  /** Seconds on each day, by project. */
  perDay: Record<string, Record<string, number>>
  projects: ProjectTime[]
  todaySec: number
  weekSec: number
  periodSec: number
}

const dayKey = isoDay

const attributed = (e: TimeEntry, nowMs: number) => liveElapsed(e, nowMs) * ((e.share_pct ?? 100) / 100)

/** The block of an entry: its sprint, or '' for time outside any sprint. */
export const blockOf = (e: TimeEntry) => e.sprint_id || ''

/** The day keys of the `n` days ending today, oldest first. */
export function daysBack(nowMs: number, n: number): string[] {
  const t = new Date(nowMs)
  const out: string[] = []
  for (let i = n - 1; i >= 0; i--) out.push(dayKey(new Date(t.getFullYear(), t.getMonth(), t.getDate() - i)))
  return out
}

/** Attributed seconds on every day there is any, for the 26-week grid. */
export function dayTotals(entries: TimeEntry[], nowMs: number): Record<string, number> {
  const out: Record<string, number> = {}
  for (const e of entries) {
    const startMs = Date.parse(e.started_at ?? '')
    if (Number.isNaN(startMs)) continue
    const key = dayKey(new Date(startMs))
    out[key] = (out[key] ?? 0) + attributed(e, nowMs)
  }
  return out
}

export function build(entries: TimeEntry[], codes: string[], nowMs: number, period: Period): TimeModel {
  const days = daysBack(nowMs, Number(period))
  const inPeriod = new Set(days)
  const inWeek = new Set(days.slice(-7))
  const todayKey = days[days.length - 1]

  const by = new Map<string, ProjectTime>()
  const of = (code: string) => {
    let p = by.get(code)
    if (!p) {
      p = { code, todaySec: 0, weekSec: 0, periodSec: 0, running: [], auto: null }
      by.set(code, p)
    }
    return p
  }
  codes.forEach(of)

  const perDay: Record<string, Record<string, number>> = {}
  for (const e of entries) {
    const p = of(e.project)
    if (!e.ended_at) {
      if (e.source === 'auto') p.auto = e
      else p.running.push(e)
    }
    const startMs = Date.parse(e.started_at ?? '')
    if (Number.isNaN(startMs)) continue
    const key = dayKey(new Date(startMs))
    if (!inPeriod.has(key)) continue
    const sec = attributed(e, nowMs)
    p.periodSec += sec
    if (inWeek.has(key)) p.weekSec += sec
    if (key === todayKey) p.todaySec += sec
    ;(perDay[key] ??= {})[e.project] = (perDay[key][e.project] ?? 0) + sec
  }

  // Projects with a timer running first, then by the time in the period.
  const projects = [...by.values()].sort((a, b) =>
    (b.running.length + (b.auto ? 1 : 0)) - (a.running.length + (a.auto ? 1 : 0))
    || b.periodSec - a.periodSec || a.code.localeCompare(b.code))
  const sum = (f: (p: ProjectTime) => number) => projects.reduce((a, p) => a + f(p), 0)
  return {
    days, perDay, projects,
    todaySec: sum((p) => p.todaySec),
    weekSec: sum((p) => p.weekSec),
    periodSec: sum((p) => p.periodSec),
  }
}

/** One block (a project's sprint, or its time outside any sprint) over `days`. */
export interface BlockTime {
  project: string
  /** '' for time outside any sprint. */
  sprintId: string
  todaySec: number
  weekSec: number
  periodSec: number
  perDay: Record<string, number>
  /** The open timer you started on it, if any. */
  open: TimeEntry | null
}

export const blockKey = (project: string, sprintId: string) => `${project}\n${sprintId}`

/** Every block with time in `days` (oldest first, ending today) or a timer running. */
export function blockTimes(entries: TimeEntry[], nowMs: number, days: string[]): Map<string, BlockTime> {
  const inPeriod = new Set(days)
  const inWeek = new Set(days.slice(-7))
  const todayKey = days[days.length - 1]
  const out = new Map<string, BlockTime>()
  for (const e of entries) {
    const startMs = Date.parse(e.started_at ?? '')
    if (Number.isNaN(startMs)) continue
    const day = dayKey(new Date(startMs))
    const running = !e.ended_at && e.source !== 'auto'
    if (!inPeriod.has(day) && !running) continue
    const k = blockKey(e.project, blockOf(e))
    let b = out.get(k)
    if (!b) {
      b = { project: e.project, sprintId: blockOf(e), todaySec: 0, weekSec: 0, periodSec: 0, perDay: {}, open: null }
      out.set(k, b)
    }
    if (running) b.open = e
    if (!inPeriod.has(day)) continue
    const sec = attributed(e, nowMs)
    b.periodSec += sec
    if (inWeek.has(day)) b.weekSec += sec
    if (day === todayKey) b.todaySec += sec
    b.perDay[day] = (b.perDay[day] ?? 0) + sec
  }
  return out
}
