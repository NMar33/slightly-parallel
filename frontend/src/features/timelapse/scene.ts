/**
 * The parametric renderer — one frame, at any size, in any dress.
 *
 * v01's scene is a fixed 1200×675 composition. This one takes a stage
 * (size, theme, layout, brand) and computes its regions, because a promo
 * cut is the same data wearing different clothes: a square for a feed, a
 * tall one for a phone, a light one for an article.
 *
 * Still pure. `drawFilm(ctx, film, u, stage)` is a function of the film and
 * a position, so the player, the export and the sheet cannot disagree.
 */

import {
  COLUMNS, COLUMN_LABEL, frameAt, vitalsAt,
  type Column, type Film, type Frame, type Placed,
} from './film'
import { pad2 } from '../../utils/dateUtils'
import { faceStack, redactedTitle, type Brand, type Layout } from './brand'
import { drawRiver as drawRiverVariant, type RiverId } from './rivers'
import { groundBase, mix, paintGround, type Theme } from './theme'
import { drawPlate, drawSheet, drawWordmark, plateWidth, sheetInk } from './spcard'

import { locale, t } from '../../i18n/scope/views'
import { monthShort } from '../../lib/months'
export type Comp = { river: boolean; captions: boolean; bookends: boolean }

export type Stage = {
  w: number
  h: number
  theme: Theme
  brand: Brand
  comp: Comp
  logo: HTMLImageElement | null
}

type Rect = { x: number; y: number; w: number; h: number }

const HOUR = 3600_000
const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const ramp = (x: number, a: number, b: number) => clamp01((x - a) / (b - a))

/* ------------------------------ the cut ------------------------------ */

const LEAD = 0.06
const TAIL = 0.26

function position(u: number, bookends: boolean): number {
  if (!bookends) return u
  if (u <= LEAD) return 0
  if (u >= 1 - TAIL) return 1
  return (u - LEAD) / (1 - LEAD - TAIL)
}

const tailPos = (u: number) => (u < 1 - TAIL ? 0 : (u - (1 - TAIL)) / TAIL)
const headAlpha = (u: number) => 1 - ramp(u, LEAD * 0.6, LEAD * 1.15)
const outroAlpha = (u: number) => ramp(tailPos(u), 0.08, 0.2)
const blackAlpha = (u: number) =>
  Math.max(1 - ramp(u, 0, LEAD * 0.45), u < 1 - TAIL ? 0 : ramp(tailPos(u), 0.8, 0.9))

/* ------------------------------ drawing ------------------------------ */

function rrect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2))
  ctx.beginPath()
  ctx.moveTo(x + rr, y)
  ctx.arcTo(x + w, y, x + w, y + h, rr)
  ctx.arcTo(x + w, y + h, x, y + h, rr)
  ctx.arcTo(x, y + h, x, y, rr)
  ctx.arcTo(x, y, x + w, y, rr)
  ctx.closePath()
}

function clip(ctx: CanvasRenderingContext2D, text: string, max: number): string {
  if (ctx.measureText(text).width <= max) return text
  let tv = text
  while (tv.length > 1 && ctx.measureText(`${tv}…`).width > max) tv = tv.slice(0, -1)
  return `${tv}…`
}

const stamp = (at: number) => {
  const d = new Date(at)
  return `${d.getDate()} ${monthShort(d.getMonth())} · ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/* ------------------------------- context ----------------------------- */

type Ctx = {
  g: CanvasRenderingContext2D
  s: Stage
  t: Theme
  b: Brand
  /** Type scale: 1 at 1200×675, growing with the stage's area. */
  k: number
  base: string
  font: (size: number, weight?: number) => string
  name: (agent: string) => string
  title: (card: { title: string }) => string
}

function makeCtx(g: CanvasRenderingContext2D, s: Stage, film: Film): Ctx {
  const k = Math.sqrt((s.w * s.h) / (1200 * 675))
  const stack = faceStack(s.brand.face)
  const order = new Map(film.agents.map((a, i) => [a, `agent ${i + 1}`]))
  return {
    g,
    s,
    t: s.theme,
    b: s.brand,
    k,
    base: groundBase(s.theme.ground),
    font: (size, weight = 400) => `${weight} ${Math.round(size * k)}px ${stack}`,
    name: (agent) => (s.brand.redactAgents ? order.get(agent) ?? t('an agent') : agent),
    title: (card) => (s.brand.redactTitles ? redactedTitle(card.title) : card.title),
  }
}

const displayName = (film: Film, b: Brand) => b.title || film.project

/**
 * A shape is not a size.
 *
 * A square is not a wide frame with more height and a phone is not a narrow
 * one — the reading order changes, so the composition does. Aspect chooses
 * the composition; `layout` only chooses the dress over it.
 */
type Shape = 'wide' | 'square' | 'tall'

export const shapeOf = (w: number, h: number): Shape =>
  w / h > 1.3 ? 'wide' : w / h > 0.8 ? 'square' : 'tall'

const FOLDED: Column[] = []

/* -------------------------------- header ----------------------------- */

function drawMark(c: Ctx, x: number, y: number, size: number, align: 'left' | 'right') {
  const logo = c.s.logo
  if (!logo || !logo.width) return 0
  const w = (size * logo.width) / logo.height
  c.g.drawImage(logo, align === 'left' ? x : x - w, y, w, size)
  return w
}

function drawHeader(
  c: Ctx, film: Film, f: Frame, r: Rect, u: number, big: boolean,
) {
  const { g, t: th, k } = c
  const titleSize = big ? 34 : 21
  g.textBaseline = 'alphabetic'
  let tx = r.x
  if (c.b.spCards) {
    // The brand's own film: the wordmark is the title, and a chosen logo
    // stays out of it.
    drawWordmark(g, r.x, r.y + titleSize * k, titleSize * k, th.ink, sheetInk(c.base).lean)
  } else {
    const mark = c.s.logo ? drawMark(c, r.x, r.y + (big ? 2 : 1) * k, titleSize * k * 1.05, 'left') : 0
    tx = r.x + (mark ? mark + 12 * k : 0)
    g.fillStyle = th.ink
    g.font = c.font(titleSize, 700)
    g.fillText(displayName(film, c.b), tx, r.y + titleSize * k)
  }

  const days = Math.ceil((film.t1 - film.t0) / (24 * HOUR))
  const day = Math.floor((f.at - film.t0) / (24 * HOUR)) + 1
  const folded = FOLDED.length && c.b.numbers
    ? FOLDED.map((col) => `${f.counts[col]} ${COLUMN_LABEL[col]}`).join(' · ')
    : ''
  g.fillStyle = th.muted
  g.font = c.font(big ? 14 : 12, 500)
  g.fillText(
    folded ? t('day {day} of {days} · {folded}', { day, days, folded }) : t('day {day} of {days}', { day, days }),
    tx, r.y + titleSize * k + 18 * k,
  )

  g.textAlign = 'right'
  g.fillStyle = th.ink
  g.font = c.font(big ? 34 : 26, 700)
  g.fillText(stamp(f.at), r.x + r.w, r.y + (big ? 32 : 24) * k)

  if (c.b.numbers) {
    g.fillStyle = th.muted
    g.font = c.font(12, 500)
    const awake = f.awake.length
    g.fillText(
      `${f.live} cards · ${f.counts.done} done${awake ? ` · ${awake} working` : ''}`,
      r.x + r.w,
      r.y + (big ? 54 : 44) * k,
    )
  }
  g.textAlign = 'left'

  const line = r.y + r.h - 1
  g.fillStyle = th.rule
  g.fillRect(r.x, line, r.w, 1)
  g.fillStyle = th.ink
  g.fillRect(r.x, line, r.w * u, 1)
}

/* -------------------------------- board ------------------------------ */

/**
 * Which named cards sit in which rows.
 *
 * The cards that get names are the ones that moved most recently — that part
 * is right. Showing them in that order is not: any card moving re-ranks every
 * row, so a single frame that spans a few board events replaces all the text
 * at once, and a film at ten frames a second reads as flicker rather than as
 * work happening.
 *
 * Ordering the same set by when each card was created instead gives every
 * card a slot it keeps. One card arriving displaces one row; the rest stay
 * where the eye left them.
 */
function keepSlots(items: Placed[]): Placed[] {
  return items.slice().sort((a, b) => (a.card.born < b.card.born ? -1 : a.card.born > b.card.born ? 1 : 0))
}

function cardTone(c: Ctx, lane: string, film: Film): string {
  const i = film.laneOf(lane)
  return i < 0 ? mix(c.base, c.t.ink, 0.34) : c.t.lanes[i % c.t.lanes.length]
}

function drawColumnBox(
  c: Ctx, film: Film, f: Frame, col: Column, r: Rect, named: number, panel: boolean,
) {
  const { g, t: th, k } = c
  const items = f.columns[col]
  if (panel) {
    g.fillStyle = th.panel
    rrect(g, r.x, r.y, r.w, r.h, 8 * k)
    g.fill()
  }
  const px = panel ? 10 * k : 0
  g.fillStyle = col === 'done' ? th.ink : th.muted
  g.font = c.font(11, 600)
  g.fillText(COLUMN_LABEL[col].toUpperCase(), r.x + px, r.y + 20 * k)
  if (c.b.numbers) {
    g.textAlign = 'right'
    g.fillStyle = items.length ? th.ink : th.dim
    g.font = c.font(15, 700)
    g.fillText(String(items.length), r.x + r.w - (panel ? px : 4 * k), r.y + 21 * k)
    g.textAlign = 'left'
  }

  const top = r.y + 34 * k
  const inner = r.w - px * 2
  const head = keepSlots(items.slice(-named))
  const rest = items.slice(0, Math.max(0, items.length - named))
  const ch = 24 * k

  head.forEach((p, i) => {
    const y = top + i * (ch + 5 * k)
    if (y + ch > r.y + r.h - 4 * k) return
    const tone = cardTone(c, p.card.lane, film)
    g.fillStyle = mix(panel ? th.panel : c.base, tone, 0.3)
    rrect(g, r.x + px, y, inner, ch, 4 * k)
    g.fill()
    g.fillStyle = tone
    rrect(g, r.x + px, y, 3 * k, ch, 1.5 * k)
    g.fill()
    const fresh = f.at - p.moved < 4 * HOUR
    g.fillStyle = fresh ? th.ink : mix(panel ? th.panel : c.base, th.ink, 0.7)
    g.font = c.font(10.5, fresh ? 700 : 500)
    g.fillText(clip(g, c.title(p.card), inner - 20 * k), r.x + px + 10 * k, y + 15.5 * k)
  })

  if (!rest.length) return
  let pileTop = top + head.length * (ch + 5 * k)
  if (head.length) {
    pileTop += 9 * k
    g.fillStyle = th.dim
    g.font = c.font(9, 700)
    g.fillText(t('+{n} EARLIER', { n: rest.length }), r.x + px, pileTop)
    pileTop += 8 * k
  }
  const bw = 21 * k
  const bh = 8.5 * k
  const gap = 3.5 * k
  const per = Math.max(1, Math.floor((inner + gap) / (bw + gap)))
  rest.forEach((p, i) => {
    const bx = r.x + px + (i % per) * (bw + gap)
    const by = pileTop + Math.floor(i / per) * (bh + gap)
    if (by + bh > r.y + r.h - 4 * k) return
    g.fillStyle = mix(c.base, cardTone(c, p.card.lane, film), 0.6)
    rrect(g, bx, by, bw, bh, 2 * k)
    g.fill()
  })
}

/**
 * A portrait board stacks its columns as rows.
 *
 * Turning a column on its side is the only way five of them fit a phone
 * frame: the label and the count sit at the top of each band, the newest
 * cards keep their names underneath, and the rest pile up as blocks. Row
 * heights follow what each column holds, so an empty review band does not
 * take the same space as fifty-eight done cards.
 */
function drawBoardRows(c: Ctx, film: Film, f: Frame, r: Rect, panel: boolean): number {
  const { g, t: th, k } = c
  const gap = 8 * k
  const px = panel ? 12 * k : 0
  const inner = r.w - px * 2
  const ch = 22 * k
  const bw = 22 * k
  const bh = 8 * k
  const bg = 3.5 * k
  const per = Math.max(1, Math.floor((inner + bg) / (bw + bg)))
  // A card is a card, not a banner: a full-width row for one title wastes the
  // frame and reads as five headlines. Two or three fit across, so a band
  // shows several at once and the eye takes in a column, not a list.
  const across = inner > 460 * k ? 3 : 2
  const cgap = 6 * k
  const cw = (inner - cgap * (across - 1)) / across
  const NAMED = across * 2

  const need = COLUMNS.map((col) => {
    const n = f.columns[col].length
    const named = Math.min(NAMED, n)
    const lines = Math.ceil(named / across)
    const rest = Math.max(0, n - named)
    return 30 * k + lines * (ch + 4 * k) + (rest ? 12 * k + Math.ceil(rest / per) * (bh + bg) : 0)
  })
  // A band takes what it needs plus a little air, never a fifth of the frame:
  // the leftover belongs to the river below, not to padding inside an empty
  // review band.
  const free = r.h - gap * (COLUMNS.length - 1)
  const total = need.reduce((a, n) => a + n, 0)
  const floorH = 38 * k
  const spare = Math.max(0, free - floorH * COLUMNS.length)
  const heights = need.map((n) =>
    Math.min(n + 55 * k, floorH + (total > 0 ? (n / total) * spare : spare / COLUMNS.length)))

  let y = r.y
  COLUMNS.forEach((col, i) => {
    const h = heights[i]
    const items = f.columns[col]
    if (panel) {
      g.fillStyle = th.panel
      rrect(g, r.x, y, r.w, h, 8 * k)
      g.fill()
    }
    g.fillStyle = col === 'done' ? th.ink : th.muted
    g.font = c.font(10.5, 700)
    g.fillText(COLUMN_LABEL[col].toUpperCase(), r.x + px, y + 18 * k)
    if (c.b.numbers) {
      g.textAlign = 'right'
      g.fillStyle = items.length ? th.ink : th.dim
      g.font = c.font(17, 700)
      g.fillText(String(items.length), r.x + r.w - px, y + 19 * k)
      g.textAlign = 'left'
    }

    const named = keepSlots(items.slice(-NAMED))
    const rest = items.slice(0, Math.max(0, items.length - named.length))
    const top = y + 27 * k
    let lines = 0
    named.forEach((pl, n) => {
      const line = Math.floor(n / across)
      const cx = r.x + px + (n % across) * (cw + cgap)
      const cy = top + line * (ch + 4 * k)
      if (cy + ch > y + h - 4 * k) return
      lines = line + 1
      const tone = cardTone(c, pl.card.lane, film)
      g.fillStyle = mix(panel ? th.panel : c.base, tone, 0.3)
      rrect(g, cx, cy, cw, ch, 4 * k)
      g.fill()
      g.fillStyle = tone
      rrect(g, cx, cy, 3 * k, ch, 1.5 * k)
      g.fill()
      const fresh = f.at - pl.moved < 4 * HOUR
      g.fillStyle = fresh ? th.ink : mix(panel ? th.panel : c.base, th.ink, 0.7)
      g.font = c.font(10.5, fresh ? 700 : 500)
      g.fillText(clip(g, c.title(pl.card), cw - 18 * k), cx + 9 * k, cy + 14.5 * k)
    })

    let cursor = top + lines * (ch + 4 * k)
    if (rest.length) {
      cursor += 4 * k
      rest.forEach((pl, n) => {
        const bx = r.x + px + (n % per) * (bw + bg)
        const by = cursor + Math.floor(n / per) * (bh + bg)
        if (by + bh > y + h - 4 * k) return
        g.fillStyle = mix(c.base, cardTone(c, pl.card.lane, film), 0.6)
        rrect(g, bx, by, bw, bh, 2 * k)
        g.fill()
      })
    }
    y += h + gap
  })
  return y - gap - r.y
}

/**
 * What a square shows instead of the river.
 *
 * There is no room for twenty days of hours in a feed post, and no need:
 * the numbers that move are better company for a board than the shape of
 * the hours behind it. Lead time and weekly landings are the two a board
 * is actually judged on; both roll with the playhead rather than summing
 * the whole run.
 */
function drawMetrics(c: Ctx, film: Film, f: Frame, r: Rect, panel: boolean) {
  const { g, t: th, k } = c
  const v = vitalsAt(film, f)
  if (panel) {
    g.fillStyle = th.panel
    rrect(g, r.x, r.y, r.w, r.h, 8 * k)
    g.fill()
  }
  const px = panel ? 20 * k : 0
  const cells: Array<[string, string, string]> = [
    [String(v.done), 'done', t('cards in done')],
    [String(v.doing), t('in progress'), t('cards in doing')],
    [v.leadDays ? v.leadDays.toFixed(1) : '—', t('lead time'), t('median days, created to done')],
    [String(v.weekly), t('this week'), t('done in the last 7 days')],
    [String(v.agents), 'agents', t('seen so far')],
    [String(v.turns), 'replies', t('so far')],
  ]
  const cols = 3
  const cw = (r.w - px * 2) / cols
  const rowH = 62 * k
  cells.forEach(([value, label, note], i) => {
    const x = r.x + px + (i % cols) * cw
    const y = r.y + 20 * k + Math.floor(i / cols) * rowH
    g.fillStyle = th.ink
    g.font = c.font(38, 700)
    g.fillText(value, x, y + 32 * k)
    g.fillStyle = th.muted
    g.font = c.font(11, 700)
    g.fillText(label.toUpperCase(), x, y + 47 * k)
    g.fillStyle = th.dim
    g.font = c.font(9.5, 500)
    g.fillText(note, x, y + 59 * k)
  })

  // The curve of landings, drawn where the river used to run.
  const top = r.y + 20 * k + 2 * rowH + 10 * k
  const h = r.y + r.h - top - 14 * k
  if (h < 16 * k) return
  const max = Math.max(1, ...v.curve)
  const at = (i: number) => ({
    x: r.x + px + (i / Math.max(1, v.curve.length - 1)) * (r.w - px * 2),
    y: top + h - (v.curve[i] / max) * h,
  })
  const line = (from: number, to: number, tone: string, fill: boolean) => {
    if (to <= from) return
    g.beginPath()
    g.moveTo(at(from).x, top + h)
    for (let i = from; i <= to; i++) {
      const pt = at(i)
      g.lineTo(pt.x, pt.y)
    }
    g.lineTo(at(to).x, top + h)
    g.closePath()
    if (fill) {
      g.fillStyle = tone
      g.fill()
    }
  }
  // The whole curve as a ghost, the reached part solid: the same past/future
  // reading the river uses, so the two panels agree about what has happened.
  line(0, v.curve.length - 1, mix(c.base, th.ink, 0.09), true)
  line(0, v.now, mix(c.base, th.up, 0.75), true)
  g.fillStyle = th.dim
  g.font = c.font(9, 600)
  g.fillText(t('CARDS DONE'), r.x + px, top + 8 * k)
}

/** Returns the height the board actually used, so the river can follow it. */
function drawBoard(
  c: Ctx, film: Film, f: Frame, r: Rect, layout: Layout, shape: Shape,
): number {
  if (r.h < 40) return r.h
  const panel = layout !== 'keynote'
  if (shape === 'tall') return drawBoardRows(c, film, f, r, panel)
  const cols = COLUMNS
  const gap = (layout === 'keynote' ? 30 : 12) * c.k
  const w = (r.w - gap * (cols.length - 1)) / cols.length
  // How many cards keep their names: the column has to be wide enough to
  // read a title and tall enough to hold them. A square has the height a
  // wide frame does not, so it names more of them.
  const byWidth = w > 190 * c.k ? 8 : w > 130 * c.k ? 3 : 0
  const byHeight = Math.floor((r.h - 46 * c.k) / (29 * c.k))
  const named = Math.max(0, Math.min(byWidth, byHeight, shape === 'square' ? 8 : 4))
  cols.forEach((col, i) =>
    drawColumnBox(c, film, f, col, { x: r.x + i * (w + gap), y: r.y, w, h: r.h }, named, panel))
  return r.h
}

/* ------------------------------- caption ----------------------------- */

function drawCaption(c: Ctx, f: Frame, r: Rect, size: number) {
  if (!f.beat) return
  c.g.fillStyle = c.t.ink
  c.g.font = c.font(size, 600)
  c.g.fillText(clip(c.g, f.beat.text, r.w), r.x, r.y + size * c.k)
}

/* ------------------------------- bookends ---------------------------- */

const MONO = 'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace'

/** Mono caps the drawing's way: tracked, small, in the sheet's label ink. */
function sheetLabel(c: Ctx, ink: string) {
  const { g, k } = c
  return (text: string, x: number, y: number, size: number, align: CanvasTextAlign) => {
    g.save()
    g.fillStyle = ink
    g.font = `500 ${Math.round(size * k)}px ${MONO}`
    g.textAlign = align
    g.letterSpacing = `${(1.6 * k).toFixed(1)}px`
    g.fillText(text, x, y)
    g.restore()
  }
}

function spBlock(c: Ctx, film: Film, f: Frame | null): Array<[string, string]> {
  const days = Math.ceil((film.t1 - film.t0) / (24 * HOUR))
  const from = new Date(film.t0), to = new Date(film.t1)
  const d = (x: Date) => x.toISOString().slice(0, 10)
  const rows: Array<[string, string]> = [
    ['PROJECT', displayName(film, c.b).toUpperCase()],
    ['SPAN', `${d(from)} → ${d(to)} · ${days} DAYS`],
    ['CARDS', f ? `${film.cards.length} · ${f.counts.done} DONE` : String(film.cards.length)],
    ['AGENTS', `${film.agents.length} · ${film.sessions.length} SESSIONS`],
  ]
  if (f && (film.stats.turns || f.turnsSeen)) rows.push(['TURNS', String(film.stats.turns || f.turnsSeen)])
  if (film.stats.commits) rows.push(['COMMITS', String(film.stats.commits)])
  return rows
}

function drawSpCard(c: Ctx, film: Film, f: Frame | null, alpha: number, end: boolean) {
  if (alpha <= 0) return
  const { g, s, t: th, k } = c
  g.save()
  g.globalAlpha = alpha
  paintGround(g, th.ground, s.w, s.h)
  const inks = sheetInk(c.base)
  const label = sheetLabel(c, inks.label)
  const tall = s.h > s.w
  const sheet = drawSheet(g, s.w, s.h, k, inks, label, spBlock(c, film, f), {
    y: tall ? s.h * 0.42 : s.h * 0.5,
    size: tall ? (s.w - 80 * k) / 7.6142 : undefined,
    titleBlock: !tall,
    labels: !tall,
  })
  g.textAlign = 'center'
  g.fillStyle = th.muted
  g.font = `500 ${Math.round(12 * k)}px ${MONO}`
  g.letterSpacing = `${(3 * k).toFixed(1)}px`
  const line = end
    ? (c.b.endline || t('A DASHBOARD FOR CODING AGENTS'))
    : (c.b.subtitle || displayName(film, c.b)).toUpperCase()
  g.fillText(line, s.w / 2, sheet.baseline + 110 * k)
  if (tall) {
    // no room for the title block: the numbers go under the line
    let y = sheet.baseline + 160 * k
    for (const [key, value] of spBlock(c, film, f)) {
      label(key, s.w / 2 - 8 * k, y, 9, 'right')
      label(value, s.w / 2 + 8 * k, y, 9, 'left')
      y += 18 * k
    }
  }
  g.restore()
}

function drawTitleCard(c: Ctx, film: Film, alpha: number) {
  if (alpha <= 0) return
  if (c.b.spCards) return drawSpCard(c, film, null, alpha, false)
  const { g, s, t: th, k } = c
  g.save()
  g.globalAlpha = alpha
  paintGround(g, th.ground, s.w, s.h)
  g.textAlign = 'center'

  const y = s.h / 2
  if (s.logo) {
    const size = 96 * k * c.b.logoScale
    const w = (size * s.logo.width) / s.logo.height
    g.drawImage(s.logo, s.w / 2 - w / 2, y - size - 44 * k, w, size)
  }
  g.fillStyle = th.ink
  g.font = c.font(56, 700)
  g.fillText(displayName(film, c.b), s.w / 2, y)

  const days = Math.ceil((film.t1 - film.t0) / (24 * HOUR))
  const line = c.b.subtitle
    || `${days} days · ${film.cards.length} cards · ${film.agents.length} agents · ${film.sessions.length} sessions`
  g.fillStyle = th.muted
  g.font = c.font(16, 500)
  g.fillText(line, s.w / 2, y + 32 * k)
  g.textAlign = 'left'
  g.restore()
}

function drawEndCard(c: Ctx, film: Film, f: Frame, alpha: number) {
  if (alpha <= 0) return
  if (c.b.spCards) return drawSpCard(c, film, f, alpha, true)
  const { g, s, t: th, k } = c
  const st = film.stats
  const days = Math.ceil((film.t1 - film.t0) / (24 * HOUR))
  const cells: Array<[string, string]> = [
    [String(days), 'days'],
    [String(film.cards.length), 'cards'],
    [String(f.counts.done), 'done'],
    [String(film.agents.length), 'agents'],
    [String(st.turns || f.turnsSeen), 'turns'],
  ]
  if (st.commits) cells.push([String(st.commits), 'commits'])

  g.save()
  g.globalAlpha = alpha
  paintGround(g, th.ground, s.w, s.h)
  g.textAlign = 'center'

  const wide = s.w >= s.h
  const perRow = wide ? cells.length : 3
  const cw = Math.min(168 * k, (s.w - 48 * k) / perRow)
  const rows = Math.ceil(cells.length / perRow)
  const blockH = rows * 74 * k
  let y = s.h / 2 - blockH / 2

  if (s.logo) {
    const size = 54 * k * c.b.logoScale
    const w = (size * s.logo.width) / s.logo.height
    g.drawImage(s.logo, s.w / 2 - w / 2, y - 108 * k, w, size)
  }
  g.fillStyle = th.ink
  g.font = c.font(32, 700)
  g.fillText(displayName(film, c.b), s.w / 2, y - 34 * k)

  cells.forEach(([value, label], i) => {
    const row = Math.floor(i / perRow)
    const inRow = Math.min(perRow, cells.length - row * perRow)
    const x = s.w / 2 + (i % perRow) * cw - ((inRow - 1) * cw) / 2
    const yy = y + row * 74 * k
    g.fillStyle = th.ink
    g.font = c.font(44, 700)
    g.fillText(value, x, yy + 44 * k)
    g.fillStyle = th.muted
    g.font = c.font(11, 700)
    g.fillText(label.toUpperCase(), x, yy + 64 * k)
  })

  y += blockH + 26 * k
  if (st.lines_add) {
    const n = (v: number) => v.toLocaleString(locale())
    g.fillStyle = th.muted
    g.font = c.font(15, 500)
    g.fillText(t('+{n} / −{n2} lines across {n3} files', { n: n(st.lines_add), n2: n(st.lines_del ?? 0), n3: n(st.files ?? 0) }), s.w / 2, y)
    y += 34 * k
  }
  g.fillStyle = th.dim
  g.font = c.font(12, 500)
  g.fillText(c.b.endline || t('counted from the project record'), s.w / 2, y)
  g.textAlign = 'left'
  g.restore()
}

/* -------------------------------- extras ----------------------------- */

let grainTile: HTMLCanvasElement | null = null

function grain(c: Ctx) {
  if (!c.b.grain) return
  if (!grainTile) {
    const tile = document.createElement('canvas')
    tile.width = 128
    tile.height = 128
    const tg = tile.getContext('2d')
    if (tg) {
      const img = tg.createImageData(128, 128)
      for (let i = 0; i < img.data.length; i += 4) {
        const v = 118 + Math.random() * 24
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v
        img.data[i + 3] = 255
      }
      tg.putImageData(img, 0, 0)
    }
    grainTile = tile
  }
  const p = c.g.createPattern(grainTile, 'repeat')
  if (!p) return
  c.g.save()
  c.g.globalAlpha = 0.05
  c.g.globalCompositeOperation = 'overlay'
  c.g.fillStyle = p
  c.g.fillRect(0, 0, c.s.w, c.s.h)
  c.g.restore()
}

function watermark(c: Ctx, film: Film) {
  if (!c.b.watermark) return
  const { g, s, t: th, k } = c
  const pad = 20 * k
  g.save()
  g.globalAlpha = 0.55
  g.textAlign = 'right'
  let x = s.w - pad
  if (c.b.spCards) {
    // The brand's own film: the monogram alone in the corner, no name beside it.
    const h = 22 * k * c.b.logoScale
    const w = plateWidth(h)
    g.globalAlpha = 0.85
    drawPlate(g, x - w, s.h - pad - h, h, sheetInk(c.base).lean)
    g.restore()
    return
  }
  if (s.logo) {
    const size = 20 * k * c.b.logoScale
    const w = (size * s.logo.width) / s.logo.height
    g.drawImage(s.logo, x - w, s.h - pad - size, w, size)
    x -= w + 8 * k
  }
  g.fillStyle = th.muted
  g.font = c.font(11, 600)
  g.fillText(displayName(film, c.b), x, s.h - pad - 5 * k)
  g.textAlign = 'left'
  g.restore()
}

/* ------------------------------- regions ----------------------------- */

/**
 * How a frame divides.
 *
 * Shares by shape first, then by layout: a wide frame gives the river a
 * quarter, a phone gives it two thirds because the river runs down it.
 * `layout` moves the shares — air for keynote, the river as hero for
 * poster — but never changes which composition is drawn.
 */
const SHARES: Record<Shape, Record<Layout, { head: number; river: number }>> = {
  wide: {
    board: { head: 0.11, river: 0.252 },
    keynote: { head: 0.142, river: 0.17 },
    poster: { head: 0.11, river: 0.42 },
  },
  square: {
    board: { head: 0.088, river: 0.27 },
    keynote: { head: 0.115, river: 0.23 },
    poster: { head: 0.088, river: 0.34 },
  },
  tall: {
    // Only a floor here: the bands take what they hold and hand the rest to
    // the river, which is measured rather than guessed (see `drawFilm`).
    board: { head: 0.062, river: 0.2 },
    keynote: { head: 0.082, river: 0.16 },
    poster: { head: 0.062, river: 0.3 },
  },
}

function regions(s: Stage, k: number, shape: Shape) {
  const pad = (s.brand.layout === 'keynote' ? 44 : 28) * k
  const w = s.w - pad * 2
  const share = SHARES[shape][s.brand.layout]
  const headH = s.h * share.head
  // A constellation is not a strip: it needs room in both directions or the
  // layout it solved for cannot be seen. Everything else keeps its share.
  // The bands that draw a picture rather than a strip need room in both
  // directions; the flight deck needs a little more again, because it is two
  // pictures side by side.
  const DEEP: Record<string, number> = { graph: 0.6, cockpit: 0.62, console: 0.62, telemetry: 0.62 }
  const deep = Math.max(share.river, DEEP[s.brand.band] ?? 0)
  const riverH = s.comp.river ? s.h * deep : 0
  const capSize = shape === 'wide' ? 15 : shape === 'square' ? 19 : 14
  const capH = s.comp.captions ? (capSize + 14) * k : 0

  const head = { x: pad, y: pad * 0.6, w, h: headH }
  const boardTop = head.y + head.h + 14 * k
  let boardH = Math.max(50 * k, s.h - boardTop - riverH - capH - pad * 0.6)
  let riverTop = s.h - riverH - pad * 0.6
  if (shape === 'square') {
    // Five columns in a square do not need six hundred pixels of height. Cap
    // the board and let the vitals take the rest — they are the reason the
    // square exists.
    boardH = Math.min(boardH, s.h * 0.42)
    riverTop = boardTop + boardH + capH + 16 * k
  }
  return {
    head,
    board: { x: pad, y: boardTop, w, h: boardH },
    cap: { x: pad, y: boardTop + boardH + 6 * k, w, h: capH },
    river: { x: pad, y: riverTop, w, h: Math.max(0, s.h - riverTop - pad * 0.6) },
    capSize,
  }
}

/* -------------------------------- frame ------------------------------ */

export function drawFilm(
  ctx: CanvasRenderingContext2D, film: Film, u: number, stage: Stage,
): Frame {
  const c = makeCtx(ctx, stage, film)
  const shape = shapeOf(stage.w, stage.h)
  const pos = position(u, stage.comp.bookends)
  const f = frameAt(film, film.wallAt(pos))
  const r = regions(stage, c.k, shape)

  paintGround(ctx, stage.theme.ground, stage.w, stage.h)
  ctx.textBaseline = 'alphabetic'
  drawHeader(c, film, f, r.head, pos, stage.brand.layout === 'keynote')
  const used = drawBoard(c, film, f, r.board, stage.brand.layout, shape)
  if (stage.comp.captions) drawCaption(c, f, { ...r.cap, y: r.board.y + used + 6 * c.k }, r.capSize)
  if (stage.comp.river) {
    const labels = stage.brand.layout !== 'keynote'
    // A phone's bands take only what they hold, so the river starts where the
    // board actually ended rather than at a share guessed in advance — no hole
    // in the middle of the frame, and no comb stretched to fill one.
    // …and it stays a strip: hours drawn much taller than they are wide turn
    // the river into a comb, so the bands keep whatever is left over.
    const top = shape === 'tall'
      ? Math.max(r.board.y + used + r.cap.h + 22 * c.k, r.river.y + r.river.h - stage.w * 0.44)
      : r.river.y
    const box = { ...r.river, y: top, h: Math.max(0, r.river.y + r.river.h - top) }
    if (shape === 'square' && stage.brand.band === 'vitals') {
      drawMetrics(c, film, f, r.river, labels)
    } else {
      drawRiverVariant(
        stage.brand.band as RiverId,
        {
          g: ctx, t: stage.theme, k: c.k, base: c.base,
          font: c.font, name: c.name, numbers: stage.brand.numbers,
        },
        film, f, box, pos, labels,
      )
    }
  }
  watermark(c, film)
  grain(c)

  if (!stage.comp.bookends) return f
  drawTitleCard(c, film, headAlpha(u))
  drawEndCard(c, film, f, outroAlpha(u))
  const black = blackAlpha(u)
  if (black > 0) {
    ctx.save()
    ctx.globalAlpha = black
    ctx.fillStyle = '#000000'
    ctx.fillRect(0, 0, stage.w, stage.h)
    ctx.restore()
  }
  return f
}
