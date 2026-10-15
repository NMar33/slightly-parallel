/**
 * The film model, without a canvas.
 *
 * Scope decides who is in the film and how wide the clock runs; the clock
 * decides how the running time is spent. Both are pure, so both are testable
 * without rendering a pixel.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildFilm, frameAt, statusAt, vitalsAt, wallStamp } from './film'
import { DEFAULTS, readOptions, writeOptions, frameCount } from './options'
import type { Card, Source } from './source'

const day = 24 * 3600_000
const T0 = Date.parse('2026-08-01T09:00:00')
const at = (d: number, h = 0) => new Date(T0 + d * day + h * 3600_000).toISOString().slice(0, 19)

function card(over: Partial<Card> = {}): Card {
  return {
    id: 'tk_1', title: 'A card', lane: 'Board', assignee: '', tags: '', sprint: '',
    born: at(0), status0: 'unclassified', moves: [], archived_at: '', evidence: false,
    ...over,
  }
}

const src: Source = {
  project: 'ALPHA',
  span: { start: at(0), end: at(20) },
  cards: [
    card({ id: 'tk_old', born: at(0), moves: [{ at: at(1), status: 'done' }] }),
    card({ id: 'tk_late', born: at(18), lane: 'Other', moves: [{ at: at(19), status: 'doing' }] }),
    card({ id: 'tk_quiet', born: at(2), moves: [] }),
  ],
  sessions: [{ id: 's1', agent_id: 'cc-a', start: at(1), end: at(1, 2), turns_n: 4, l1: '' }],
  marks: [],
  stats: { turns: 4 },
}

describe('the board replays', () => {
  it('holds the status a card was born with until its first move', () => {
    const c = src.cards[0]
    expect(statusAt(c, Date.parse(at(0, 1)))).toBe('unclassified')
    expect(statusAt(c, Date.parse(at(1, 1)))).toBe('done')
    expect(statusAt(c, Date.parse(at(0)) - 1)).toBeNull()
  })

  it('counts agents and sessions as they arrive, not as finals', () => {
    const film = buildFilm(src)
    expect(frameAt(film, Date.parse(at(0, 1))).agentsSeen).toBe(0)
    expect(frameAt(film, Date.parse(at(2))).agentsSeen).toBe(1)
    expect(frameAt(film, Date.parse(at(2))).turnsSeen).toBe(4)
  })
})

describe('scope', () => {
  it('a period trims the clock but never the cast', () => {
    const whole = buildFilm(src)
    const recent = buildFilm(src, { days: 3 })
    expect(Math.round((whole.t1 - whole.t0) / day)).toBeGreaterThan(3)
    expect(Math.round((recent.t1 - recent.t0) / day)).toBe(3)
    // The card born on day 0 still stands on the board of a 3-day film.
    expect(recent.cards.map((c) => c.id)).toContain('tk_old')
  })

  it('“only what moved” drops the silent ones', () => {
    const film = buildFilm(src, { days: 3, activeOnly: true })
    expect(film.cards.map((c) => c.id)).toEqual(['tk_late'])
  })

  it('a lane filter keeps only that lane', () => {
    expect(buildFilm(src, { lanes: ['Other'] }).cards.map((c) => c.id)).toEqual(['tk_late'])
  })
})

describe('the clock', () => {
  it('event time gives a busy hour more film than an empty one', () => {
    const film = buildFilm(src)
    const busy = film.hours.filter((h) => h.moves + h.work > 0)
    const idle = film.hours.filter((h) => h.moves + h.work === 0)
    expect(busy[0].weight).toBeGreaterThan(idle[0].weight * 2)
  })

  it('wall time gives every hour the same', () => {
    const film = buildFilm(src, { clock: 'wall' })
    // The clock accumulates in ten-minute buckets now, so an hour's weight is
    // a sum of six of them and lands within rounding of every other hour. The
    // last hour is partial, hence dropping it.
    const weights = film.hours.slice(0, -1).map((h) => h.weight)
    const first = weights[0]
    for (const w of weights) expect(Math.abs(w - first)).toBeLessThan(1e-9)
  })
})

describe('options travel in the url', () => {
  it('writes only what differs from the defaults, and reads it back', () => {
    const o = { ...DEFAULTS, days: 7, seconds: 15, clock: 'wall' as const, lanes: ['Board'] }
    const p = writeOptions(o, new URLSearchParams('project=ALPHA'))
    expect(p.get('project')).toBe('ALPHA')
    expect(p.get('days')).toBe('7')
    expect(p.has('fps')).toBe(false)
    expect(readOptions(p)).toEqual(o)
  })

  it('counts frames', () => {
    expect(frameCount({ ...DEFAULTS, seconds: 15, fps: 10 })).toBe(150)
  })
})

describe('vitals — what a square shows instead of the river', () => {
  it('rolls with the playhead rather than summing the whole run', () => {
    const film = buildFilm(src)
    const early = vitalsAt(film, frameAt(film, Date.parse(at(0, 12))))
    const late = vitalsAt(film, frameAt(film, Date.parse(at(19))))
    expect(early.done).toBe(0)
    expect(early.leadDays).toBe(0)
    expect(late.done).toBe(1)
    // tk_old was born on day 0 and landed on day 1.
    expect(late.leadDays).toBeCloseTo(1, 1)
    // …which is well outside a seven-day window by day 19.
    expect(late.weekly).toBe(0)
  })

  it('carries a curve that only ever climbs, and knows where "now" is', () => {
    const film = buildFilm(src)
    const v = vitalsAt(film, frameAt(film, Date.parse(at(10))))
    expect(v.curve.length).toBe(film.hours.length)
    for (let i = 1; i < v.curve.length; i++) expect(v.curve[i]).toBeGreaterThanOrEqual(v.curve[i - 1])
    expect(v.now).toBeGreaterThan(0)
    expect(v.now).toBeLessThan(v.curve.length)
  })
})

describe('wallStamp', () => {
  afterEach(() => vi.unstubAllEnvs())
  it('reads the wall clock in local time, as the film does', () => {
    vi.stubEnv('TZ', 'Australia/Sydney')
    // 22:30 UTC on 4 Oct is 09:30 on 5 Oct in Sydney (UTC+11 in summer time).
    expect(wallStamp(Date.UTC(2026, 9, 4, 22, 30))).toBe('2026-10-05 09:30')
  })
})

describe('a long history', () => {
  it('builds a film from more turns than a spread call takes as arguments', () => {
    const big: Source = { ...src, sessions: [{ id: 's1', agent_id: 'cc-a', start: at(1), end: at(19), turns_n: 300_000, l1: '' }] }
    expect(() => buildFilm(big)).not.toThrow()
    const film = buildFilm(big)
    expect(film.t1).toBe(Date.parse(at(20)))
  })
})
