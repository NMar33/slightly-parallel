import { describe, expect, it } from 'vitest'

import {
  RATIO_FLOOR_MIN, YEAR_LIMIT, countsOf, dayCurve, layerValues, period, ratioOf, stepsOf, streak, usualDay, yearGrid, yearOf, yourMinutesByDay,
  type OperatorEntry, type YearSession,
} from './home-data'
import { formatYYMMDD, isoDay } from '../../utils/dateUtils'
import { dayTotals } from '../time/model'

const NOW = new Date(2026, 9, 12, 15, 0)
const day = (off: number) => formatYYMMDD(new Date(2026, 9, 12 + off))
const s = (over: Partial<YearSession>): YearSession => ({
  id: 'x', project: 'p', agent_id: 'a', created_date: day(0), start_time: '10:00', end_time: '11:00',
  agent_min: 60, turns_n: 1, l1: '', ...over,
})
const byDay = (rows: YearSession[]) => {
  const m = new Map<string, YearSession[]>()
  for (const r of rows) m.set(r.created_date, [...(m.get(r.created_date) ?? []), r])
  return m
}

describe('the home page numbers', () => {
  it('spreads a session over its span as a running total', () => {
    const c = dayCurve([s({})])
    expect(c[59]).toBe(0)                    // 09:50–10:00
    expect(c[62]).toBeCloseTo(30)            // half way through
    expect(c[143]).toBeCloseTo(60)           // the end of the day
  })

  it('a session past midnight runs to the end of the day', () => {
    expect(dayCurve([s({ start_time: '23:00', end_time: '00:30' })])[143]).toBeCloseTo(60)
  })

  it('counts the day, leaving the architecture rows out of the entries', () => {
    const c = countsOf([s({ git: { commits: 2 }, tasks: 1, produced: { decisions: 1, architecture: 9 } }), s({ agent_id: 'b' })])
    expect(c).toEqual({ minutes: 120, commits: 2, tasks: 1, entries: 1, chats: 2 })
  })

  it('a usual working day is the mean of the days with agent time before it', () => {
    const u = usualDay(byDay([s({ created_date: day(-1), agent_min: 60 }), s({ created_date: day(-2), agent_min: 120 }), s({ created_date: day(-3), agent_min: 0 })]), day(0))
    expect(u.days).toBe(2)
    expect(u.counts.minutes).toBe(90)
  })

  it('the streak counts back from today, or from yesterday while today is empty', () => {
    const days = byDay([s({ created_date: day(-1) }), s({ created_date: day(-2) }), s({ created_date: day(-4) })])
    expect(streak(days, NOW)).toBe(2)
    days.set(day(0), [s({})])
    expect(streak(days, NOW)).toBe(3)
  })

  it('compares 30 days with the 30 before', () => {
    const days = byDay([s({ created_date: day(-1), git: { commits: 4, add: 10 } }), s({ created_date: day(-40), git: { commits: 2 } })])
    expect(period(days, 30, 0, NOW)).toMatchObject({ commits: 4, added: 10, activeDays: 1 })
    expect(period(days, 30, 30, NOW)).toMatchObject({ commits: 2, activeDays: 1 })
  })

  it('the year grid starts at the first week with work, at least 26 weeks, Monday first', () => {
    const g = yearGrid(byDay([s({ created_date: day(-3) })]), NOW)
    expect(g.length).toBe(26 * 7)
    expect(g[0]!.date.getDay()).toBe(1)
    expect(g.find((c) => c.day === day(-3))!.minutes).toBe(60)
    expect(g.filter((c) => c.future).length).toBe(6)   // Tue–Sun after Monday 12 October
  })

  it('marks a year cut at the limit as truncated, and keeps working with it', () => {
    expect(yearOf(undefined)).toMatchObject({ ready: false, truncated: false })
    expect(yearOf([s({})]).truncated).toBe(false)
    const full = Array.from({ length: YEAR_LIMIT }, (_, i) => s({ id: `x${i}` }))
    const y = yearOf(full)
    expect(y.truncated).toBe(true)
    expect(y.days.get(day(0))).toHaveLength(YEAR_LIMIT)
  })

  // An entry of the operator's timer, local wall clock on NOW's day unless `dayOff` moves it.
  const iso = (d: Date) => {
    const p = (n: number) => String(n).padStart(2, '0')
    const off = -d.getTimezoneOffset()
    const sign = off >= 0 ? '+' : '-'
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}${sign}${p(Math.floor(Math.abs(off) / 60))}:${p(Math.abs(off) % 60)}`
  }
  const te = (h: number, m: number, dur: number, over: Partial<OperatorEntry> = {}, dayOff = 0): OperatorEntry => {
    const a = new Date(2026, 9, 12 + dayOff, h, m)
    return { id: `tm_${h}${m}${dur}`, project: 'p', agent_id: 'operator', source: 'auto', started_at: iso(a), ended_at: iso(new Date(a.getTime() + dur * 60_000)), duration_min: dur, share_pct: 100, ...over }
  }

  it('your time is the sum of the operator\'s timer entries per day, each at its share', () => {
    const m = yourMinutesByDay([te(10, 0, 60), te(11, 0, 30, { share_pct: 50 }), te(14, 0, 20, { source: 'manual' }), te(9, 0, 45, {}, -1)])
    expect(m.get(day(0))).toBe(95)
    expect(m.get(day(-1))).toBe(45)
    expect(yourMinutesByDay([]).size).toBe(0)
  })

  it('your time splits an entry across midnight between its two days', () => {
    const m = yourMinutesByDay([te(23, 30, 90)])
    expect(m.get(day(0))).toBeCloseTo(30)
    expect(m.get(day(1))).toBeCloseTo(60)
    // Shared and paused: the minutes follow the wall clock, the total stays active time × share.
    const p = yourMinutesByDay([te(23, 0, 60, { share_pct: 50, paused_total_sec: 3600, ended_at: iso(new Date(2026, 9, 13, 1, 0)) })])
    expect(p.get(day(0))).toBeCloseTo(15)
    expect(p.get(day(1))).toBeCloseTo(15)
  })

  it('your time ignores entries that are not the operator\'s, and empty ones', () => {
    const m = yourMinutesByDay([te(10, 0, 60, { agent_id: 'cc-1234abcd' }), te(11, 0, 0), te(12, 0, 30, { started_at: '' }), te(13, 0, 30)])
    expect(m.get(day(0))).toBe(30)
  })

  it('a running timer counts up to now, a paused one stops at its pause less the banked pauses', () => {
    const now = new Date(2026, 9, 12, 15, 0).getTime()
    const running = te(14, 0, 0, { ended_at: undefined, duration_min: 0 })
    expect(yourMinutesByDay([running], now).get(day(0))).toBeCloseTo(60)
    const paused = te(13, 0, 0, { ended_at: undefined, duration_min: 0, paused_at: iso(new Date(2026, 9, 12, 14, 0)), paused_total_sec: 600 })
    expect(yourMinutesByDay([paused], now).get(day(0))).toBeCloseTo(50)
    // A running timer from before midnight: both days get their part, up to now.
    const late = te(23, 0, 0, { ended_at: undefined, duration_min: 0 })
    const m = yourMinutesByDay([late], new Date(2026, 9, 13, 1, 0).getTime())
    expect(m.get(day(0))).toBeCloseTo(60)
    expect(m.get(day(1))).toBeCloseTo(60)
  })

  it('today\'s your time equals the Timer page\'s count of the same entries, to the second', () => {
    const at = (h: number, m: number, s: number) => new Date(2026, 9, 12, h, m, s)
    const short = (h: number, m: number, sec: number, over: Partial<OperatorEntry> = {}): OperatorEntry => {
      const a = at(h, m, 0)
      // The stored duration is rounded to the minute; the wall clock is not.
      return { ...te(h, m, 1), id: `tm_${h}_${m}_${sec}`, ended_at: iso(new Date(a.getTime() + sec * 1000)), ...over }
    }
    const now = at(16, 0, 0).getTime()
    const entries = [
      short(9, 0, 40), short(9, 5, 70), short(9, 10, 20, { share_pct: 60 }),
      // Hand-edited: 7 s of wall time, a 30-minute duration (tm_58758436). The Timer page counts the 7 s.
      short(10, 0, 7, { duration_min: 30 }),
      short(11, 0, 1800, { paused_total_sec: 300 }),
      te(15, 30, 0, { ended_at: undefined, duration_min: 0 }),
    ]
    const timerSec = dayTotals(entries, now)[isoDay(at(12, 0, 0))]!
    expect((yourMinutesByDay(entries, now).get(day(0)) ?? 0) * 60).toBeCloseTo(timerSec, 6)
    expect(timerSec).toBeCloseTo(40 + 70 + 12 + 7 + 1500 + 1800)
  })

  it('agent sessions spanning 20 h beside 2 h of timer entries: your time is 2 h', () => {
    const sessions = [
      s({ start_time: '02:00', end_time: '22:00', duration_min: 1200, agent_min: 600 }),
      s({ start_time: '03:00', end_time: '21:00', duration_min: 1080, agent_min: 300 }),
    ]
    const you = yourMinutesByDay([te(9, 0, 60), te(15, 0, 60)]).get(day(0)) ?? 0
    const v = layerValues(sessions, you)
    expect(v.you).toBe(120)
    expect(v.agent).toBe(900)
    expect(v.ratio).toBeCloseTo(900 / 120)
  })

  it('your time never exceeds the day\'s timer total, and agent sessions never add to it', () => {
    const entries = [te(8, 0, 50), te(10, 0, 70, { share_pct: 40 }), te(23, 0, 120), te(13, 0, 30, { agent_id: 'cc-x' })]
    const timerTotal = entries
      .filter((e) => e.agent_id === 'operator')
      .reduce((t, e) => t + (e.duration_min ?? 0) * (e.share_pct ?? 100) / 100, 0)
    const byDayMin = yourMinutesByDay(entries)
    expect([...byDayMin.values()].reduce((a, b) => a + b, 0)).toBeCloseTo(timerTotal)
    const you = byDayMin.get(day(0)) ?? 0
    expect(you).toBeLessThanOrEqual(timerTotal)
    for (const rows of [[], [s({ duration_min: 600 })], [s({ start_time: '00:00', duration_min: 1440, agent_min: 1440 }), s({ duration_min: 900 })]]) {
      expect(layerValues(rows, you).you).toBe(you)
    }
    expect(layerValues([s({ duration_min: 600 })]).you).toBe(0)
  })

  it('the ratio is empty below 30 minutes of your time', () => {
    expect(ratioOf(120, RATIO_FLOOR_MIN - 1)).toBe(0)
    expect(ratioOf(120, 0)).toBe(0)
    expect(ratioOf(48, RATIO_FLOOR_MIN)).toBeCloseTo(1.6)
  })

  it('a day has a value on every layer', () => {
    const v = layerValues([
      s({ start_time: '10:00', duration_min: 60, agent_min: 90, git: { add: 100 } }),
      s({ start_time: '10:30', duration_min: 60, agent_min: 54, git: { add: 20 } }),
    ], 90)
    expect(v).toEqual({ agent: 144, you: 90, ratio: 1.6, lines: 120 })
    expect(layerValues([])).toEqual({ agent: 0, you: 0, ratio: 0, lines: 0 })
  })

  it('the ratio keeps its 30-minute floor on the timer\'s time', () => {
    expect(layerValues([s({ agent_min: 300 })], RATIO_FLOOR_MIN - 1).ratio).toBe(0)
    expect(layerValues([s({ agent_min: 300 })], 60).ratio).toBe(5)
  })

  it('steps a layer by its own quantiles, empty days at 0', () => {
    const step = stepsOf([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
    expect([0, 1, 4, 6, 7, 8].map(step)).toEqual([0, 1, 2, 3, 3, 4])
    expect(stepsOf([0, 0])(0)).toBe(0)
    expect(stepsOf([0.5, 1.6])(1.6)).toBe(4)
  })
})
