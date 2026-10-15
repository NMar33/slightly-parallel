/**
 * Instruments.
 *
 * The board says what happened; these say how the thing is running right now.
 * They are drawn as instruments rather than as charts on purpose: a dial with
 * a needle and a redline is read at a glance and without a legend, which is
 * the whole point of a panel you are supposed to be able to scan while doing
 * something else.
 *
 * Every reading is live — it moves with the playhead — and every one of them
 * is a number the log already knows. Nothing here is decoration standing in
 * for data that does not exist.
 */

import type { Film, Frame } from './film'
import { COLUMNS, COLUMN_LABEL, statusAt, vitalsAt, type Column } from './film'
import type { Theme } from './theme'
import { mix } from './theme'

import { t } from '../../i18n/scope/views'
type Rect = { x: number; y: number; w: number; h: number }

type Panel = {
  g: CanvasRenderingContext2D
  t: Theme
  k: number
  base: string
  font: (size: number, weight?: number) => string
  numbers: boolean
}

const TAU = Math.PI * 2

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

function clip(g: CanvasRenderingContext2D, s: string, max: number): string {
  if (g.measureText(s).width <= max) return s
  let out = s
  while (out.length > 1 && g.measureText(`${out}…`).width > max) out = out.slice(0, -1)
  return `${out}…`
}

/** The housing every instrument sits in. */
export function bezel(p: Panel, r: Rect, title: string) {
  const { g, t: th, k } = p
  g.fillStyle = mix(p.base, th.ink, 0.035)
  rrect(g, r.x, r.y, r.w, r.h, 6 * k)
  g.fill()
  g.strokeStyle = mix(p.base, th.ink, 0.11)
  g.lineWidth = 1 * k
  rrect(g, r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1, 6 * k)
  g.stroke()
  if (!title) return
  g.fillStyle = th.dim
  g.font = p.font(8, 700)
  g.fillText(clip(g, title.toUpperCase(), r.w - 14 * k), r.x + 7 * k, r.y + 11 * k)
}

/**
 * A dial: an arc from empty to full, a needle at the reading, and a redline
 * where the number stops being good news.
 */
export function dial(
  p: Panel, r: Rect,
  o: { value: number; max: number; label: string; read: string; tone: string; redline?: number },
) {
  const { g, t: th, k } = p
  const cx = r.x + r.w / 2
  const cy = r.y + r.h * 0.66
  const rad = Math.min(r.w * 0.42, r.h * 0.5)
  const a0 = Math.PI * 0.82
  const a1 = Math.PI * 2.18
  const frac = Math.max(0, Math.min(1, o.max ? o.value / o.max : 0))

  g.lineWidth = Math.max(2, rad * 0.14)
  g.strokeStyle = mix(p.base, th.ink, 0.1)
  g.beginPath()
  g.arc(cx, cy, rad, a0, a1)
  g.stroke()

  if (o.redline !== undefined && o.max) {
    const ra = a0 + (a1 - a0) * Math.min(1, o.redline / o.max)
    g.strokeStyle = mix(p.base, th.lanes[6], 0.34)
    g.beginPath()
    g.arc(cx, cy, rad, ra, a1)
    g.stroke()
  }

  g.strokeStyle = o.tone
  g.lineCap = 'round'
  g.beginPath()
  g.arc(cx, cy, rad, a0, a0 + (a1 - a0) * frac)
  g.stroke()
  g.lineCap = 'butt'

  // Ticks, so the arc has a scale and not just a length.
  for (let i = 0; i <= 8; i++) {
    const a = a0 + ((a1 - a0) * i) / 8
    const inner = rad * 1.16
    const outer = rad * (i % 4 === 0 ? 1.3 : 1.24)
    g.strokeStyle = mix(p.base, th.ink, i % 4 === 0 ? 0.3 : 0.16)
    g.lineWidth = 1 * k
    g.beginPath()
    g.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner)
    g.lineTo(cx + Math.cos(a) * outer, cy + Math.sin(a) * outer)
    g.stroke()
  }

  const na = a0 + (a1 - a0) * frac
  g.strokeStyle = th.ink
  g.lineWidth = 1.4 * k
  g.beginPath()
  g.moveTo(cx, cy)
  g.lineTo(cx + Math.cos(na) * rad * 0.92, cy + Math.sin(na) * rad * 0.92)
  g.stroke()
  g.fillStyle = th.ink
  g.beginPath()
  g.arc(cx, cy, 2 * k, 0, TAU)
  g.fill()

  g.textAlign = 'center'
  g.fillStyle = th.ink
  g.font = p.font(15, 700)
  g.fillText(o.read, cx, cy - rad * 0.28)
  g.fillStyle = th.dim
  g.font = p.font(8, 700)
  g.fillText(clip(g, o.label.toUpperCase(), r.w - 8 * k), cx, r.y + r.h - 3 * k)
  g.textAlign = 'left'
}

/** A bar meter with a scale — how full something is, against its limit. */
export function meter(
  p: Panel, r: Rect,
  o: { value: number; max: number; label: string; read: string; tone: string },
) {
  const { g, t: th, k } = p
  const barH = Math.min(7 * k, r.h * 0.34)
  const y = r.y + r.h - barH - 10 * k
  g.fillStyle = th.dim
  g.font = p.font(8, 700)
  g.fillText(clip(g, o.label.toUpperCase(), r.w * 0.7), r.x, r.y + 8 * k)
  g.textAlign = 'right'
  g.fillStyle = th.ink
  g.font = p.font(11, 700)
  g.fillText(o.read, r.x + r.w, r.y + 9 * k)
  g.textAlign = 'left'

  g.fillStyle = mix(p.base, th.ink, 0.09)
  rrect(g, r.x, y, r.w, barH, barH / 2)
  g.fill()
  const frac = Math.max(0, Math.min(1, o.max ? o.value / o.max : 0))
  if (frac > 0) {
    g.fillStyle = o.tone
    rrect(g, r.x, y, Math.max(barH, r.w * frac), barH, barH / 2)
    g.fill()
  }
  for (let i = 1; i < 5; i++) {
    g.fillStyle = mix(p.base, th.ink, 0.22)
    g.fillRect(r.x + (r.w * i) / 5, y + barH + 2 * k, 1, 3 * k)
  }
}

/** One lamp per thing, lit for the ones that are on. */
export function lamps(
  p: Panel, r: Rect,
  o: { n: number; on: boolean[]; label: string; tone: string },
) {
  const { g, t: th, k } = p
  g.fillStyle = th.dim
  g.font = p.font(8, 700)
  g.fillText(o.label.toUpperCase(), r.x, r.y + 8 * k)
  const lit = o.on.filter(Boolean).length
  g.textAlign = 'right'
  g.fillStyle = lit ? th.ink : th.dim
  g.font = p.font(11, 700)
  g.fillText(`${lit}/${o.n}`, r.x + r.w, r.y + 9 * k)
  g.textAlign = 'left'

  const cols = Math.min(o.n, Math.max(6, Math.floor(r.w / (14 * k))))
  const cell = r.w / cols
  const rows = Math.ceil(o.n / cols)
  const top = r.y + 16 * k
  const rowH = Math.max(6 * k, Math.min(9 * k, (r.h - 18 * k) / Math.max(1, rows)))
  for (let i = 0; i < o.n; i++) {
    const cxp = r.x + (i % cols) * cell + cell / 2
    const cyp = top + Math.floor(i / cols) * rowH + rowH / 2
    const on = o.on[i]
    if (on) {
      g.fillStyle = mix(p.base, o.tone, 0.28)
      g.beginPath()
      g.arc(cxp, cyp, 7 * k, 0, TAU)
      g.fill()
    }
    g.fillStyle = on ? o.tone : mix(p.base, th.ink, 0.16)
    g.beginPath()
    g.arc(cxp, cyp, 3.2 * k, 0, TAU)
    g.fill()
  }
}

/** A number that wants to be read from across the room. */
export function readout(
  p: Panel, r: Rect,
  o: { value: string; label: string; sub?: string; tone?: string; size?: number },
) {
  const { g, t: th, k } = p
  g.fillStyle = th.dim
  g.font = p.font(8, 700)
  g.fillText(clip(g, o.label.toUpperCase(), r.w), r.x, r.y + 8 * k)
  const size = o.size ?? 26
  g.fillStyle = o.tone ?? th.ink
  g.font = p.font(size, 700)
  g.fillText(clip(g, o.value, r.w), r.x, r.y + size * k + 6 * k)
  if (!o.sub) return
  // Right under the number, not at the bottom of whatever box it was given:
  // a caption an inch away from its figure stops being its caption.
  g.fillStyle = th.muted
  g.font = p.font(9, 500)
  g.fillText(clip(g, o.sub, r.w), r.x, r.y + size * k + 19 * k)
}

/** A trace: the whole series faint, the part already run solid. */
export function trace(
  p: Panel, r: Rect,
  o: { series: number[]; now: number; label: string; tone: string; fill?: boolean },
) {
  const { g, t: th, k } = p
  const { series } = o
  if (series.length < 2) return
  const max = Math.max(1, ...series)
  const at = (i: number) => ({
    x: r.x + (i / (series.length - 1)) * r.w,
    y: r.y + r.h - 4 * k - (series[i] / max) * (r.h - 16 * k),
  })
  const line = (to: number, tone: string, fill: boolean) => {
    if (to < 1) return
    g.beginPath()
    g.moveTo(r.x, r.y + r.h - 4 * k)
    for (let i = 0; i <= to; i++) {
      const q = at(i)
      g.lineTo(q.x, q.y)
    }
    if (fill) {
      g.lineTo(at(to).x, r.y + r.h - 4 * k)
      g.closePath()
      g.fillStyle = tone
      g.fill()
      return
    }
    g.strokeStyle = tone
    g.lineWidth = 1.2 * k
    g.stroke()
  }
  // The future is a line, not a fill: a curve that only climbs, filled to
  // its end, is a rectangle — which says nothing and looks like a mistake.
  line(series.length - 1, mix(p.base, th.ink, 0.16), false)
  line(o.now, o.fill === false ? o.tone : mix(p.base, o.tone, 0.75), o.fill !== false)
  const head = at(Math.max(0, o.now))
  g.fillStyle = th.ink
  g.beginPath()
  g.arc(head.x, head.y, 2 * k, 0, TAU)
  g.fill()
  g.fillStyle = th.dim
  g.font = p.font(8, 700)
  g.fillText(o.label.toUpperCase(), r.x, r.y + 8 * k)
}

/** The last few things that happened, newest at the top. */
export function log(
  p: Panel, film: Film, f: Frame, r: Rect, o: { label: string; rows: number },
) {
  const { g, t: th, k } = p
  g.fillStyle = th.dim
  g.font = p.font(8, 700)
  g.fillText(o.label.toUpperCase(), r.x, r.y + 8 * k)

  type Line = { at: number; text: string; tone: string }
  const lines: Line[] = []
  for (const m of film.marks) {
    const at = new Date(m.at).getTime()
    if (at > f.at) continue
    const card = film.byId.get(m.task_id)
    lines.push({
      at,
      text: `${m.kind} · ${card ? card.title : m.task_id}`,
      tone: m.kind === 'evidence' ? th.lanes[2] : th.lanes[3],
    })
  }
  for (const c of film.cards) {
    for (const mv of c.moves) {
      if (mv.status !== 'done') continue
      const at = new Date(mv.at).getTime()
      if (at > f.at) break
      lines.push({ at, text: t('done · {title}', { title: c.title }), tone: th.up })
      break
    }
  }
  lines.sort((a, b) => b.at - a.at)

  const rowH = Math.min(12 * k, (r.h - 16 * k) / o.rows)
  lines.slice(0, o.rows).forEach((ln, i) => {
    const y = r.y + 20 * k + i * rowH
    const fade = 1 - i / (o.rows + 1)
    g.save()
    g.globalAlpha = 0.35 + 0.65 * fade
    g.fillStyle = ln.tone
    g.beginPath()
    g.arc(r.x + 2.5 * k, y - 3 * k, 2 * k, 0, TAU)
    g.fill()
    g.fillStyle = mix(p.base, th.ink, 0.62)
    g.font = p.font(9, 500)
    g.fillText(clip(g, ln.text, r.w - 12 * k), r.x + 9 * k, y)
    g.restore()
  })
}

/* ----------------------------- the readings ---------------------------- */

const HOUR = 3600_000

/** Everything the instruments show, read once per frame. */
export function readings(film: Film, f: Frame) {
  const v = vitalsAt(film, f)
  const day = 24 * HOUR
  const elapsed = Math.max(1, (f.at - film.t0) / day)

  let commits = 0
  let add = 0
  let del = 0
  let recent = 0
  const files = new Set<string>()
  for (const c of film.git?.commits ?? []) {
    const at = new Date(c.at).getTime()
    if (at > f.at) break
    commits++
    add += c.add
    del += c.del
    for (const path of c.touched) files.add(path)
    if (at >= f.at - day) recent++
  }

  // Every card movement so far — the strip counts them, and it must not
  // report the number of cards instead.
  let moves = 0
  for (const h of film.hours) {
    if (h.at > f.at) break
    moves += h.moves
  }

  const awake = new Set(f.awake.map((s) => s.agent_id))
  return {
    moves,
    ...v,
    elapsedDays: elapsed,
    dayOf: Math.floor((f.at - film.t0) / day) + 1,
    days: Math.ceil((film.t1 - film.t0) / day),
    commits,
    add,
    del,
    filesTouched: files.size,
    commitsToday: recent,
    perDay: v.done / elapsed,
    awake: film.agents.map((a) => awake.has(a)),
    live: f.live,
    backlog: f.counts.todo + f.counts.unclassified,
    review: f.counts.review,
  }
}


/**
 * A telemetry strip: one thin trace per reading, stacked, each with its
 * current value at the right. The shape of the last twenty days in a band an
 * inch tall — which is what a panel of them is for.
 */
/**
 * The gutters a strip keeps for its name and its value. The flow underneath
 * has to keep the same ones, or the two plots are different widths and their
 * playheads sit in different places for the same moment.
 */
const STRIP_LABEL_W = 96
const STRIP_READ_W = 48

/**
 * The housing every strip shares: a name in a fixed left gutter, a running
 * total in a fixed right gutter, and a plot box between them. Returns the
 * plot so anything can be drawn inside it — bars, bands, whatever — and still
 * belong to the same panel. Four readings in a column have to be one
 * component wearing different contents, or the odd one out reads as a chart
 * from somewhere else.
 */
function stripFrame(
  p: Panel, r: Rect, o: { label: string; read: string },
): Rect {
  const { g, t: th, k } = p
  const labelW = STRIP_LABEL_W * k
  const readW = STRIP_READ_W * k
  const plot = { x: r.x + labelW, y: r.y, w: r.w - labelW - readW, h: r.h }

  g.fillStyle = th.muted
  g.font = p.font(10, 700)
  g.fillText(clip(g, o.label.toUpperCase(), labelW - 10 * k), r.x, r.y + r.h * 0.62)
  g.textAlign = 'right'
  g.fillStyle = th.ink
  g.font = p.font(12, 700)
  g.fillText(o.read, r.x + r.w, r.y + r.h * 0.66)
  g.textAlign = 'left'

  g.fillStyle = mix(p.base, th.ink, 0.05)
  rrect(g, plot.x, plot.y, plot.w, plot.h, 2 * k)
  g.fill()
  return plot
}

export function strip(
  p: Panel, r: Rect,
  o: {
    series: number[]
    /** Where each sample sits across the film, 0..1. Every panel shares this
     *  axis, or the playheads disagree and nothing lines up. */
    u0: number[]
    u1: number[]
    /** The playhead, in the same 0..1. */
    now: number
    label: string
    read: string
    tone: string
  },
) {
  const { g, t: th, k } = p
  const plot = stripFrame(p, r, { label: o.label, read: o.read })

  const max = Math.max(1, ...o.series)
  for (let i = 0; i < o.series.length; i++) {
    const h = (o.series[i] / max) * (plot.h - 3 * k)
    if (h <= 0) continue
    const xa = plot.x + o.u0[i] * plot.w
    const xb = plot.x + o.u1[i] * plot.w
    g.fillStyle = o.u1[i] <= o.now ? o.tone : mix(p.base, th.ink, 0.1)
    g.fillRect(xa, plot.y + plot.h - h - 1.5 * k, Math.max(0.7, xb - xa), h)
  }
  const hx = plot.x + Math.max(0, Math.min(1, o.now)) * plot.w
  g.fillStyle = th.ink
  g.fillRect(Math.round(hx), plot.y, 1, plot.h)
}


/* ------------------------------- the flow ------------------------------ */

/**
 * The board's statuses are an order, not a set.
 *
 * A card goes unclassified → to do → doing → review → done; that is a scale,
 * and a scale wants one hue getting stronger, not five unrelated ones. Five
 * categorical hues also cost five colours out of seven, which is why every
 * strip on the panel was colliding with a band underneath it: commits were
 * the same green as done, card moves the same amber as doing, agent turns the
 * same cyan as review. One ramp gives the colours back and encodes the thing
 * correctly at the same time — done is the brightest, and watching it fill
 * the block is the point.
 */
const FLOW_STEP: Record<Column, number> = {
  unclassified: 0.34, todo: 0.5, doing: 0.66, review: 0.82, done: 1,
}

const flowTone = (p: Panel, col: Column) => mix(p.base, p.t.up, FLOW_STEP[col])

const flows = new WeakMap<Film, { counts: number[][] }>()

/**
 * The board's whole population, counted by status, once per film hour.
 *
 * Per hour and not per day, because the strips above it are per hour: two
 * readings on one panel have to be sampled on the same grid or they are not
 * comparable, however well their playheads line up. Solved once and cached —
 * a hundred and thirty cards across four hundred hours is not free.
 */
function flowOf(film: Film) {
  const cached = flows.get(film)
  if (cached) return cached
  const counts = film.hours.map((h) => {
    const row = new Array(COLUMNS.length).fill(0)
    for (const card of film.cards) {
      const s = statusAt(card, h.at + HOUR / 2)
      if (s === null) continue
      row[COLUMNS.indexOf(s)]++
    }
    return row
  })
  const out = { counts }
  flows.set(film, out)
  return out
}

/**
 * Cumulative flow: a band per status per day, stacked.
 *
 * The same reading the project's analytics tab calls the river, and the one
 * that actually answers "is this working" — the total is how much the board
 * is carrying, and a middle that keeps fattening is work piling up in front
 * of done rather than passing through it.
 */
export function flow(
  p: Panel, film: Film, f: Frame, r: Rect,
  o: { label: string; read: string; key?: boolean },
) {
  const { g, t: th, k } = p
  const { counts } = flowOf(film)
  const hours = film.hours
  if (hours.length < 2) return

  // The same housing as the strips above: same gutters, same box, same
  // height. Only what is inside the plot is different.
  const plot = stripFrame(p, r, { label: o.label, read: o.read })
  const max = Math.max(1, ...counts.map((row) => row.reduce((a, v) => a + v, 0)))
  const x = (i: number) => plot.x + hours[i].u0 * plot.w
  const nowI = hours.findIndex((h) => h.at > f.at)
  const cut = nowI < 0 ? hours.length - 1 : Math.max(0, nowI - 1)
  const headX = plot.x + Math.min(1, Math.max(0, film.filmAt(f.at))) * plot.w

  const tops = counts.map((row) => {
    const out: number[] = []
    let acc = 0
    for (let s = 0; s < COLUMNS.length; s++) {
      acc += row[s]
      out.push(acc)
    }
    return out
  })

  const draw = (to: number, live: boolean) => {
    for (let s = COLUMNS.length - 1; s >= 0; s--) {
      g.beginPath()
      g.moveTo(x(0), plot.y + plot.h)
      for (let i = 0; i <= to; i++) {
        g.lineTo(x(i), plot.y + plot.h - (tops[i][s] / max) * (plot.h - 2 * k))
      }
      if (live) g.lineTo(headX, plot.y + plot.h - (tops[to][s] / max) * (plot.h - 2 * k))
      g.lineTo(live ? headX : x(to), plot.y + plot.h)
      g.closePath()
      const tone = flowTone(p, COLUMNS[s])
      g.fillStyle = live ? tone : mix(p.base, tone, 0.14)
      g.fill()
      // A hairline of the ground between bands: five steps of one hue need an
      // edge to read as five, however far apart the steps are.
      if (live && s > 0) {
        g.strokeStyle = mix(p.base, p.t.ink, 0.06)
        g.lineWidth = 1 * k
        g.stroke()
      }
    }
  }
  draw(hours.length - 1, false)
  draw(cut, true)

  g.fillStyle = th.ink
  g.fillRect(Math.round(headX), plot.y, 1, plot.h)

  if (o.key === false) return
  // The key rides inside the plot, so the block keeps the strips' height.
  let lx = plot.x + 5 * k
  g.font = p.font(8, 700)
  for (const col of COLUMNS) {
    g.fillStyle = flowTone(p, col)
    rrect(g, lx, plot.y + 5 * k, 5 * k, 5 * k, 1.5 * k)
    g.fill()
    g.fillStyle = mix(p.base, th.ink, 0.5)
    g.fillText(COLUMN_LABEL[col], lx + 7.5 * k, plot.y + 10 * k)
    lx += 7.5 * k + g.measureText(COLUMN_LABEL[col]).width + 9 * k
  }
}
