/**
 * What runs under the board.
 *
 * Six readings of the same twenty days, each answering a different question,
 * all drawn into the same rectangle by the same rule: everything before the
 * playhead is lit, everything after it is a ghost. That is the film's one
 * grammar, and it is what lets a viewer compare two variants at a glance.
 *
 * Every river is a pure function of (film, frame, rect, position). No state,
 * no simulation stepping per frame — a layout that needs solving is solved
 * once, deterministically, before the first frame is drawn.
 */

import type { Film, Frame } from './film'
import type { GraphNode } from './source'
import type { Theme } from './theme'
import { mix } from './theme'
import { bezel, dial, flow, lamps, log, meter, readings, readout, strip, trace } from './cockpit'

import { locale, t } from '../../i18n/scope/views'
import { monthShort } from '../../lib/months'
export type RiverId =
  | 'pulse' | 'output' | 'areas' | 'growth' | 'lanes' | 'days' | 'graph'
  | 'cockpit' | 'console' | 'telemetry'

type River = {
  id: RiverId
  name: string
  /** One line in the picker. */
  note: string
  /** What a reader is looking at, for the caption under the film. */
  caption: string
  needsGit?: boolean
}

/**
 * Captions are written for someone who has never seen the picture before.
 *
 * They say where each thing is on the screen, what one mark stands for, and
 * what the colours mean — in that order, in the words a reader would use.
 * Not what the reading is "about".
 */
export const RIVERS: River[] = [
  {
    id: 'pulse',
    name: 'Pulse',
    note: t('agent replies above the line, card moves below'),
    caption:
      t('Top: the kanban board. Each card sits in the column it was in at that moment; the newest few show their titles, the rest are blocks coloured by lane. Bottom: two counts per hour. Above the line, how many times an agent replied. Below it, how many times a card changed column.'),
  },
  {
    id: 'output',
    name: 'Effort & output',
    note: t('agent replies above, lines of code below'),
    needsGit: true,
    caption:
      t('Top: the kanban board, one block per card in the column it was in then. Bottom: agent replies per hour above the line; lines of code added and deleted per hour below it, with a tick on the centre line for each commit.'),
  },
  {
    id: 'areas',
    name: t('Where the work went'),
    note: t('lines changed per hour, stacked by area: frontend, backend, tests, docs'),
    needsGit: true,
    caption:
      t('Top: the kanban board. Bottom: the lines of code changed each hour, stacked by the part of the repository they are in: frontend, backend, tests, docs and tooling, each in its own colour and named in the key below. The height is the total changed that hour.'),
  },
  {
    id: 'growth',
    name: 'Growth',
    note: t('lines of code in the project, commit by commit'),
    needsGit: true,
    caption:
      t('Top: the kanban board. Bottom: the lines of code in the project, all lines added minus all lines deleted, from the first commit to the last. Each tick on the curve is one commit. The filled part is the past; the dim part is still to come.'),
  },
  {
    id: 'lanes',
    name: t('Agent lanes'),
    note: t('one lane per agent, lit while the agent is working'),
    caption:
      t('Top: the kanban board. Bottom: one row per agent, in the order they first appeared. Each bar is a stretch when that agent was working; the bright bar is working now, the dim ones are finished. Two bright bars at the same point mean two agents worked at the same time.'),
  },
  {
    id: 'days',
    name: 'Days',
    note: t('one column per day; readable at small sizes'),
    caption:
      t('Top: the kanban board. Bottom: one column per calendar day, with the date below it. Each column is agent replies stacked on card moves, so its height is how much happened that day. The current day is outlined and days still ahead are dim. This chart stays readable when the film is small.'),
  },
  {
    id: 'graph',
    name: 'Constellation',
    note: t('files that change together, drawn as the commits arrive'),
    needsGit: true,
    caption:
      t('Top: the kanban board. Bottom: the project\'s files, drawn from the commits. One dot per file, sized by how often it was edited and coloured by file type: blue is TypeScript, green Python, amber Markdown. Grey dots and lines are folders. A coloured line joins two files that are often changed in the same commit. A file appears at the commit that created it and is highlighted while it is edited.'),
  },
  {
    id: 'cockpit',
    name: t('Flight deck'),
    note: t('the files on the left, gauges on the right'),
    needsGit: true,
    caption:
      t('Top: the kanban board. Bottom left: the project\'s files, drawn from the commits, a dot per file, joined where two files often change together. Bottom right, two gauges: cards finished per day, and lead time, the days from writing a card to finishing it; the red arc marks a long lead time. Below them three bars: cards in progress, cards waiting, and commits in the last 24 hours.'),
  },
  {
    id: 'console',
    name: 'Console',
    note: t('the files on the left, totals and recent events on the right'),
    needsGit: true,
    caption:
      t('Top: the kanban board. Bottom left: the project\'s files, drawn from the commits, a dot per file, joined to the files it often changes with. Bottom right: cards finished, the median days a card takes, and commits with their lines. Below them, one light per agent, lit while it works. At the bottom, the latest events: a card finished, an agent reporting work done, evidence attached.'),
  },
  {
    id: 'telemetry',
    name: 'Telemetry',
    note: t('the files on the left, three hourly counts and the board over time'),
    needsGit: true,
    caption:
      t('Top: the kanban board. Bottom left: the project\'s files, drawn from the commits, a dot per file, joined where two files often change together. Bottom right: three counts per hour, each with its running total: agent replies, card moves, and commits. Below them, the board over time: one band per status, stacked, brighter the closer the status is to done, named in the key. The height is the number of cards at that hour. The white line marks the same moment in all four.'),
  },
]

type RiverCtx = {
  g: CanvasRenderingContext2D
  t: Theme
  k: number
  base: string
  font: (size: number, weight?: number) => string
  name: (agent: string) => string
  numbers: boolean
}

type Rect = { x: number; y: number; w: number; h: number }

const HOUR = 3600_000

const ms = (iso: string) => new Date(iso).getTime()

function rrect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2))
  g.beginPath()
  g.moveTo(x + rr, y)
  g.arcTo(x + w, y, x + w, y + h, rr)
  g.arcTo(x + w, y + h, x, y + h, rr)
  g.arcTo(x, y + h, x, y, rr)
  g.arcTo(x, y, x + w, y, rr)
  g.closePath()
}

function clip(g: CanvasRenderingContext2D, text: string, max: number): string {
  if (g.measureText(text).width <= max) return text
  let s = text
  while (s.length > 1 && g.measureText(`${s}…`).width > max) s = s.slice(0, -1)
  return `${s}…`
}

/** The strip's title and, at the right, whatever it is counting. */
function caption(c: RiverCtx, r: Rect, left: string, right: string) {
  const { g, t: th, k } = c
  g.fillStyle = th.muted
  g.font = c.font(10, 700)
  g.fillText(left.toUpperCase(), r.x, r.y + 10 * k)
  if (!c.numbers || !right) return
  g.textAlign = 'right'
  g.fillStyle = th.dim
  g.font = c.font(10, 600)
  g.fillText(right.toUpperCase(), r.x + r.w, r.y + 10 * k)
  g.textAlign = 'left'
}

/** Day rules and the Monday labels, shared by every time-axis river. */
function timeAxis(c: RiverCtx, film: Film, r: Rect, plot: Rect, labels: boolean) {
  const { g, t: th, k } = c
  const day0 = new Date(film.t0)
  day0.setHours(0, 0, 0, 0)
  for (let at = day0.getTime(); at <= film.t1; at += 24 * HOUR) {
    if (at < film.t0) continue
    const x = r.x + film.filmAt(at) * r.w
    g.fillStyle = th.rule
    g.fillRect(x, plot.y, 1, plot.h)
    const d = new Date(at)
    if (labels && d.getDay() === 1) {
      g.fillStyle = th.dim
      g.font = c.font(9, 500)
      g.fillText(`${d.getDate()} ${monthShort(d.getMonth())}`, x + 3 * k, r.y + r.h - 2 * k)
    }
  }
}

function playhead(c: RiverCtx, r: Rect, plot: Rect, u: number) {
  c.g.fillStyle = c.t.ink
  c.g.fillRect(r.x + u * r.w - 0.5, plot.y, 1, plot.h)
}

/* ------------------------- hourly series helpers ---------------------- */

/** One number per film hour, so any series can ride the event-time clock. */
function byHour(film: Film, stamps: Array<[number, number]>): number[] {
  const out = new Array(film.hours.length).fill(0)
  const h0 = Math.floor(film.hours[0].at / HOUR)
  for (const [at, v] of stamps) {
    const i = Math.floor(at / HOUR) - h0
    if (i >= 0 && i < out.length) out[i] += v
  }
  return out
}

/** A band of hourly values rising from `mid`, drawn past or future. */
function band(
  c: RiverCtx, film: Film, f: Frame, r: Rect,
  values: number[], max: number, mid: number, height: number,
  dir: -1 | 1, tone: string, past: boolean,
) {
  const { g } = c
  let any = false
  g.beginPath()
  for (let i = 0; i < film.hours.length; i++) {
    const h = film.hours[i]
    if ((h.at <= f.at) !== past) continue
    const xa = r.x + h.u0 * r.w
    const xb = r.x + h.u1 * r.w
    const v = mid + dir * Math.sqrt(Math.max(0, values[i]) / max) * height
    if (!any) { g.moveTo(xa, mid); any = true }
    g.lineTo(xa, v)
    g.lineTo(xb, v)
    g.lineTo(xb, mid)
  }
  if (!any) return
  g.closePath()
  g.fillStyle = tone
  g.fill()
}

const turnsPerHour = (film: Film) => film.hours.map((h) => h.work)
const movesPerHour = (film: Film) => film.hours.map((h) => h.moves)

function linesPerHour(film: Film): number[] {
  const git = film.git
  if (!git) return film.hours.map(() => 0)
  return byHour(film, git.commits.map((c) => [ms(c.at), c.add + c.del] as [number, number]))
}

/* ------------------------------ A · pulse ----------------------------- */

function pulse(c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean) {
  const { t: th } = c
  const head = labels ? 16 * c.k : 0
  const plot = { x: r.x, y: r.y + head, w: r.w, h: r.h - head - (labels ? 13 * c.k : 0) }
  const mid = plot.y + plot.h * 0.58
  const up = plot.h * 0.58
  const down = plot.h * 0.42
  const work = turnsPerHour(film)
  const moves = movesPerHour(film)
  const maxW = Math.max(1, ...work)
  const maxM = Math.max(1, ...moves)

  if (labels) {
    caption(c, r, t('agents working'), t('{agentsSeen} agents · {sessionsSeen} chats · {turnsSeen} replies', { agentsSeen: f.agentsSeen, sessionsSeen: f.sessionsSeen, turnsSeen: f.turnsSeen }))
    c.g.fillStyle = f.awake.length ? th.ink : th.dim
    c.g.font = c.font(11, 500)
    c.g.fillText(clip(c.g, f.awake.map((s) => c.name(s.agent_id)).join('  ') || 'none', r.w * 0.4), r.x + 92 * c.k, r.y + 10 * c.k)
  }
  timeAxis(c, film, r, plot, labels)
  band(c, film, f, r, work, maxW, mid, up, -1, mix(c.base, th.ink, 0.1), false)
  band(c, film, f, r, moves, maxM, mid, down, 1, mix(c.base, th.ink, 0.08), false)
  band(c, film, f, r, work, maxW, mid, up, -1, th.up, true)
  band(c, film, f, r, moves, maxM, mid, down, 1, th.down, true)
  c.g.fillStyle = th.rule
  c.g.fillRect(r.x, mid, r.w, 1)
  marks(c, film, f, r, mid)
  playhead(c, r, plot, u)
}

function marks(c: RiverCtx, film: Film, f: Frame, r: Rect, mid: number) {
  for (const m of film.marks) {
    const at = ms(m.at)
    if (at > f.at) continue
    c.g.fillStyle = m.kind === 'evidence' ? c.t.lanes[2] : c.t.lanes[6]
    c.g.beginPath()
    c.g.arc(r.x + film.filmAt(at) * r.w, mid, 2.4 * c.k, 0, Math.PI * 2)
    c.g.fill()
  }
}

/* --------------------------- B · effort & output ---------------------- */

function output(c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean) {
  const { t: th, k } = c
  const head = labels ? 16 * k : 0
  const plot = { x: r.x, y: r.y + head, w: r.w, h: r.h - head - (labels ? 13 * k : 0) }
  const mid = plot.y + plot.h * 0.5
  const work = turnsPerHour(film)
  const lines = linesPerHour(film)
  const maxW = Math.max(1, ...work)
  const maxL = Math.max(1, ...lines)

  let add = 0
  let del = 0
  let commits = 0
  for (const cm of film.git?.commits ?? []) {
    if (ms(cm.at) > f.at) break
    add += cm.add
    del += cm.del
    commits++
  }

  if (labels) {
    caption(c, r, t('effort & output'), t('{commits} commits · +{add} / −{del}', { commits, add: add.toLocaleString(locale()), del: del.toLocaleString(locale()) }))
  }
  timeAxis(c, film, r, plot, labels)
  band(c, film, f, r, work, maxW, mid, plot.h * 0.5, -1, mix(c.base, th.ink, 0.1), false)
  band(c, film, f, r, lines, maxL, mid, plot.h * 0.5, 1, mix(c.base, th.ink, 0.08), false)
  band(c, film, f, r, work, maxW, mid, plot.h * 0.5, -1, th.up, true)
  band(c, film, f, r, lines, maxL, mid, plot.h * 0.5, 1, th.down, true)

  // A commit is a moment, not an hour: mark each one on the line.
  for (const cm of film.git?.commits ?? []) {
    const at = ms(cm.at)
    if (at > f.at) continue
    const x = r.x + film.filmAt(at) * r.w
    c.g.fillStyle = mix(c.base, th.ink, 0.55)
    c.g.fillRect(x, mid - 1.5 * k, 1, 3 * k)
  }
  c.g.fillStyle = th.rule
  c.g.fillRect(r.x, mid, r.w, 1)
  if (labels) {
    c.g.fillStyle = th.dim
    c.g.font = c.font(9, 500)
    c.g.fillText('replies', r.x, plot.y + 8 * k)
    c.g.fillText(t('lines changed'), r.x, plot.y + plot.h - 2 * k)
  }
  playhead(c, r, plot, u)
}

/* ---------------------------- C · churn by area ----------------------- */

const AREA_TONE: Record<string, number> = {
  frontend: 0, backend: 5, tests: 2, docs: 3, tooling: 4, other: 6,
}

function areas(c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean) {
  const { t: th, k } = c
  const git = film.git
  const head = labels ? 16 * k : 0
  const plot = { x: r.x, y: r.y + head, w: r.w, h: r.h - head - (labels ? 13 * k : 0) }
  if (!git) return
  const list = git.areas
  const series = list.map((area) =>
    byHour(film, git.commits.map((cm) => {
      const share = cm.areas[area] ?? 0
      const total = Object.values(cm.areas).reduce((a, n) => a + n, 0) || 1
      return [ms(cm.at), ((cm.add + cm.del) * share) / total] as [number, number]
    })))
  const totals = film.hours.map((_, i) => series.reduce((a, s) => a + s[i], 0))
  const max = Math.max(1, ...totals)

  if (labels) caption(c, r, t('where the work went'), t('lines changed, by area'))
  timeAxis(c, film, r, plot, labels)

  // Cumulative tops, then drawn from the outermost inward: each fill runs
  // from the baseline to its own top, so the next one covers all but its own
  // band. Drawing them in order would leave only the last colour visible.
  const tops: number[][] = []
  series.forEach((s, si) => {
    tops[si] = film.hours.map((_, i) => (si ? tops[si - 1][i] : 0) + s[i])
  })

  const draw = (past: boolean) => {
    for (let si = series.length - 1; si >= 0; si--) {
      const { g } = c
      let any = false
      g.beginPath()
      for (let i = 0; i < film.hours.length; i++) {
        const h = film.hours[i]
        if ((h.at <= f.at) !== past) continue
        const xa = r.x + h.u0 * r.w
        const xb = r.x + h.u1 * r.w
        const y = plot.y + plot.h - Math.sqrt(tops[si][i] / max) * plot.h
        if (!any) { g.moveTo(xa, plot.y + plot.h); any = true }
        g.lineTo(xa, y)
        g.lineTo(xb, y)
        g.lineTo(xb, plot.y + plot.h)
      }
      if (!any) continue
      g.closePath()
      const tone = th.lanes[AREA_TONE[list[si]] ?? si % th.lanes.length]
      g.fillStyle = past ? tone : mix(c.base, tone, 0.14)
      g.fill()
    }
  }
  // Future first, so the lit stack sits on top of its own ghost.
  draw(false)
  draw(true)

  if (labels) {
    let x = r.x
    c.g.font = c.font(9, 600)
    list.forEach((area, i) => {
      const tone = th.lanes[AREA_TONE[area] ?? i % th.lanes.length]
      c.g.fillStyle = tone
      rrect(c.g, x, r.y + r.h - 9 * k, 7 * k, 7 * k, 2 * k)
      c.g.fill()
      c.g.fillStyle = th.dim
      // Measure with the label's own font, or the swatches walk into the text.
      c.g.font = c.font(9, 600)
      c.g.fillText(area, x + 11 * k, r.y + r.h - 3 * k)
      x += 11 * k + c.g.measureText(area).width + 16 * k
    })
  }
  playhead(c, r, plot, u)
}

/* ------------------------------ D · growth ---------------------------- */

function growth(c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean) {
  const { t: th, k } = c
  const git = film.git
  const head = labels ? 16 * k : 0
  const plot = { x: r.x, y: r.y + head, w: r.w, h: r.h - head - (labels ? 13 * k : 0) }
  if (!git) return

  // Net lines, accumulated: what the repository weighs at each hour.
  const delta = byHour(film, git.commits.map((cm) => [ms(cm.at), cm.add - cm.del] as [number, number]))
  const curve: number[] = []
  let acc = 0
  for (const d of delta) {
    acc += d
    curve.push(acc)
  }
  const max = Math.max(1, ...curve)
  const files = new Set<string>()
  let seen = 0
  for (const cm of git.commits) {
    if (ms(cm.at) > f.at) break
    for (const p of cm.touched) files.add(p)
    seen++
  }

  if (labels) {
    caption(c, r, t('growth'), t('{v} net lines · {size} files · {seen} commits', { v: curve[Math.max(0, film.hours.findIndex((h) => h.at > f.at) - 1)]?.toLocaleString(locale()) ?? 0, size: files.size, seen }))
  }
  timeAxis(c, film, r, plot, labels)

  const area = (past: boolean, tone: string) => {
    const { g } = c
    let any = false
    g.beginPath()
    for (let i = 0; i < film.hours.length; i++) {
      const h = film.hours[i]
      if ((h.at <= f.at) !== past) continue
      const x = r.x + ((h.u0 + h.u1) / 2) * r.w
      const y = plot.y + plot.h - (curve[i] / max) * plot.h
      if (!any) { g.moveTo(x, plot.y + plot.h); any = true }
      g.lineTo(x, y)
    }
    if (!any) return
    const last = past
      ? r.x + film.filmAt(Math.min(f.at, film.t1)) * r.w
      : r.x + r.w
    g.lineTo(last, plot.y + plot.h)
    g.closePath()
    g.fillStyle = tone
    g.fill()
  }
  area(false, mix(c.base, th.ink, 0.09))
  area(true, mix(c.base, th.up, 0.7))

  // Each commit as a tick along the curve — the steps that built it.
  for (const cm of git.commits) {
    const at = ms(cm.at)
    if (at > f.at) continue
    const i = Math.max(0, Math.min(curve.length - 1, film.hours.findIndex((h) => h.at + HOUR > at)))
    const x = r.x + film.filmAt(at) * r.w
    const y = plot.y + plot.h - (curve[i] / max) * plot.h
    c.g.fillStyle = mix(c.base, th.ink, 0.5)
    c.g.fillRect(x, y - 1.5 * k, 1, 3 * k)
  }
  playhead(c, r, plot, u)
}

/* ------------------------------ E · lanes ----------------------------- */

function lanes(c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean) {
  const { t: th, k } = c
  const head = labels ? 16 * k : 0
  const plot = { x: r.x, y: r.y + head, w: r.w, h: r.h - head - (labels ? 13 * k : 0) }
  const rows = Math.max(1, film.agents.length)
  const step = plot.h / rows
  const bh = Math.max(1.5 * k, Math.min(6 * k, step - 1.5 * k))

  if (labels) caption(c, r, t('agent lanes'), t('{agentsSeen} of {length} agents · {sessionsSeen} sessions', { agentsSeen: f.agentsSeen, length: film.agents.length, sessionsSeen: f.sessionsSeen }))
  timeAxis(c, film, r, plot, labels)

  film.agents.forEach((agent, i) => {
    const y = plot.y + i * step
    const tone = th.lanes[i % th.lanes.length]
    for (const s of film.sessions) {
      if (s.agent_id !== agent) continue
      const a = ms(s.start)
      const b = Math.max(ms(s.end), a + 6 * 60_000)
      const xa = r.x + film.filmAt(a) * r.w
      const xb = r.x + film.filmAt(b) * r.w
      const w = Math.max(1.5 * k, xb - xa)
      if (a > f.at) {
        c.g.fillStyle = mix(c.base, th.ink, 0.07)
      } else {
        // Live now, or done: a lane that is awake is at full strength.
        c.g.fillStyle = b >= f.at && a <= f.at ? th.ink : mix(c.base, tone, 0.85)
      }
      rrect(c.g, xa, y, Math.min(w, r.x + r.w - xa), bh, bh / 2)
      c.g.fill()
    }
  })

  for (const m of film.marks) {
    const at = ms(m.at)
    if (at > f.at) continue
    const i = film.agents.indexOf(m.actor)
    if (i < 0) continue
    c.g.fillStyle = m.kind === 'evidence' ? th.lanes[2] : th.ink
    c.g.beginPath()
    c.g.arc(r.x + film.filmAt(at) * r.w, plot.y + i * step + bh / 2, 2 * k, 0, Math.PI * 2)
    c.g.fill()
  }
  playhead(c, r, plot, u)
}

/* ------------------------------- F · days ----------------------------- */

function days(c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean) {
  const { t: th, k } = c
  const head = labels ? 16 * k : 0
  const plot = { x: r.x, y: r.y + head, w: r.w, h: r.h - head - (labels ? 15 * k : 0) }
  const day0 = new Date(film.t0)
  day0.setHours(0, 0, 0, 0)
  const n = Math.max(1, Math.ceil((film.t1 - day0.getTime()) / (24 * HOUR)))
  const work = new Array(n).fill(0)
  const moves = new Array(n).fill(0)
  for (const h of film.hours) {
    const i = Math.floor((h.at - day0.getTime()) / (24 * HOUR))
    if (i < 0 || i >= n) continue
    work[i] += h.work
    moves[i] += h.moves
  }
  const max = Math.max(1, ...work.map((v, i) => v + moves[i]))
  const gap = Math.min(4 * k, (r.w / n) * 0.22)
  const bw = r.w / n - gap
  const today = Math.floor((f.at - day0.getTime()) / (24 * HOUR))

  if (labels) caption(c, r, t('by the day'), t('{n} days · {turnsSeen} replies', { n, turnsSeen: f.turnsSeen }))

  for (let i = 0; i < n; i++) {
    const x = r.x + i * (bw + gap)
    const total = work[i] + moves[i]
    const h = (total / max) * plot.h
    const wh = total ? (work[i] / total) * h : 0
    const past = i < today
    const live = i === today
    const y = plot.y + plot.h - h
    c.g.fillStyle = past || live ? th.up : mix(c.base, th.ink, 0.1)
    rrect(c.g, x, y, bw, wh, 2 * k)
    c.g.fill()
    c.g.fillStyle = past || live ? th.down : mix(c.base, th.ink, 0.07)
    rrect(c.g, x, y + wh, bw, Math.max(0, h - wh), 2 * k)
    c.g.fill()
    if (live) {
      c.g.strokeStyle = th.ink
      c.g.lineWidth = 1
      rrect(c.g, x - 1.5 * k, y - 1.5 * k, bw + 3 * k, h + 3 * k, 3 * k)
      c.g.stroke()
    }
    if (labels && n <= 32) {
      const d = new Date(day0.getTime() + i * 24 * HOUR)
      c.g.fillStyle = live ? th.ink : th.dim
      c.g.font = c.font(8.5, live ? 700 : 500)
      c.g.textAlign = 'center'
      c.g.fillText(String(d.getDate()), x + bw / 2, r.y + r.h - 3 * k)
      c.g.textAlign = 'left'
    }
  }
}

/* --------------------------- G · constellation ------------------------ */

/**
 * The repository, simulated forward through its own history.
 *
 * The layout is not a picture of the finished codebase with things fading
 * in — it is the codebase being built. The simulation walks the commits in
 * order: a file is inserted the moment it is first written, sprouting out of
 * the folder that holds it, and the whole structure then relaxes before the
 * next commit lands. Folders push each other apart, children hold to their
 * parent, co-changed files pull across folder walls, and every arrival
 * shoves its neighbours aside. The tree opens as the work fills it.
 *
 * It is still pure. The walk runs once, seeded and step-counted, and stores
 * a position for every node at every commit; drawing interpolates between
 * two of those. Same input, same film — playback and export cannot disagree,
 * and nothing is simulated per frame.
 */

type Body = { x: number; y: number; vx: number; vy: number }

/** One stored moment of the simulation: where everything stood, and the camera. */
type Key = {
  at: number
  /** Nodes then hubs, x/y interleaved. */
  pos: Float32Array
  cam: { cx: number; cy: number; halfX: number; halfY: number }
}

type Sim = {
  keys: Key[]
  /** Film position → fractional key index, evenly paced. See `pace`. */
  pace: Float32Array
  nodes: GraphNode[]
  hubs: Array<{ path: string; name: string; parent: number; n: number }>
  /** Film time each node was first written, and each tie first formed. */
  nodeBorn: number[]
  hubBorn: number[]
  edges: Array<[number, number, number, number]>
}

const sims = new WeakMap<Film, Sim>()


const SPRING_DIR = 0.34      // a folder's distance from its parent
const SPRING_FILE = 0.1      // a file's distance from its folder
const SETTLE_STEPS = 420     // to solve the finished repository
const REWIND_STEPS = 3       // to re-settle after taking one commit away
/** The most a body may move in one step. Nothing lurches. */
const MAX_STEP = 0.0035
/** Passes of temporal smoothing over the finished keyframes. */
const SMOOTH_PASSES = 3
/** How hard a body is held to its place in the finished repository. */
const ANCHOR = 0.4
/** And how far it may ever stray from it. */
const MAX_DRIFT = 0.09

function simulate(film: Film): Sim {
  const cached = sims.get(film)
  if (cached) return cached
  const git = film.git
  const blank: Sim = {
    keys: [], pace: new Float32Array(0), nodes: [], hubs: [], nodeBorn: [], hubBorn: [], edges: [],
  }
  if (!git) return blank
  const { nodes, edges, dirs } = git.graph
  const n = nodes.length
  const m = dirs.length
  if (!n) return blank

  const byPath = new Map(nodes.map((nd, i) => [nd.path, i]))
  const nodeBorn = nodes.map((nd) => ms(nd.born))
  const hubBorn = dirs.map(() => Infinity)
  nodes.forEach((nd, i) => {
    let d = nd.dir
    while (d >= 0) {
      hubBorn[d] = Math.min(hubBorn[d], nodeBorn[i])
      d = dirs[d].parent
    }
  })
  const own = dirs.map(() => 0)
  for (const nd of nodes) if (nd.dir >= 0) own[nd.dir]++

  const tie = edges.map(([a, b, w, since]) => [a, b, w, ms(since)] as [number, number, number, number])

  const N = n + m
  const body: Body[] = Array.from({ length: N }, () => ({ x: 0, y: 0, vx: 0, vy: 0 }))
  const alive = new Array<boolean>(N).fill(true)
  const hubOf = (i: number) => (nodes[i].dir >= 0 ? n + nodes[i].dir : -1)
  const parentOf = (b: number) =>
    b < n ? hubOf(b) : (dirs[b - n].parent >= 0 ? n + dirs[b - n].parent : -1)

  // Seed the finished repository on its own tree, so the solve starts from
  // something shaped like a codebase and only has to tidy it.
  const kids: number[][] = dirs.map(() => [])
  const roots: number[] = []
  dirs.forEach((d, i) => (d.parent >= 0 ? kids[d.parent].push(i) : roots.push(i)))
  const weight = dirs.map(() => 0)
  const weigh = (i: number): number => {
    if (weight[i]) return weight[i]
    weight[i] = own[i] + kids[i].reduce((a, x) => a + weigh(x), 0)
    return weight[i]
  }
  roots.forEach(weigh)
  const arc = dirs.map(() => ({ a0: 0, a1: 0 }))
  const share = (list: number[], a0: number, a1: number) => {
    const total = list.reduce((a, i) => a + weight[i], 0) || 1
    let a = a0
    for (const i of list) {
      const w = ((a1 - a0) * weight[i]) / total
      arc[i] = { a0: a, a1: a + w }
      share(kids[i], a + w * 0.03, a + w * 0.97)
      a += w
    }
  }
  share(roots, 0, Math.PI * 2)
  const maxDepth = Math.max(1, ...dirs.map((d) => d.depth))
  dirs.forEach((d, i) => {
    const mid = (arc[i].a0 + arc[i].a1) / 2
    const rad = 0.12 + (d.depth / (maxDepth + 1)) * 0.6
    body[n + i].x = Math.cos(mid) * rad
    body[n + i].y = Math.sin(mid) * rad
  })
  const seat = new Map<number, number>()
  nodes.forEach((nd, i) => {
    if (nd.dir < 0) return
    const k = seat.get(nd.dir) ?? 0
    seat.set(nd.dir, k + 1)
    const { a0, a1 } = arc[nd.dir]
    const a = a0 + (a1 - a0) * ((k + 0.5) / Math.max(1, own[nd.dir]))
    const rad = 0.12 + (dirs[nd.dir].depth / (maxDepth + 1)) * 0.6 + 0.09
    body[i].x = Math.cos(a) * rad
    body[i].y = Math.sin(a) * rad
  })

  // The finished layout, kept as every node's home. During the rewind each
  // body is pulled back toward it, so a node only leaves its final place when
  // the structure around it genuinely needs the room, and returns as soon as
  // it can. Without this every node crawls a little in every frame and the
  // whole picture is permanently in motion — which is what read as torn.
  const home: Array<{ x: number; y: number }> = Array.from({ length: N }, () => ({ x: 0, y: 0 }))
  let anchor = 0

  const step = (now: number, damp: number) => {
    const fx = new Float64Array(N)
    const fy = new Float64Array(N)

    for (let b = 0; b < N; b++) {
      if (!alive[b]) continue
      const parent = parentOf(b)
      if (parent < 0 || !alive[parent]) continue
      const rest = b < n ? SPRING_FILE : SPRING_DIR
      const dx = body[parent].x - body[b].x
      const dy = body[parent].y - body[b].y
      const d = Math.hypot(dx, dy) || 1e-5
      const pull = (d - rest) * 0.14
      fx[b] += (dx / d) * pull
      fy[b] += (dy / d) * pull
      fx[parent] -= (dx / d) * pull * 0.25
      fy[parent] -= (dy / d) * pull * 0.25
    }

    for (const [a, b, w, since] of tie) {
      if (since > now || !alive[a] || !alive[b]) continue
      const dx = body[b].x - body[a].x
      const dy = body[b].y - body[a].y
      const d = Math.hypot(dx, dy) || 1e-5
      const pull = (d - 0.16) * Math.min(1, w / 8) * 0.022
      fx[a] += (dx / d) * pull
      fy[a] += (dy / d) * pull
      fx[b] -= (dx / d) * pull
      fy[b] -= (dy / d) * pull
    }

    for (let i = 0; i < N; i++) {
      if (!alive[i]) continue
      const heavy = i >= n ? 3.4 : 1
      for (let j = i + 1; j < N; j++) {
        if (!alive[j]) continue
        const dx = body[j].x - body[i].x
        const dy = body[j].y - body[i].y
        const d2 = dx * dx + dy * dy + 1e-6
        if (d2 > 0.25) continue
        const d = Math.sqrt(d2)
        const push = (0.00135 * heavy * (j >= n ? 3.4 : 1)) / d2
        fx[i] -= (dx / d) * push
        fy[i] -= (dy / d) * push
        fx[j] += (dx / d) * push
        fy[j] += (dy / d) * push
      }
      fx[i] -= body[i].x * 0.006
      fy[i] -= body[i].y * 0.006
      if (anchor) {
        fx[i] += (home[i].x - body[i].x) * anchor
        fy[i] += (home[i].y - body[i].y) * anchor
      }
    }

    for (let i = 0; i < N; i++) {
      if (!alive[i]) continue
      body[i].vx = (body[i].vx + fx[i]) * damp
      body[i].vy = (body[i].vy + fy[i]) * damp
      // Nothing lurches: a body may only ever creep, so a frame is never far
      // from the one before it.
      const speed = Math.hypot(body[i].vx, body[i].vy)
      if (speed > MAX_STEP) {
        body[i].vx = (body[i].vx / speed) * MAX_STEP
        body[i].vy = (body[i].vy / speed) * MAX_STEP
      }
      body[i].x += body[i].vx
      body[i].y += body[i].vy
      if (anchor) {
        // A hard ceiling on how far a node may ever be from its final place.
        // Earlier frames are the last frame with pieces missing — not a
        // different arrangement of the same pieces.
        const dx = body[i].x - home[i].x
        const dy = body[i].y - home[i].y
        const drift = Math.hypot(dx, dy)
        if (drift > MAX_DRIFT) {
          body[i].x = home[i].x + (dx / drift) * MAX_DRIFT
          body[i].y = home[i].y + (dy / drift) * MAX_DRIFT
        }
      }
    }
  }

  // 1 · Solve the repository as it finished. This is the layout the film is
  //     heading for, and it is the only one solved from scratch.
  const commits = git.commits
  const endAt = commits.length ? ms(commits[commits.length - 1].at) : film.t1
  for (let s = 0; s < SETTLE_STEPS; s++) step(endAt, 0.82)
  for (let i = 0; i < N; i++) {
    home[i].x = body[i].x
    home[i].y = body[i].y
  }
  anchor = ANCHOR

  // 2 · Then walk backwards, taking one commit's arrivals away at a time and
  //     letting what remains close the gap. Every earlier frame is a small
  //     deformation of the frame after it — which, played forward, is a graph
  //     growing into a shape it already fits, instead of one thrashing toward
  //     a shape it has not found yet.
  const born = (i: number) => (i < n ? nodeBorn[i] : hubBorn[i - n])
  const back: Key[] = []
  const grab = (at: number) => {
    const pos = new Float32Array(N * 2)
    for (let i = 0; i < N; i++) {
      pos[i * 2] = body[i].x
      pos[i * 2 + 1] = body[i].y
    }
    back.push({ at, pos, cam: { cx: 0, cy: 0, halfX: 1, halfY: 1 } })
  }

  for (let c = commits.length - 1; c >= 0; c--) {
    grab(ms(commits[c].at))
    // Everything that first appeared at this commit is unwritten a moment ago.
    const before = c > 0 ? ms(commits[c - 1].at) : -Infinity
    let removed = false
    for (let i = 0; i < N; i++) {
      if (alive[i] && born(i) > before) {
        alive[i] = false
        removed = true
      }
    }
    if (removed) for (let s = 0; s < REWIND_STEPS; s++) step(before, 0.82)
  }
  back.reverse()
  const keys = back

  // 3 · Smooth along time. Three light passes over the sequence take out the
  //     last of the twitch without moving anything anywhere it was not going.
  for (let pass = 0; pass < SMOOTH_PASSES; pass++) {
    const prev = keys.map((key) => new Float32Array(key.pos))
    for (let k = 1; k < keys.length - 1; k++) {
      const a = prev[k - 1]
      const b = prev[k]
      const c2 = prev[k + 1]
      for (let i = 0; i < N * 2; i++) keys[k].pos[i] = a[i] * 0.25 + b[i] * 0.5 + c2[i] * 0.25
    }
  }

  // No recentring. The solve already pulls toward the origin, so the finished
  // layout is centred and every earlier frame is anchored to it — subtracting
  // a per-frame centroid on top of that only shifted all hundred and thirty
  // nodes together in every frame, which was most of the motion left.

  // One camera for the whole film, taken from the finished repository.
  //
  // A frame that re-fits itself as the graph grows moves every pixel in every
  // frame — the picture is then never still even when nothing in it is
  // changing, and that reads as the whole thing shivering. Framed once on the
  // end state, the graph grows into a fixed window instead, which is also
  // what "the last frame is the reference" means: it is the shot, and
  // everything before it is that shot with pieces missing.
  // One radius, from the finished repository. The forces are the same in
  // every direction, so the layout is round and the frame should show it
  // round: the scale is uniform, and the strip's spare width is left as
  // margin for the names rather than spent stretching the picture.
  const last = keys[keys.length - 1]
  const reach: number[] = []
  for (let i = 0; i < N; i++) {
    reach.push(Math.hypot(last.pos[i * 2], last.pos[i * 2 + 1]))
  }
  reach.sort((a, b) => a - b)
  const p94 = reach[Math.min(reach.length - 1, Math.floor(reach.length * 0.94))]
  const half = Math.max(0.12, p94 * 1.1 + 0.03)
  for (const key of keys) key.cam = { cx: 0, cy: 0, halfX: half, halfY: half }

  const sim: Sim = {
    keys,
    pace: pace(film, keys),
    nodes,
    hubs: dirs.map((d, i) => ({ path: d.path, name: d.name, parent: d.parent, n: own[i] })),
    nodeBorn,
    hubBorn,
    edges: tie,
  }
  sims.set(film, sim)
  void byPath
  return sim
}

/**
 * How fast the graph is allowed to advance.
 *
 * The film's clock spends its running time where the work was, and a busy
 * hour still holds more commits than a quiet one even after that. Read
 * straight off the clock, the graph therefore crosses anywhere between zero
 * and six commits in a single frame: it freezes for a second, then lurches.
 * That is the whole of the roughness — not the frame rate.
 *
 * So the mapping from film position to commit is smoothed. Sampled on an even
 * grid, blurred, and forced back to monotonic, it advances at a near-constant
 * rate while still arriving at the right commit at the right moment. The graph
 * runs a few minutes ahead or behind its own timestamp, and moves evenly.
 */
const PACE_SAMPLES = 1200

function pace(film: Film, keys: Key[]): Float32Array {
  const out = new Float32Array(PACE_SAMPLES + 1)
  if (!keys.length) return out
  let k = 0
  for (let s = 0; s <= PACE_SAMPLES; s++) {
    const at = film.wallAt(s / PACE_SAMPLES)
    while (k + 1 < keys.length && keys[k + 1].at <= at) k++
    out[s] = k
  }
  // A wide blur: this is the one place the film is allowed to lie a little,
  // and the lie buys even motion.
  const span = 26
  const smooth = new Float32Array(out.length)
  for (let s = 0; s < out.length; s++) {
    let sum = 0
    let n = 0
    for (let d = -span; d <= span; d++) {
      const i = s + d
      if (i < 0 || i >= out.length) continue
      sum += out[i]
      n++
    }
    smooth[s] = sum / n
  }
  // Never go backwards: a file that has appeared must not un-appear.
  for (let s = 1; s < smooth.length; s++) {
    if (smooth[s] < smooth[s - 1]) smooth[s] = smooth[s - 1]
  }
  return smooth
}

/** Where everything stands at `at`, interpolated between the two keyframes. */
function frameOf(sim: Sim, u: number) {
  const { keys, pace: curve } = sim
  if (!keys.length) return null
  const end = keys.length - 1
  const clampIdx = (i: number) => Math.min(end, Math.max(0, i))
  const s = Math.min(PACE_SAMPLES, Math.max(0, u * PACE_SAMPLES))
  const lo = Math.floor(s)
  const hi = Math.min(PACE_SAMPLES, lo + 1)
  const idx = curve[lo] + (curve[hi] - curve[lo]) * (s - lo)
  const i = clampIdx(Math.floor(idx))
  return { i, t: Math.min(1, Math.max(0, idx - i)), keys, clampIdx }
}

/**
 * A curve through the stored moments, not a chain of straight lines.
 *
 * There is roughly one moment per drawn frame, so straight-line interpolation
 * puts a corner in every node's path at every frame — the velocity changes
 * direction constantly, which is exactly the faceted, restless quality that
 * survives however small the steps are. A Catmull-Rom spline passes through
 * the same positions with a continuous velocity, so the motion curves.
 */
function spline(p0: number, p1: number, p2: number, p3: number, it: number): number {
  const t2 = it * it
  const t3 = t2 * it
  return 0.5 * (
    2 * p1
    + (-p0 + p2) * it
    + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
  )
}

/**
 * Colour by file type, not by area.
 *
 * Ninety-five of Slightly Parallel's hundred and thirty busiest files are frontend, so
 * colouring by area paints almost the whole graph one blue. The extension is
 * what a reader can pick out — tests from components, Python from
 * TypeScript, prose from code — and it is the convention every codebase
 * visualisation uses for exactly that reason.
 */
const EXT_TONE: Record<string, number> = {
  tsx: 0, ts: 5, py: 2, md: 3, css: 4, json: 6, mjs: 1, js: 1, sh: 4, yml: 3, html: 1,
}

function fileTone(it: Theme, node: GraphNode): string {
  const name = node.name
  if (/\.test\.|\.spec\.|^test_/.test(name)) return it.lanes[2 % it.lanes.length]
  const ext = name.includes('.') ? name.split('.').pop() ?? '' : ''
  const i = EXT_TONE[ext]
  if (i !== undefined) return it.lanes[i % it.lanes.length]
  let h = 0
  for (let n = 0; n < ext.length; n++) h = (h * 31 + ext.charCodeAt(n)) % 997
  return it.lanes[h % it.lanes.length]
}

/** How long a new file keeps arriving, and a touch keeps glowing. */
const ARRIVE_MS = 8 * HOUR
const BEAM_MS = 7 * HOUR
const ease = (x: number) => 1 - (1 - x) ** 3
const smoothstep = (x: number) => {
  const v = Math.min(1, Math.max(0, x))
  return v * v * (3 - 2 * v)
}

/**
 * A touch swells and fades; it does not switch on.
 *
 * With two hundred and forty-seven commits across two hundred and fifty
 * frames there is a commit landing in almost every one of them, so a beam
 * that appears at full strength is a flash in every frame — which is exactly
 * what made the graph feel torn. Rising over the first fifth of its life and
 * falling over the rest, the beams overlap and blend instead.
 */
const touchGlow = (age: number) => {
  if (age < 0 || age > BEAM_MS) return 0
  const x = age / BEAM_MS
  return x < 0.2 ? smoothstep(x / 0.2) : smoothstep(1 - (x - 0.2) / 0.8)
}

function graph(c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean) {
  const { t: th, k, g } = c
  const git = film.git
  if (!git) return
  const sim = simulate(film)
  const at = frameOf(sim, u)
  if (!at) return
  const { nodes, hubs, nodeBorn, hubBorn, edges } = sim
  const n = nodes.length

  const head = labels ? 16 * k : 0
  const pad = 10 * k
  const box = {
    x: r.x + pad, y: r.y + head + pad * 0.5,
    w: r.w - pad * 2, h: r.h - head - pad,
  }
  const plot = box

  // The camera between the two keyframes, so the pull-back is as smooth as
  // the motion inside it.
  // Uniform scale, set by whichever side is tighter — in a wide strip that is
  // the height. A circle stays a circle. The camera is fixed, so one moment
  // is enough to read it from.
  const half = at.keys[at.i].cam.halfY
  const scale = Math.min(plot.w, plot.h) / (half * 2)
  const k0 = at.keys[at.clampIdx(at.i - 1)].pos
  const k1 = at.keys[at.i].pos
  const k2 = at.keys[at.clampIdx(at.i + 1)].pos
  const k3 = at.keys[at.clampIdx(at.i + 2)].pos
  const px = (i: number) => {
    const x = spline(k0[i * 2], k1[i * 2], k2[i * 2], k3[i * 2], at.t)
    const y = spline(k0[i * 2 + 1], k1[i * 2 + 1], k2[i * 2 + 1], k3[i * 2 + 1], at.t)
    return {
      x: plot.x + plot.w / 2 + x * scale,
      y: plot.y + plot.h / 2 + y * scale,
    }
  }

  // What the repository knows at this instant.
  const age = nodeBorn.map((b) => f.at - b)
  const grown = age.map((a) => (a < 0 ? 0 : ease(Math.min(1, a / ARRIVE_MS))))
  const touches = new Array(n).fill(0)
  const byPath = new Map(nodes.map((nd, i) => [nd.path, i]))
  const heat = new Array(n).fill(0)
  let live = 0
  for (const cm of git.commits) {
    const when = ms(cm.at)
    if (when > f.at) break
    live++
    const h = touchGlow(f.at - when)
    for (const path of cm.touched) {
      const i = byPath.get(path)
      if (i === undefined) continue
      touches[i]++
      if (h > heat[i]) heat[i] = h
    }
  }
  const maxTouch = Math.max(1, ...touches)
  const shown = grown.filter((v) => v > 0).length

  // Chosen from the whole history, so the set never changes mid-film.
  const named = nodes
    .map((nd, i) => [i, nd.churn] as [number, number])
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([i]) => i)

  if (labels) {
    const ties = edges.filter((e) => e[3] <= f.at).length
    caption(c, r, t('the files'), t('{shown} files · {ties} links · {live} commits', { shown, ties, live }))
  }

  // Branches: a folder's line to its parent, drawn as thick as it is full.
  hubs.forEach((h, i) => {
    if (hubBorn[i] > f.at || h.parent < 0 || hubBorn[h.parent] > f.at) return
    const a = px(n + i)
    const b = px(n + h.parent)
    g.strokeStyle = mix(c.base, th.ink, 0.16)
    g.lineWidth = Math.min(2.6 * k, (0.7 + Math.sqrt(h.n) * 0.35) * k)
    g.beginPath()
    g.moveTo(a.x, a.y)
    g.lineTo(b.x, b.y)
    g.stroke()
  })

  // Ties, only once the two files have met.
  for (const [a, b, w, since] of edges) {
    if (since > f.at || !grown[a] || !grown[b]) continue
    const pa = px(a)
    const pb = px(b)
    const fresh = Math.min(1, (f.at - since) / ARRIVE_MS)
    // A pair that met once is a coincidence; the strength of the line should
    // say so, or four hundred of them become a net over everything.
    g.strokeStyle = mix(c.base, th.up, Math.min(0.7, (0.06 + w * 0.06) * (0.45 + 0.55 * fresh)))
    g.lineWidth = Math.min(1.8 * k, (0.5 + w * 0.08) * k)
    g.beginPath()
    g.moveTo(pa.x, pa.y)
    g.lineTo(pb.x, pb.y)
    g.stroke()
  }

  // A commit lands as a beam from the folder to each file it touched.
  nodes.forEach((nd, i) => {
    if (heat[i] <= 0 || nd.dir < 0 || hubBorn[nd.dir] > f.at) return
    const a = px(n + nd.dir)
    const b = px(i)
    g.strokeStyle = mix(c.base, th.ink, 0.1 + 0.45 * heat[i])
    g.lineWidth = (0.4 + 1.5 * heat[i]) * k
    g.beginPath()
    g.moveTo(a.x, a.y)
    g.lineTo(b.x, b.y)
    g.stroke()
  })

  // Folder knots, so the tree has joints.
  //
  // Filled, as they were — rings read worse — but bigger and darker than the
  // files around them. A folder should sit behind the picture, not compete
  // with it: heavier than a file so the joints are legible, darker than the
  // ground so they never pull the eye off the colour.
  hubs.forEach((h, i) => {
    if (hubBorn[i] > f.at) return
    const p = px(n + i)
    g.fillStyle = mix(c.base, th.ink, 0.13)
    g.beginPath()
    g.arc(p.x, p.y, Math.min(7 * k, (2.4 + Math.sqrt(h.n) * 0.95) * k), 0, Math.PI * 2)
    g.fill()
  })

  // A node's size says how worked the file is, not how far the camera has
  // pulled back — so it is in screen pixels and does not shrink with the zoom.
  const radiusOf = (i: number) =>
    (2 + 6 * Math.sqrt(touches[i] / maxTouch)) * k * grown[i]

  nodes.forEach((nd, i) => {
    if (!grown[i]) return
    const p = px(i)
    const tone = fileTone(th, nd)
    const rad = Math.max(0.7 * k, radiusOf(i))
    const arriving = 1 - Math.min(1, age[i] / ARRIVE_MS)
    const glow = Math.max(heat[i], arriving)
    if (glow > 0) {
      g.fillStyle = mix(c.base, tone, 0.26 * glow)
      g.beginPath()
      g.arc(p.x, p.y, rad + (2 + 7 * glow) * k, 0, Math.PI * 2)
      g.fill()
    }
    // Continuous, not a threshold: a node brightens toward white as it is
    // worked and dims back, rather than flipping between two colours.
    g.fillStyle = mix(tone, th.ink, heat[i] * 0.85)
    g.beginPath()
    g.arc(p.x, p.y, rad, 0, Math.PI * 2)
    g.fill()
  })

  if (!labels) return

  const taken: Array<[number, number, number, number]> = []
  const free = (x: number, y: number, w: number, h: number) =>
    !taken.some(([a, b, cw, ch]) => x < a + cw && a < x + w && y < b + ch && b < y + h)

  g.font = c.font(9, 700)
  hubs.forEach((h, i) => {
    if (hubBorn[i] > f.at || h.n < 4) return
    const p = px(n + i)
    const w = g.measureText(h.name).width + 8 * k
    if (!free(p.x - w / 2, p.y - 17 * k, w, 14 * k)) return
    taken.push([p.x - w / 2, p.y - 17 * k, w, 14 * k])
    g.fillStyle = mix(c.base, th.ink, 0.42)
    g.textAlign = 'center'
    g.fillText(h.name, p.x, p.y - 7 * k)
    g.textAlign = 'left'
  })

  // The names are a fixed cast, chosen once from the finished repository, and
  // they fade in when their file appears. Picking them per frame — by whatever
  // is hottest right now — meant a dozen labels blinking on and off every
  // frame, which read as noise however smooth the motion underneath was.
  named
    .forEach((i) => {
      const appear = smoothstep((f.at - nodeBorn[i]) / ARRIVE_MS)
      if (appear <= 0.02) return
      const p = px(i)
      const rad = Math.max(0.7 * k, radiusOf(i))
      g.font = c.font(9.5, 600)
      const text = clip(g, nodes[i].name, 150 * k)
      const w = g.measureText(text).width
      // A round graph in a wide strip leaves both sides empty, so the names
      // live out there — one column each side, with a hairline back to the
      // dot. The middle stays the picture instead of a pile of text over it.
      const mid = plot.x + plot.w / 2
      const ring = Math.min(plot.w, plot.h) / 2
      const out = p.x < mid ? -1 : 1
      const edge = mid + out * (ring + 12 * k)
      const x = out < 0 ? edge - w : edge
      const y = p.y - 7.5 * k
      // Claim more than the glyphs occupy: two names a couple of pixels
      // apart clear a tight box and still read as one smudge.
      const bh = 15 * k
      if (x < r.x || x + w > r.x + r.w || !free(x - 4 * k, y, w + 8 * k, bh)) return
      taken.push([x - 4 * k, y, w + 8 * k, bh])
      g.save()
      g.globalAlpha = appear
      g.strokeStyle = mix(c.base, th.ink, 0.18)
      g.lineWidth = 0.8 * k
      g.beginPath()
      g.moveTo(p.x + out * (rad + 2 * k), p.y)
      g.lineTo(out < 0 ? x + w + 4 * k : x - 4 * k, p.y)
      g.stroke()
      g.fillStyle = mix(c.base, th.ink, 0.55 + 0.4 * heat[i])
      g.fillText(text, x, p.y + 3 * k)
      g.restore()
    })
}

/* -------------------------- H · the flight deck ----------------------- */

/**
 * The codebase with instruments beside it.
 *
 * A graph tells you the shape of the thing; it does not tell you how fast it
 * is going, how much is in flight, or whether anything is wrong. Panels do —
 * and a dial with a needle and a redline is read without a legend, which is
 * what you want from something meant to be scanned rather than studied.
 *
 * Two arrangements of the same idea, because which one reads better is a
 * matter of taste: dials and meters, or readouts and a running log.
 */
function deck(
  c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean,
  style: 'cockpit' | 'console' | 'telemetry',
) {
  const { t: th, k } = c
  const gap = 12 * k
  // The graph keeps the larger half; the instruments only need to be legible.
  const leftW = Math.round(r.w * 0.56)
  const left = { x: r.x, y: r.y, w: leftW, h: r.h }
  const right = { x: r.x + leftW + gap, y: r.y + (labels ? 16 * k : 0), w: r.w - leftW - gap, h: r.h - (labels ? 16 * k : 0) }

  graph(c, film, f, left, u, labels)

  const p = { g: c.g, t: th, k, base: c.base, font: c.font, numbers: c.numbers }
  const d = readings(film, f)
  const cell = (col: number, row: number, cols: number, rows: number, span = 1): Rect => {
    const cw = (right.w - gap * (cols - 1)) / cols
    const ch = (right.h - gap * (rows - 1)) / rows
    return {
      x: right.x + col * (cw + gap),
      y: right.y + row * (ch + gap),
      w: cw * span + gap * (span - 1),
      h: ch,
    }
  }
  const inset = (b: Rect, pad = 8): Rect =>
    ({ x: b.x + pad * k, y: b.y + pad * k, w: b.w - pad * 2 * k, h: b.h - pad * 2 * k })

  if (style === 'cockpit') {
    // Two dials over three meters: rate and lead time are the two numbers a
    // board is steered by, and the rest is how full it is.
    const a = cell(0, 0, 2, 2)
    const b = cell(1, 0, 2, 2)
    bezel(p, a, '')
    bezel(p, b, '')
    dial(p, inset(a, 6), {
      value: d.perDay, max: 8, label: t('cards / day'), tone: th.up,
      read: d.perDay.toFixed(1),
    })
    dial(p, inset(b, 6), {
      value: d.leadDays, max: 6, redline: 3, label: t('lead time · days'), tone: th.down,
      read: d.leadDays ? d.leadDays.toFixed(1) : '—',
    })
    const low = cell(0, 1, 1, 2)
    bezel(p, low, '')
    const m = inset(low, 10)
    const rowH = m.h / 3
    meter(p, { ...m, y: m.y, h: rowH }, {
      value: d.doing, max: Math.max(8, d.doing), label: t('in progress'), read: String(d.doing), tone: th.lanes[3],
    })
    meter(p, { ...m, y: m.y + rowH, h: rowH }, {
      value: d.backlog, max: Math.max(30, d.backlog), label: t('waiting'), read: String(d.backlog), tone: th.lanes[0],
    })
    meter(p, { ...m, y: m.y + rowH * 2, h: rowH }, {
      value: d.commitsToday, max: 40, label: t('commits · 24h'), read: String(d.commitsToday), tone: th.lanes[2],
    })
    return
  }

  if (style === 'telemetry') {
    // Five readings, each a strip of its own history with the current value
    // at the end. Stacked they are a panel you read down rather than across.
    const perHour = (pick: (h: Film['hours'][number]) => number) => film.hours.map(pick)
    const commitsPerHour = film.hours.map((h) => {
      let n = 0
      for (const cm of film.git?.commits ?? []) {
        const at = new Date(cm.at).getTime()
        if (at >= h.at && at < h.at + 3600_000) n++
      }
      return n
    })
    // Everything on this panel rides the film's own clock: the hours already
    // carry their position across the film, and the flow below reads the same
    // mapping, so the four playheads are one line.
    const u0 = film.hours.map((h) => h.u0)
    const u1 = film.hours.map((h) => h.u1)
    const head = Math.min(1, Math.max(0, film.filmAt(f.at)))
    const rows: Array<[string, number[], string, string]> = [
      // Three kinds of event, so three hues — and none of them the one the
      // board's ramp is built from, or a strip means two things at once.
      [t('agent replies'), perHour((h) => h.work), th.lanes[0], String(d.turns)],
      [t('card moves'), perHour((h) => h.moves), th.lanes[3], String(d.moves)],
      [t('commits'), commitsPerHour, th.lanes[2], String(d.commits)],
    ]
    // Four blocks of one height, one housing, one clock. The board gets the
    // last slot and is drawn in the same frame as the three above it — the
    // only difference is bands instead of bars.
    const unit = right.h / 4
    rows.forEach(([label, series, tone, read], i) => {
      strip(p, { x: right.x, y: right.y + i * unit, w: right.w, h: unit - gap * 0.6 }, {
        series, u0, u1, now: head, label, read, tone,
      })
    })
    flow(p, film, f, {
      x: right.x, y: right.y + 3 * unit, w: right.w, h: unit - gap * 0.6,
    }, { label: t('the board'), read: String(d.live) })
    return
  }

  // Console: three figures across the top, the lamps that say who is awake,
  // then the landing curve and what just happened. Rows sized to what each
  // holds rather than cut into an even grid — a third of a tall panel is a
  // lot of nothing under a number.
  const rows = { head: right.h * 0.3, lamp: right.h * 0.2, foot: right.h * 0.5 }
  const cw = (right.w - gap * 2) / 3
  const headRow = (i: number): Rect =>
    ({ x: right.x + i * (cw + gap), y: right.y, w: cw, h: rows.head })

  readout(p, headRow(0), {
    value: String(d.done), label: t('done'), sub: t('of {length} cards', { length: film.cards.length }), size: 30,
  })
  readout(p, headRow(1), {
    value: d.leadDays ? d.leadDays.toFixed(1) : '—', label: t('lead · days'),
    sub: t('median, created to done'), size: 30,
  })
  readout(p, headRow(2), {
    value: String(d.commits), label: t('commits'),
    sub: `+${d.add.toLocaleString(locale())} / −${d.del.toLocaleString(locale())}`, size: 30,
  })

  lamps(p, { x: right.x, y: right.y + rows.head, w: right.w, h: rows.lamp }, {
    n: film.agents.length, on: d.awake, label: t('agents working'), tone: th.up,
  })

  const footY = right.y + rows.head + rows.lamp
  const traceW = (right.w - gap) * 0.52
  trace(p, { x: right.x, y: footY, w: traceW, h: rows.foot }, {
    series: d.curve, now: d.now, label: t('cards done'), tone: th.up,
  })
  log(p, film, f, { x: right.x + traceW + gap, y: footY, w: right.w - traceW - gap, h: rows.foot }, {
    label: t('last events'), rows: 5,
  })
}

/* ------------------------------- registry ----------------------------- */

type Draw = (c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean) => void

const DRAW: Record<RiverId, Draw> = {
  pulse, output, areas, growth, lanes, days, graph,
  cockpit: (c, film, f, r, u, labels) => deck(c, film, f, r, u, labels, 'cockpit'),
  console: (c, film, f, r, u, labels) => deck(c, film, f, r, u, labels, 'console'),
  telemetry: (c, film, f, r, u, labels) => deck(c, film, f, r, u, labels, 'telemetry'),
}

/** The solved layout, for tests that assert it is deterministic. */
export const __layoutForTest = simulate

export function drawRiver(
  id: RiverId, c: RiverCtx, film: Film, f: Frame, r: Rect, u: number, labels: boolean,
) {
  // A git river with no repository behind it falls back rather than showing
  // an empty box: the film should never claim something it cannot read.
  const wanted = RIVERS.find((x) => x.id === id)
  const use = wanted?.needsGit && !film.git ? 'pulse' : id
  ;(DRAW[use] ?? pulse)(c, film, f, r, u, labels)
}
