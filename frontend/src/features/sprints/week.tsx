import { useMemo } from 'react'

import { isoDay } from '../../utils/dateUtils'

import type { Block, DeckTask } from './deck'
import type { Day } from './bands'

import { locale } from '../../i18n/scope/views'
/**
 * What every week page shares: the calendar arithmetic, the version switch
 * while four of them are on trial, and the small readings each one draws
 * from the same per-day series.
 */

const DAY_MS = 86400e3

/** The local day of a moment, YYYY-MM-DD — the key the series is read by.
 *  Not toISOString: that is the UTC day, a day early east of Greenwich. */
export const isoOf = (ms: number): string => isoDay(new Date(ms))

/** A Slightly Parallel short date (2608-27) or an ISO one, as milliseconds; a bare
 *  day is its local midnight, as the window's days are. */
function dateMs(s: string | null | undefined): number {
  const raw = String(s || '')
  if (!raw) return NaN
  const iso = raw.length === 7 ? `20${raw.slice(0, 2)}-${raw.slice(2, 4)}-${raw.slice(5, 7)}` : raw
  return Date.parse(iso.length === 10 ? `${iso}T00:00:00` : iso)
}

/** The days the window shows, as local midnights: counted on the calendar,
 *  not in 24-hour steps, which slip an hour across a clock change. */
export function windowDays(today: string, range: number): number[] {
  const [y, m, d] = today.split('-').map(Number)
  return Array.from({ length: range }, (_, i) => new Date(y!, m! - 1, d! - (range - 1) + i).getTime())
}

/** The window a page is showing, aligned to whole days. */
export function useWindow(today: string, range: 7 | 30) {
  return useMemo(() => {
    // A week reads back six days; a month, twenty-nine — today always last.
    const days = windowDays(today, range)
    return { from: days[0]!, end: days[days.length - 1]!, days, iso: days.map(isoOf) }
  }, [today, range])
}

export const weekdayShort = (ms: number) => new Date(ms).toLocaleDateString(locale(), { weekday: 'short' })
export const isWeekendMs = (ms: number) => [0, 6].includes(new Date(ms).getDay())

/** A block's bet as a span, clamped to nothing when it has no start. */
export function betSpan(b: Block): { start: number; end: number } | null {
  const start = dateMs(b.started_date)
  if (Number.isNaN(start)) return null
  return { start, end: start + (Number(b.bet_days) || 0) * DAY_MS }
}

export function seriesMap(b: Block): Record<string, Day> {
  const out: Record<string, Day> = {}
  for (const d of b.series ?? []) out[d.date] = d
  return out
}

/**
 * Statistics a week page can state without lying: all from the series, and
 * all clamped to the block's own life. A block cannot be idle on a day it
 * did not exist — counting the window instead of the life turned three days
 * of neglect into twenty-nine days of "prehistory".
 */
export function readings(b: Block, days: Day[]) {
  const startMs = dateMs(b.started_date)
  const alive = Number.isNaN(startMs)
    ? days
    : days.filter((d) => Date.parse(`${d.date}T00:00:00`) >= startMs)
  const worked = alive.filter((d) => d.human_min + d.agent_min + d.events > 0)
  const landed = alive.reduce((a, d) => a + d.done, 0)
  const minutes = alive.reduce((a, d) => a + d.human_min + d.agent_min, 0)
  const human = alive.reduce((a, d) => a + d.human_min, 0)
  const agent = alive.reduce((a, d) => a + d.agent_min, 0)
  const open = b.tasks_total - b.tasks_done
  const rate = worked.length ? landed / worked.length : 0
  return {
    /** Days of the range the block was actually alive for. */
    span: alive.length,
    worked: worked.length,
    silent: alive.length - worked.length,
    landed,
    minutes,
    human,
    agent,
    perDay: worked.length ? minutes / worked.length : 0,
    rate,
    daysToEmpty: rate > 0 ? Math.ceil(open / rate) : null,
    costPerLanding: landed > 0 ? minutes / landed : null,
    fleetShare: minutes > 0 ? agent / minutes : 0,
    busiest: days.reduce<Day | null>((a, d) => (!a || d.human_min + d.agent_min > a.human_min + a.agent_min ? d : a), null),
  }
}

/* ---------------------------------------------------------------------------
 * Lead time — the reading a cumulative flow is actually for.
 * ------------------------------------------------------------------------- */

const dayDiff = (a: string, b: string): number | null => {
  const x = Date.parse(`${a}T00:00:00`), y = Date.parse(`${b}T00:00:00`)
  return Number.isNaN(x) || Number.isNaN(y) ? null : Math.round((y - x) / DAY_MS)
}

/**
 * How long work takes to cross the block, and what has not crossed yet. The
 * horizontal distance in a cumulative flow: joined → landed.
 */
export function leadTime(b: Block, today: string) {
  const landed: number[] = []
  for (const t of b.tasks) {
    if (!t.joined || !t.done_on) continue
    const d = dayDiff(t.joined, t.done_on)
    if (d != null && d >= 0) landed.push(d)
  }
  landed.sort((x, y) => x - y)
  const median = landed.length ? landed[Math.floor(landed.length / 2)]! : null
  const inFlight = b.tasks
    .filter((t) => !t.done_on && t.joined)
    .map((t) => ({ task: t, age: dayDiff(t.joined!, today) ?? 0 }))
    .sort((x, y) => y.age - x.age)
  return {
    median,
    samples: landed.length,
    slowest: landed.length ? landed[landed.length - 1]! : null,
    inFlight,
    oldest: inFlight[0] ?? null,
  }
}

/** Days a task has sat in its current column — the stuck number. */
export function stuckDays(t: DeckTask, today: string): number | null {
  const since = String(t.status_since || t.joined || '')
  if (!since) return null
  return dayDiff(since.slice(0, 10), today)
}

/**
 * The readings that compare effort to outcome. Two cautions live in the
 * numbers themselves: agent minutes are whole sessions that mentioned the
 * block's tasks, so leverage errs generous; and a block with nothing landed
 * has no cost per landing rather than a cost of zero.
 */
export function effectivity(b: Block, days: Day[]) {
  const startMs = dateMs(b.started_date)
  const alive = Number.isNaN(startMs)
    ? days
    : days.filter((d) => Date.parse(`${d.date}T00:00:00`) >= startMs)
  const sum = (xs: Day[], f: (d: Day) => number) => xs.reduce((a, d) => a + f(d), 0)
  const human = sum(alive, (d) => d.human_min)
  const agent = sum(alive, (d) => d.agent_min)
  const landed = sum(alive, (d) => d.done)
  const worked = alive.filter((d) => d.human_min + d.agent_min + d.events > 0).length

  // Leverage over the two halves of the block's life: is the fleet taking
  // more of the load than it was, or less?
  const half = Math.floor(alive.length / 2)
  const lev = (xs: Day[]) => {
    const h = sum(xs, (d) => d.human_min)
    return h > 0 ? sum(xs, (d) => d.agent_min) / h : null
  }
  const early = lev(alive.slice(0, half))
  const late = lev(alive.slice(half))

  return {
    human,
    agent,
    /** Fleet minutes per minute of yours — the leverage. */
    leverage: human > 0 ? agent / human : null,
    trend: early != null && late != null ? late - early : null,
    /** What a landing cost you alone, and what it cost in all attention. */
    yoursPerLanding: landed > 0 ? human / landed : null,
    totalPerLanding: landed > 0 ? (human + agent) / landed : null,
    /** Landings per hour of your time — the same fact, read forwards. */
    landedPerHour: human > 0 ? landed / (human / 60) : null,
    landed,
    /** How many of its living days the block was touched at all. */
    rhythm: alive.length > 0 ? worked / alive.length : 0,
    worked,
    span: alive.length,
  }
}

/* ---------------------------------------------------------------------------
 * The numbers — flow statistics, medians rather than averages.
 * ------------------------------------------------------------------------- */

const median = (xs: number[]): number | null => {
  if (xs.length === 0) return null
  const s = [...xs].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2
}
const percentile = (xs: number[], p: number): number | null => {
  if (xs.length === 0) return null
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.min(s.length - 1, Math.floor(p * s.length))]!
}
const longestRun = (flags: boolean[], want: boolean): number => {
  let best = 0, run = 0
  for (const f of flags) {
    run = f === want ? run + 1 : 0
    if (run > best) best = run
  }
  return best
}

/**
 * Flow statistics over the block's own life. Medians, because a fortnight of
 * this work is three loud days and eleven quiet ones — a mean would describe
 * a week nobody had. Every rate counts the quiet days too: that is the point
 * of asking for a typical day rather than a busy one.
 */
export function numbers(b: Block, days: Day[]) {
  const startMs = dateMs(b.started_date)
  const alive = Number.isNaN(startMs)
    ? days
    : days.filter((d) => Date.parse(`${d.date}T00:00:00`) >= startMs)
  const isoSet = new Set(alive.map((d) => d.date))

  // Tasks that joined the block, bucketed by the day they arrived.
  const arrivals: Record<string, number> = {}
  for (const t of b.tasks) {
    const j = String(t.joined || '').slice(0, 10)
    if (j && isoSet.has(j)) arrivals[j] = (arrivals[j] ?? 0) + 1
  }
  const newPerDay = alive.map((d) => arrivals[d.date] ?? 0)
  const donePerDay = alive.map((d) => d.done)
  const netPerDay = alive.map((d, i) => newPerDay[i]! - d.done)
  const wipPerDay = alive.map((d) => (d.bands?.doing ?? 0) + (d.bands?.review ?? 0))
  const effortPerDay = alive.map((d) => d.human_min + d.agent_min)
  const workedFlags = alive.map((d) => d.human_min + d.agent_min + d.events > 0)

  const leadDays: number[] = []
  for (const t of b.tasks) {
    if (!t.joined || !t.done_on) continue
    const a = Date.parse(`${String(t.joined).slice(0, 10)}T00:00:00`)
    const z = Date.parse(`${String(t.done_on).slice(0, 10)}T00:00:00`)
    if (!Number.isNaN(a) && !Number.isNaN(z) && z >= a) leadDays.push(Math.round((z - a) / DAY_MS))
  }

  const weekend = alive.filter((d) => isWeekendMs(Date.parse(`${d.date}T00:00:00`)))
  const weekendMin = weekend.reduce((a, d) => a + d.human_min, 0)
  const allMin = alive.reduce((a, d) => a + d.human_min, 0)

  return {
    span: alive.length,
    newMedian: median(newPerDay), newMax: Math.max(0, ...newPerDay), newTotal: newPerDay.reduce((a, n) => a + n, 0),
    doneMedian: median(donePerDay), doneMax: Math.max(0, ...donePerDay), doneTotal: donePerDay.reduce((a, n) => a + n, 0),
    netMedian: median(netPerDay),
    wipMedian: median(wipPerDay), wipMax: Math.max(0, ...wipPerDay),
    effortMedian: median(effortPerDay), effortWorkedMedian: median(effortPerDay.filter((m) => m > 0)),
    leadMedian: median(leadDays), leadP90: percentile(leadDays, 0.9), leadSamples: leadDays.length,
    streak: longestRun(workedFlags, true),
    silence: longestRun(workedFlags, false),
    weekendShare: allMin > 0 ? weekendMin / allMin : null,
  }
}
