import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { READING_MS } from '../../../time/beats'

vi.mock('../../../../lib/getJson', () => ({ postJson: vi.fn(() => Promise.resolve({})), getJson: vi.fn(() => Promise.resolve({})) }))
vi.mock('../../../../lib/uiPrefs', () => ({
  persistPref: vi.fn((k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* fine */ } }),
}))

import { postJson } from '../../../../lib/getJson'
import { persistPref } from '../../../../lib/uiPrefs'
import {
  DAY_KEY, HEALTH_DEFAULT, SETTINGS_KEY, adoptServerBreak, breakNow, cleanSettings, didIt, dueOf, finishBreak, flushDay, freshDay,
  getHealth, later, laterDay, readDay, resetHealthStore, setHealthSettings, startBreak, step, tick, zoneOf, type Day,
} from './healthModel'

const MIN = 60_000
const S = HEALTH_DEFAULT
const T0 = new Date(2026, 10, 18, 9, 0, 0).getTime()
let clockNow = T0

/** `min` minutes of steady work from `from`: input every 20 s, a step after each. */
function workFor(d: Day, from: number, min: number): Day {
  let x = d
  for (let t = from; t <= from + min * MIN; t += 20_000) x = step(x, t, t, S)
  return x
}

describe('the counter from activity', () => {
  it('counts steady input minute for minute', () => {
    const d = workFor(freshDay(T0), T0, 30)
    expect(d.run).toBeCloseTo(30, 5)
    expect(d.wk).toBeCloseTo(30, 5)
  })

  it('counts two minutes of reading after the last input, then stands still', () => {
    let d = workFor(freshDay(T0), T0, 10)
    const last = d.input
    d = step(d, last + 6 * MIN, 0, S)
    expect(d.run).toBeCloseTo(10 + READING_MS / MIN, 5)
  })

  it('a gap shorter than the reset only stands the counter still', () => {
    let d = workFor(freshDay(T0), T0, 20)
    const back = d.input + 8 * MIN
    d = step(d, back, back, S)
    d = workFor(d, back, 10)
    expect(d.run).toBeCloseTo(20 + 2 + 10, 5)
    expect(d.breaks).toEqual([])
  })

  it('a gap of `reset` minutes sets it to zero and is kept as a break', () => {
    let d = workFor(freshDay(T0), T0, 40)
    const left = d.input
    d = step(d, left + 11 * MIN, 0, S)
    expect(d.run).toBe(0)                       // shows zero while still away
    const back = left + 25 * MIN
    d = workFor(d, back, 5)
    expect(d.run).toBeCloseTo(5, 5)
    expect(d.breaks).toHaveLength(1)
    expect(d.breaks[0]).toMatchObject({ at: left, len: 25, reset: true, idle: true })
    expect(d.wk).toBeCloseTo(40 + 2 + 5, 5)
  })

  it('the computer\'s input elsewhere (an older moment) never moves the input back', () => {
    let d = workFor(freshDay(T0), T0, 5)
    const input = d.input
    d = step(d, input + 1000, input - 30_000, S)
    expect(d.input).toBe(input)
  })

  it('the first input of the day is not a break', () => {
    const d = step(freshDay(T0), T0 + 3 * 3600_000, T0 + 3 * 3600_000, S)
    expect(d.breaks).toEqual([])
  })
})

describe('zones and thresholds', () => {
  it('green, yellow from 90, red from 150; minutes in each zone counted exactly', () => {
    expect([zoneOf(89.9, S), zoneOf(90, S), zoneOf(150, S)]).toEqual(['green', 'yellow', 'red'])
    const d = workFor(freshDay(T0), T0, 160)
    expect(d.inYellow).toBeCloseTo(60, 5)
    expect(d.inRed).toBeCloseTo(10, 5)
  })

  it('a new zone asks at once with its first action', () => {
    const d = workFor(freshDay(T0), T0, 91)
    const now = d.at
    const due = dueOf({ ...d, rem: { r1: { next: 999, count: 0, paused: false }, r2: { next: 999, count: 0, paused: false } } }, S, now)
    expect(due).toMatchObject({ kind: 'yellow', act: 'stretch' })
  })
})

describe('reminders', () => {
  const only = (id: string) => ({ ...S, acts: { yellow: [], red: [] }, reminders: S.reminders.filter((r) => r.id === id) })

  it('water every 45 work minutes, three times, then a pause of 3 h', () => {
    const s = only('r1')
    let d = freshDay(T0)
    const at = (wk: number) => ({ ...d, wk })
    expect(dueOf(at(44), s, T0)).toBeNull()
    expect(dueOf(at(45), s, T0)).toMatchObject({ kind: 'remind', act: 'water', n: 1 })
    const seen: number[] = []
    for (let wk = 0; wk <= 45 * 3 + 180 + 1; wk += 1) {
      d = at(wk)
      const due = dueOf(d, s, T0)
      if (due?.kind === 'remind') {
        seen.push(wk)
        // answer it through the pure path
        const r = s.reminders[0]!
        const st = d.rem.r1 ?? { next: r.every, count: 0, paused: false }
        const count = st.count + 1
        d = { ...d, rem: { r1: count >= r.times ? { next: wk + r.pause, count: 0, paused: true } : { next: wk + r.every, count, paused: false } } }
      }
    }
    expect(seen).toEqual([45, 90, 135, 315])
  })

  it('stretch every 60, twice, then 2 h — through «Сделал» in the store', () => {
    localStorage.clear()
    resetHealthStore(() => clockNow)
    setHealthSettings(only('r2'))
    const times: number[] = []
    for (let m = 0; m < 60 * 2 + 120 + 5; m += 1) {
      const now = T0 + m * MIN
      clockNow = now
      tick(now)
      const h = getHealth()
      if (dueOf(h.d, h.s, now)?.kind === 'remind') { times.push(Math.round(h.d.wk)); didIt() }
    }
    expect(times).toEqual([60, 120, 240])
  })

  it('«Позже» moves the zone and every reminder 15 minutes on', () => {
    const d = { ...freshDay(T0), wk: 50 }
    const x = laterDay(d, S, T0)
    expect(x.nextAt).toBe(T0 + 15 * MIN)
    expect(x.rem.r1!.next).toBe(65)
    expect(x.rem.r2!.next).toBe(75)
  })

  it('a break pauses them: work minutes stand still on a break', () => {
    let d = workFor(freshDay(T0), T0, 40)
    d = { ...d, away: d.at }
    const wk = d.wk
    d = step(d, d.at + 30 * MIN, d.at + 30 * MIN, S)
    expect(d.wk).toBe(wk)
    expect(dueOf(d, S, d.at)).toBeNull()
  })
})


describe('the break and the server', () => {
  beforeEach(() => {
    localStorage.clear()
    clockNow = T0
    resetHealthStore(() => clockNow)
    vi.mocked(postJson).mockClear()
  })

  it('«Перерыв» pauses the counter and the project time; «Готово» zeroes it and resumes', () => {
    for (let m = 0; m <= 30; m += 1) { clockNow = T0 + m * MIN; tick(clockNow) }
    expect(getHealth().d.run).toBeCloseTo(30, 5)
    startBreak()
    expect(postJson).toHaveBeenLastCalledWith('/api/time/auto/break', { on: true })
    for (let m = 31; m <= 45; m += 1) { clockNow = T0 + m * MIN; tick(clockNow) }
    expect(getHealth().d.run).toBeCloseTo(30, 5)
    expect(getHealth().d.wk).toBeCloseTo(30, 5)
    finishBreak('  чай ')
    expect(postJson).toHaveBeenLastCalledWith('/api/time/auto/break', { on: false, note: 'чай' })
    const d = getHealth().d
    expect(d.away).toBeNull()
    expect(d.run).toBe(0)
    expect(d.breaks.at(-1)).toMatchObject({ len: 15, note: 'чай', reset: true })
  })

  it('a break twice sends once; «Перерыв» on a reminder answers it', () => {
    setHealthSettings({ ...S, reminders: [S.reminders[0]!] })
    for (let m = 0; m <= 45; m += 1) { clockNow = T0 + m * MIN; tick(clockNow) }
    expect(dueOf(getHealth().d, getHealth().s, clockNow)?.kind).toBe('remind')
    breakNow()
    startBreak()
    expect(vi.mocked(postJson).mock.calls.filter((c) => c[0] === '/api/time/auto/break')).toHaveLength(1)
    expect(getHealth().d.rem.r1).toMatchObject({ count: 1 })
  })

  it('a break the server holds is adopted; one it ended ends here', () => {
    adoptServerBreak(true, T0 - 5 * MIN)
    expect(getHealth().d.away).toBe(T0 - 5 * MIN)
    adoptServerBreak(false, null)
    expect(getHealth().d.away).toBeNull()
    expect(postJson).not.toHaveBeenCalled()
  })

  it('«Позже» through the store keeps the suggestion away for 15 minutes', () => {
    for (let m = 0; m <= 91; m += 1) { clockNow = T0 + m * MIN; tick(clockNow) }
    setHealthSettings({ ...S, reminders: [] })
    expect(dueOf(getHealth().d, getHealth().s, clockNow)?.kind).toBe('yellow')
    later()
    expect(dueOf(getHealth().d, getHealth().s, clockNow + 14 * MIN)).toBeNull()
    expect(dueOf(getHealth().d, getHealth().s, clockNow + 15 * MIN)?.kind).toBe('yellow')
  })
})

describe('settings', () => {
  beforeEach(() => { localStorage.clear(); resetHealthStore(() => T0) })
  afterEach(() => vi.mocked(persistPref).mockClear())

  it('persist through persistPref under sp-term-health', () => {
    setHealthSettings({ yellow: 60 })
    expect(persistPref).toHaveBeenCalledWith(SETTINGS_KEY, expect.stringContaining('"yellow":60'))
    resetHealthStore(() => T0)
    expect(getHealth().s.yellow).toBe(60)
  })

  it('off: nothing counts and nothing is due', () => {
    setHealthSettings({ on: false })
    tick(T0)
    for (let m = 0; m < 100; m += 1) tick(T0 + m * MIN)
    expect(getHealth().d.run).toBe(0)
    expect(dueOf({ ...getHealth().d, run: 200, wk: 200 }, getHealth().s, T0)).toBeNull()
  })

  it('a damaged or partial value falls back field by field', () => {
    localStorage.setItem(SETTINGS_KEY, '{not json')
    resetHealthStore(() => T0)
    expect(getHealth().s).toEqual(HEALTH_DEFAULT)
    expect(cleanSettings({ yellow: 100, red: 50, reset: 'x', reminders: [{ id: 'a', act: 'nope' }] })).toMatchObject({ yellow: 100, red: 101, reset: 10, reminders: [], on: true })
    expect(cleanSettings({ on: false }).on).toBe(false)
    expect(cleanSettings(null)).toEqual(HEALTH_DEFAULT)
  })
})

describe('today survives a reload', () => {
  beforeEach(() => { localStorage.clear() })

  it('the day is kept under its date and read back; a new date starts the counts again', () => {
    let now = T0
    resetHealthStore(() => now)
    for (let m = 0; m <= 100; m += 1) { now = T0 + m * MIN; tick(now) }
    startBreak()
    now += 12 * MIN
    finishBreak('обед')
    flushDay()
    const kept = JSON.parse(localStorage.getItem(DAY_KEY)!) as Day
    expect(kept.inYellow).toBeCloseTo(10, 5)
    resetHealthStore(() => now)
    const d = getHealth().d
    expect(d.inYellow).toBeCloseTo(10, 5)
    expect(d.breaks.map((b) => b.note)).toEqual(['обед'])
    const tomorrow = readDay(T0 + 24 * 3600_000)
    expect(tomorrow.inYellow).toBe(0)
    expect(tomorrow.breaks).toEqual([])
  })

  it('a damaged day reads as a fresh one', () => {
    localStorage.setItem(DAY_KEY, '[]')
    expect(readDay(T0)).toEqual(freshDay(T0))
  })
})
