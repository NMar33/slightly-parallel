import { describe, expect, it } from 'vitest'

import {
  RATIO_FLOOR_MIN, YEAR_LIMIT, countsOf, dayCurve, layerValues, period, ratioOf, stepsOf, streak, usualDay, yearGrid, yearOf, yourMinutes,
  type YearSession,
} from './home-data'
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

  it('your time merges overlapping and nested sessions so parallel chats count once', () => {
    expect(yourMinutes([s({ start_time: '10:00', duration_min: 60 }), s({ start_time: '10:30', duration_min: 60 })])).toBe(90)
    expect(yourMinutes([s({ start_time: '10:00', duration_min: 120 }), s({ start_time: '10:30', duration_min: 15 })])).toBe(120)
    expect(yourMinutes([s({ start_time: '14:00', duration_min: 30 }), s({ start_time: '10:00', duration_min: 30 })])).toBe(60)
    expect(yourMinutes([s({ start_time: '10:00', duration_min: 30 }), s({ start_time: '10:30', duration_min: 30 })])).toBe(60)
  })

  it('your time stops at midnight, skips empty sessions and is 0 for an empty day', () => {
    expect(yourMinutes([s({ start_time: '23:30', duration_min: 90 })])).toBe(30)
    expect(yourMinutes([s({ start_time: '10:00', duration_min: 0 }), s({ start_time: '11:00' })])).toBe(0)
    expect(yourMinutes([])).toBe(0)
  })

  it('your time is capped at a whole day', () => {
    expect(yourMinutes([s({ start_time: '00:00', duration_min: 2000 }), s({ start_time: '12:00', duration_min: 600 })])).toBe(1440)
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
    ])
    expect(v).toEqual({ agent: 144, you: 90, ratio: 1.6, lines: 120 })
    expect(layerValues([])).toEqual({ agent: 0, you: 0, ratio: 0, lines: 0 })
  })

  it('a session past midnight counts the same share of agent and your time in the ratio', () => {
    const v = layerValues([s({ start_time: '23:00', duration_min: 180, agent_min: 170 })])
    expect(v.you).toBe(60)
    expect(v.agent).toBe(170)
    expect(v.ratio).not.toBeCloseTo(2.8)
    expect(v.ratio).toBeCloseTo(170 / 180)
  })

  it('steps a layer by its own quantiles, empty days at 0', () => {
    const step = stepsOf([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
    expect([0, 1, 4, 6, 7, 8].map(step)).toEqual([0, 1, 2, 3, 3, 4])
    expect(stepsOf([0, 0])(0)).toBe(0)
    expect(stepsOf([0.5, 1.6])(1.6)).toBe(4)
  })
})
