/**
 * The film model — pure, no canvas, no React.
 *
 * Two things live here. The **clock**: wall time is not film time, because
 * 83% of a project's hours hold nothing at all. An hour's share of the film
 * is `base + sqrt(events)`, so silence is a short held beat instead of dead
 * air and the busiest hour gets room to be read. And the **state**: the board
 * and the river at an instant, rebuilt from the log rather than stored.
 */

import { DEFAULTS, type Options } from './options'
import type { Card, Git, Mark, Move, Session, Source, Stats } from './source'

import { t } from '../../i18n/scope/views'
export const COLUMNS = ['unclassified', 'todo', 'doing', 'review', 'done'] as const
export type Column = (typeof COLUMNS)[number]

export const COLUMN_LABEL: Record<Column, string> = {
  unclassified: 'unclassified',
  todo: t('to do'),
  doing: 'doing',
  review: 'review',
  done: 'done',
}

const HOUR = 3600_000
// An empty hour still costs a little film, or a quiet week vanishes and the
// viewer never learns it happened. Tuned so silence is ~1/5 of the running time.

export type Beat = { at: number; kind: string; text: string }

export type Hour = {
  at: number
  weight: number
  /** agent turns in this hour — the river's own line */
  work: number
  /** card movements in this hour — what the board shows for it */
  moves: number
  u0: number
  u1: number
}

export type Film = {
  project: string
  t0: number
  t1: number
  cards: Card[]
  byId: Map<string, Card>
  lanes: string[]
  laneOf: (lane: string) => number
  agents: string[]
  sessions: Session[]
  marks: Mark[]
  stats: Stats
  git: Git | null
  hours: Hour[]
  beats: Beat[]
  /** film position 0..1 → wall clock ms */
  wallAt: (u: number) => number
  /** wall clock ms → film position 0..1 */
  filmAt: (ms: number) => number
}

const ms = (iso: string) => (iso ? new Date(iso).getTime() : NaN)

/** Status a card carries at `at`, or null once it has left the board. */
export function statusAt(c: Card, at: number): Column | null {
  const born = ms(c.born)
  if (!(born <= at)) return null
  const gone = ms(c.archived_at)
  if (Number.isFinite(gone) && gone <= at) return null
  let s = c.status0
  for (const m of c.moves) {
    if (ms(m.at) > at) break
    s = m.status
  }
  if (s === 'done-archived') return 'done'
  if (s === 'parked') return null
  return (COLUMNS as readonly string[]).includes(s) ? (s as Column) : 'todo'
}

/** When the card last changed anything, at or before `at` — drives the glow. */
function movedAt(c: Card, at: number): number {
  let last = ms(c.born)
  for (const m of c.moves) {
    const tv = ms(m.at)
    if (tv > at) break
    last = tv
  }
  return last
}

function topLanes(cards: Card[], n = 7): string[] {
  const count = new Map<string, number>()
  for (const c of cards) if (c.lane) count.set(c.lane, (count.get(c.lane) ?? 0) + 1)
  return [...count.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([l]) => l)
}

function tally(stamps: number[], size: number): Map<number, number> {
  const m = new Map<number, number>()
  for (const s of stamps) {
    const b = Math.floor(s / size)
    m.set(b, (m.get(b) ?? 0) + 1)
  }
  return m
}

/**
 * The film's clock.
 *
 * Wall time gives every hour the same share, which spends four fifths of the
 * running time on nothing. Event time gives an hour a share for what happened
 * in it — but it has to be measured finer than an hour, because the work does
 * not arrive spread across one. Slightly Parallel's busiest hour holds a hundred and
 * fifty-four events, most of them inside a couple of minutes; weighted by the
 * hour, that whole burst still landed inside a single frame, so the board sat
 * still and then jumped twenty-six cards at once. That is what reads as
 * flicker, and no amount of smoothing downstream can fix a clock that hands a
 * frame a day's worth of change.
 *
 * So the weight is accumulated in ten-minute buckets, in proportion to what
 * happened. The hours the rest of the film draws with keep their positions
 * from the same accumulation, so every reading still shares one axis.
 */
const BUCKET = 10 * 60_000
/** What an empty bucket is worth, so silence is a held beat and not a cut. */
const IDLE_BUCKET = 0.02

function buildClock(
  t0: number, t1: number, moves: number[], work: number[], clock: Options['clock'],
) {
  const b0 = Math.floor(t0 / BUCKET)
  const b1 = Math.floor(t1 / BUCKET)
  const moveLoad = tally(moves, BUCKET)
  const workLoad = tally(work, BUCKET)

  // Cumulative weight at the start of each bucket, and the total.
  const acc = new Float64Array(b1 - b0 + 2)
  let total = 0
  for (let b = b0; b <= b1; b++) {
    const i = b - b0
    acc[i] = total
    const n = (moveLoad.get(b) ?? 0) + (workLoad.get(b) ?? 0)
    total += clock === 'wall' ? 1 : IDLE_BUCKET + n
  }
  acc[b1 - b0 + 1] = total
  const norm = total || 1

  const filmAt = (at: number) => {
    const i = Math.min(acc.length - 2, Math.max(0, Math.floor(at / BUCKET) - b0))
    const within = Math.min(1, Math.max(0, (at - (b0 + i) * BUCKET) / BUCKET))
    return (acc[i] + (acc[i + 1] - acc[i]) * within) / norm
  }
  const wallAt = (u: number) => {
    const x = Math.min(1, Math.max(0, u)) * norm
    let lo = 0
    let hi = acc.length - 2
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1
      if (acc[mid] <= x) lo = mid
      else hi = mid - 1
    }
    const span = acc[lo + 1] - acc[lo]
    const f = span > 0 ? (x - acc[lo]) / span : 0
    return (b0 + lo + f) * BUCKET
  }

  // The hours the rivers draw with, positioned by the same clock.
  const moveHours = tally(moves, HOUR)
  const workHours = tally(work, HOUR)
  const hours: Hour[] = []
  const h0 = Math.floor(t0 / HOUR)
  const h1 = Math.floor(t1 / HOUR)
  for (let h = h0; h <= h1; h++) {
    const at = h * HOUR
    hours.push({
      at,
      weight: filmAt(at + HOUR) - filmAt(at),
      work: workHours.get(h) ?? 0,
      moves: moveHours.get(h) ?? 0,
      u0: filmAt(at),
      u1: filmAt(at + HOUR),
    })
  }
  return { hours, wallAt, filmAt }
}

function buildBeats(src: Source, cards: Card[], hours: Hour[]): Beat[] {
  const beats: Beat[] = []

  const firstDone = cards
    .flatMap((c) => c.moves.filter((m) => m.status === 'done').map((m) => ms(m.at)))
    .sort((a, b) => a - b)[0]
  if (Number.isFinite(firstDone)) beats.push({ at: firstDone, kind: 'first', text: t('first card done') })

  const busiest = [...hours].sort((a, b) => b.weight - a.weight)[0]
  if (busiest) {
    // The hour's own count, now that weight is a share of the film.
    const n = busiest.moves + busiest.work
    beats.push({ at: busiest.at + HOUR / 2, kind: 'peak', text: t('{n} replies and card moves in one hour', { n }) })
  }

  const live = hours.filter((h) => h.moves + h.work > 0)
  for (let i = 1; i < live.length; i++) {
    const gap = (live[i].at - live[i - 1].at) / (24 * HOUR)
    if (gap >= 2.5) {
      beats.push({
        at: live[i - 1].at + HOUR,
        kind: 'quiet',
        text: t('{v} days with no replies or card moves', { v: Math.round(gap) }),
      })
    }
  }

  let longest = { days: 0, title: '', at: 0 }
  for (const c of cards) {
    for (let i = 0; i < c.moves.length; i++) {
      if (c.moves[i].status !== 'doing') continue
      const from = ms(c.moves[i].at)
      const to = i + 1 < c.moves.length ? ms(c.moves[i + 1].at) : ms(src.span.end)
      const days = (to - from) / (24 * HOUR)
      if (days > longest.days) longest = { days, title: c.title, at: to }
    }
  }
  if (longest.days >= 3) {
    beats.push({
      at: longest.at,
      kind: 'stuck',
      text: t('“{title}” was in doing for {v} days', { title: longest.title, v: longest.days.toFixed(0) }),
    })
  }

  for (const m of src.marks) {
    if (m.kind === 'evidence') beats.push({ at: ms(m.at), kind: 'evidence', text: t('an agent attached evidence') })
  }

  return beats.filter((b) => Number.isFinite(b.at)).sort((a, b) => a.at - b.at)
}

function inWindow(c: Card, t0: number, t1: number): boolean {
  return c.moves.some((m) => {
    const tv = ms(m.at)
    return tv >= t0 && tv <= t1
  }) || (ms(c.born) >= t0 && ms(c.born) <= t1)
}

export function buildFilm(src: Source, options?: Partial<Options>): Film {
  const opts = { ...DEFAULTS, ...options }
  let cards = src.cards.slice().sort((a, b) => ms(a.born) - ms(b.born))
  if (opts.lanes.length) cards = cards.filter((c) => opts.lanes.includes(c.lane))
  if (opts.sprint) cards = cards.filter((c) => c.sprint === opts.sprint)
  const moveStamps: number[] = []
  for (const c of cards) {
    moveStamps.push(ms(c.born))
    for (const m of c.moves) moveStamps.push(ms(m.at))
  }
  // A session's turns are spread over its own span, so a long session reads
  // as a long swell in the river rather than a spike at its first minute.
  const workStamps: number[] = []
  for (const s of src.sessions) {
    const a = ms(s.start)
    const b = Math.max(ms(s.end), a)
    const n = Math.max(1, s.turns_n)
    for (let i = 0; i < n; i++) workStamps.push(a + ((b - a) * i) / n)
  }

  // One stamp per turn: a long history holds more than a spread call takes
  // as arguments (Math.max(...all) throws a RangeError), so one loop.
  let first = Infinity
  let last = ms(src.span.end)
  for (const s of [moveStamps, workStamps]) {
    for (const x of s) {
      if (!Number.isFinite(x)) continue
      if (x < first) first = x
      if (x > last) last = x
    }
  }
  const t1 = last
  // A period trims the clock, never the cast: a card born before the window
  // still stands on the board, holding whatever state it had when it opened.
  const t0 = opts.days > 0 ? Math.max(first, t1 - opts.days * 24 * HOUR) : first

  if (opts.activeOnly) {
    cards = cards.filter((c) => inWindow(c, t0, t1))
    moveStamps.length = 0
    for (const c of cards) {
      moveStamps.push(ms(c.born))
      for (const m of c.moves) moveStamps.push(ms(m.at))
    }
  }

  const inside = (s: number) => s >= t0 && s <= t1
  const { hours, wallAt, filmAt } = buildClock(
    t0, t1,
    moveStamps.filter((s) => Number.isFinite(s) && inside(s)),
    workStamps.filter((s) => Number.isFinite(s) && inside(s)),
    opts.clock,
  )

  const lanes = topLanes(cards)
  const laneIndex = new Map(lanes.map((l, i) => [l, i]))

  const firstSeen = new Map<string, number>()
  for (const s of src.sessions) {
    const tv = ms(s.start)
    const seen = firstSeen.get(s.agent_id)
    if (seen === undefined || tv < seen) firstSeen.set(s.agent_id, tv)
  }
  const agents = [...firstSeen.entries()].sort((a, b) => a[1] - b[1]).map(([a]) => a)

  return {
    project: src.project,
    t0,
    t1,
    cards,
    byId: new Map(cards.map((c) => [c.id, c])),
    lanes,
    laneOf: (lane: string) => laneIndex.get(lane) ?? -1,
    agents,
    sessions: src.sessions,
    marks: src.marks,
    stats: src.stats ?? { turns: 0 },
    git: src.git?.commits?.length ? src.git : null,
    hours,
    beats: buildBeats(src, cards, hours).filter((b) => b.at >= t0 && b.at <= t1),
    wallAt,
    filmAt,
  }
}

export type Placed = { card: Card; status: Column; moved: number }

export type Frame = {
  at: number
  columns: Record<Column, Placed[]>
  counts: Record<Column, number>
  live: number
  parked: number
  awake: Session[]
  /** Agents and sessions *so far* — both grow as the film runs. */
  agentsSeen: number
  sessionsSeen: number
  turnsSeen: number
  beat: Beat | null
}

/**
 * What the board *is* at an instant, beyond its counts.
 *
 * A square frame has no room for the river and no need of it: the numbers
 * that change are more interesting than the shape of the hours. Lead time
 * and throughput are the two a board actually gets judged on, and both are
 * rolling — they answer "right now", not "over the whole run".
 */
type Vitals = {
  done: number
  doing: number
  /** Median days from a card's birth to its first landing in done. */
  leadDays: number
  /** Cards that landed in the last seven days. */
  weekly: number
  agents: number
  turns: number
  /** Cumulative done, one point per hour of the film — the sparkline. */
  curve: number[]
  /** Index in `curve` the playhead has reached; the rest is drawn as a ghost. */
  now: number
}

export function vitalsAt(film: Film, f: Frame): Vitals {
  const leads: number[] = []
  let weekly = 0
  const week = f.at - 7 * 24 * HOUR
  for (const c of film.cards) {
    const born = new Date(c.born).getTime()
    for (const m of c.moves) {
      if (m.status !== 'done') continue
      const tv = new Date(m.at).getTime()
      if (tv > f.at) break
      leads.push((tv - born) / (24 * HOUR))
      if (tv >= week) weekly++
      break
    }
  }
  leads.sort((a, b) => a - b)
  const median = leads.length ? leads[Math.floor(leads.length / 2)] : 0

  const curve: number[] = []
  let seen = 0
  const landings = film.cards
    .map((c) => c.moves.find((m) => m.status === 'done'))
    .filter(Boolean)
    .map((m) => new Date((m as Move).at).getTime())
    .sort((a, b) => a - b)
  let i = 0
  let now = 0
  film.hours.forEach((h, n) => {
    while (i < landings.length && landings[i] <= h.at + HOUR) {
      seen++
      i++
    }
    curve.push(seen)
    if (h.at <= f.at) now = n
  })

  return {
    done: f.counts.done,
    doing: f.counts.doing,
    leadDays: median,
    weekly,
    agents: f.agentsSeen,
    turns: f.turnsSeen,
    curve,
    now,
  }
}

/** The board and the river at one instant. */
export function frameAt(film: Film, at: number): Frame {
  const columns = Object.fromEntries(COLUMNS.map((c) => [c, [] as Placed[]])) as Record<Column, Placed[]>
  let parked = 0
  for (const card of film.cards) {
    const status = statusAt(card, at)
    if (status === null) {
      if (new Date(card.born).getTime() <= at) parked++
      continue
    }
    columns[status].push({ card, status, moved: movedAt(card, at) })
  }
  for (const c of COLUMNS) columns[c].sort((a, b) => a.moved - b.moved)
  const counts = Object.fromEntries(COLUMNS.map((c) => [c, columns[c].length])) as Record<Column, number>
  const live = COLUMNS.reduce((n, c) => n + counts[c], 0)

  const started = film.sessions.filter((s) => new Date(s.start).getTime() <= at)
  const agentsSeen = new Set(started.map((s) => s.agent_id)).size
  const turnsSeen = started.reduce((n, s) => n + (s.turns_n || 0), 0)

  const awake = film.sessions.filter((s) => {
    const a = new Date(s.start).getTime()
    const b = new Date(s.end).getTime()
    return a <= at && at <= Math.max(b, a + 60_000)
  })

  let beat: Beat | null = null
  for (const b of film.beats) {
    if (b.at <= at && at - b.at < 6 * HOUR) beat = b
  }

  return {
    at, columns, counts, live, parked, awake,
    agentsSeen, sessionsSeen: started.length, turnsSeen, beat,
  }
}

/** A wall-clock moment as the studio's readout writes it, in local time
 *  like the film's own clock: `2026-10-05 09:30`. */
export function wallStamp(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
