import { describe, expect, it } from 'vitest'

import { YEAR_LIMIT, countsOf, dayCurve, period, streak, usualDay, yearGrid, yearOf, type YearSession } from './home-data'
import { formatYYMMDD } from '../../utils/dateUtils'

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
})
