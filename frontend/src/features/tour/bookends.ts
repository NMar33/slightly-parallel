/**
 * The opening and the closing card, in several hands.
 *
 * A tour opens on a card and closes on one, and the card is where the
 * brand lives: the wordmark from its outlines, the construction drawing,
 * the s∥p plate, the two stems — the same shapes as brand/kit, drawn here
 * without a font or a file. Each hand is one function; the script names
 * the one it wants, and the studio shows them all as thumbnails.
 *
 * Every line of text is fitted and wrapped before it is drawn, so a long
 * subtitle or closing line steps down a size and takes another line rather
 * than running off the stage.
 */

import { SP_COLOURS, SP_LEAN_DEG, SP_METRICS, SP_WORDMARK_WIDTH } from '../timelapse/spmark'
import { drawPlate, drawSheet, drawWordmark, plateWidth, sheetInk, type SheetInk } from '../timelapse/spcard'
import type { Stage } from './scene'
import {
  DEFAULT_ENDING, DEFAULT_OPENING, clamp, duration, ease, live,
  type Ending, type Opening, type Script,
} from './script'
import { fitSize, lines } from './words'
import { YARD_SECONDS, drawYard } from './yard'

const MONO = 'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace'

const font = (stage: Stage, size: number, weight = 400) => `${weight} ${size}px ${stage.face}`

const groundOf = (stage: Stage) =>
  (typeof stage.theme.ground === 'string' ? stage.theme.ground : stage.theme.ground.to)

/** The scale every size here is written in: 1 on a 1200×675 stage. */
const scaleOf = (stage: Stage) => Math.sqrt((stage.w * stage.h) / (1200 * 675))

/** Arrive, hold, leave — the card is never mid-fade for long. */
const openAlpha = (u: number) => clamp(u / 0.18) * (1 - clamp((u - 0.86) / 0.14))
/** Held, then gone: the last thing a reader sees is the line, not a fade. */
const endAlpha = (u: number) => clamp(u / 0.14) * (1 - clamp((u - 0.72) / 0.28))

/** The leaning l arrives upright and settles at the brand's angle. */
const leanAt = (u: number) => SP_LEAN_DEG * ease(clamp((u - 0.12) / 0.48))

type Block = { size: number; rows: string[]; h: number }

/**
 * `text` at the largest size from `hi` down to `lo` that fits `n` lines of
 * `max` px, and the height those lines take at `leading`.
 */
function fit(
  g: CanvasRenderingContext2D, stage: Stage, text: string, max: number, n: number,
  hi: number, lo: number, weight: number, leading: number, face = stage.face,
): Block {
  if (!text.trim()) return { size: hi, rows: [], h: 0 }
  const size = fitSize(g, text, max, n, hi, lo, weight, face)
  g.font = `${weight} ${size}px ${face}`
  const rows = lines(g, text, max, n)
  return { size, rows, h: rows.length * size * leading }
}

/** Draws a fitted block with its first baseline at `y`; returns the baseline after it. */
function put(
  g: CanvasRenderingContext2D, stage: Stage, b: Block, x: number, y: number,
  weight: number, colour: string, align: CanvasTextAlign, leading: number, face = stage.face,
): number {
  g.save()
  g.font = `${weight} ${b.size}px ${face}`
  g.fillStyle = colour
  g.textAlign = align
  let yy = y
  for (const row of b.rows) {
    g.fillText(row, x, yy)
    yy += b.size * leading
  }
  g.restore()
  return yy
}

/** A small capital label, spaced out, in mono. */
function caps(
  g: CanvasRenderingContext2D, k: number, text: string, x: number, y: number,
  size: number, colour: string, align: CanvasTextAlign, spacing = 1.6,
) {
  g.save()
  g.fillStyle = colour
  g.font = `500 ${Math.round(size * k)}px ${MONO}`
  g.textAlign = align
  g.letterSpacing = `${(spacing * k).toFixed(1)}px`
  g.fillText(text.toUpperCase(), x, y)
  g.restore()
}

/** The drawing's labels, the sheet's way. */
const labeller = (g: CanvasRenderingContext2D, k: number, ink: string) =>
  (text: string, x: number, y: number, size: number, align: CanvasTextAlign) =>
    caps(g, k, text, x, y, size, ink, align)

/** `text` cut to one line of `max` px in the label font. */
function short(g: CanvasRenderingContext2D, k: number, text: string, max: number): string {
  g.save()
  g.font = `500 ${Math.round(9 * k)}px ${MONO}`
  const [row] = lines(g, text, max, 1)
  g.restore()
  return row ?? ''
}

const rule = (g: CanvasRenderingContext2D, x1: number, x2: number, y: number, colour: string, w: number) => {
  g.save()
  g.strokeStyle = colour
  g.lineWidth = w
  g.beginPath(); g.moveTo(x1, y); g.lineTo(x2, y); g.stroke()
  g.restore()
}

const nameOf = (s: Script) => s.title || s.name

/**
 * What this tour is called, for a card that already carries the brand: the
 * title, unless it is the product's name (the README cuts), then the name.
 */
const tourName = (s: Script) => (s.title && s.title.toLowerCase() !== 'slightly parallel' ? s.title : s.name)

/** What the title block says about this tour. */
function block(g: CanvasRenderingContext2D, k: number, s: Script, end: boolean): Array<[string, string]> {
  const n = live(s).length
  const rows: Array<[string, string]> = [['TOUR', short(g, k, tourName(s), 200 * k)]]
  if (s.section && !end) rows.push(['SECTION', short(g, k, s.section, 200 * k)])
  rows.push(['BEATS', String(n)], ['RUNS', `${Math.round(duration(s))} S`])
  if (end) rows.push(['MADE WITH', 'SLIGHTLY PARALLEL'])
  return rows
}

/** The plate reads on any ground; on a dark one a hairline gives it an edge. */
function plate(g: CanvasRenderingContext2D, x: number, y: number, h: number, inks: SheetInk, dark: boolean) {
  const w = drawPlate(g, x, y, h, inks.lean)
  if (dark) {
    g.save()
    g.strokeStyle = inks.hair
    g.lineWidth = 1
    const r = w * 0.18
    g.beginPath()
    g.moveTo(x + r, y)
    g.arcTo(x + w, y, x + w, y + h, r)
    g.arcTo(x + w, y + h, x, y + h, r)
    g.arcTo(x, y + h, x, y, r)
    g.arcTo(x, y, x + w, y, r)
    g.closePath()
    g.stroke()
    g.restore()
  }
  return w
}

/* ------------------------------ openings ------------------------------ */

type Hand = (g: CanvasRenderingContext2D, stage: Stage, s: Script, u: number) => void

/** The name and the subtitle, centred, in the tour's own typeface. */
const openPlain: Hand = (g, stage, s) => {
  const t = stage.theme, k = scaleOf(stage)
  const title = fit(g, stage, nameOf(s), stage.w * 0.82, 2, 74 * k, 40 * k, 700, 1.1)
  const sub = fit(g, stage, s.subtitle, stage.w * 0.66, 3, 26 * k, 18 * k, 400, 1.45)
  const gap = sub.rows.length ? 24 * k : 0
  const top = (stage.h - (title.h + gap + sub.h)) / 2
  rule(g, stage.w / 2 - 60 * k, stage.w / 2 + 60 * k, top - 10 * k, t.lanes[0], Math.max(2, 3 * k))
  let y = put(g, stage, title, stage.w / 2, top + title.size, 700, t.ink, 'center', 1.1)
  y += gap - title.size * 0.1 + sub.size * 0.6
  put(g, stage, sub, stage.w / 2, y, 400, t.muted, 'center', 1.45)
}

/** The wordmark, leaning in; the subtitle under it. */
const openWordmark: Hand = (g, stage, s, u) => {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const tall = stage.h > stage.w
  const size = tall ? (stage.w - 80 * k) / SP_WORDMARK_WIDTH : Math.min((stage.w - 240 * k) / SP_WORDMARK_WIDTH, 112 * k)
  const width = SP_WORDMARK_WIDTH * size
  const sub = fit(g, stage, s.subtitle, stage.w * 0.62, 3, 22 * k, 16 * k, 400, 1.45)
  const gap = sub.rows.length ? 56 * k : 0
  const total = size * (SP_METRICS.asc - SP_METRICS.desc) + gap + sub.h
  const baseline = (stage.h - total) / 2 + size * SP_METRICS.asc
  drawWordmark(g, (stage.w - width) / 2, baseline, size, inks.ink, inks.lean, leanAt(u))
  put(g, stage, sub, stage.w / 2, baseline - size * SP_METRICS.desc + gap, 400, t.muted, 'center', 1.45)
}

/** The construction drawing: the wordmark with its lines and a title block. */
function sheet(g: CanvasRenderingContext2D, stage: Stage, s: Script, line: string, end: boolean) {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const tall = stage.h > stage.w
  const rows = block(g, k, s, end)
  const drawn = drawSheet(g, stage.w, stage.h, k, inks, labeller(g, k, inks.label), rows, {
    y: tall ? stage.h * 0.42 : stage.h * 0.5,
    size: tall ? (stage.w - 80 * k) / 7.6142 : undefined,
    titleBlock: !tall,
    labels: !tall,
  })
  g.save()
  // Set before measuring: the spacing is a third of each letter's width.
  g.letterSpacing = `${(3 * k).toFixed(1)}px`
  const under = fit(g, stage, line.toUpperCase(), stage.w * 0.8, 2, 12 * k, 10 * k, 500, 1.7, MONO)
  let y = put(g, stage, under, stage.w / 2, drawn.baseline + 110 * k, 500, t.muted, 'center', 1.7, MONO)
  g.restore()
  if (tall) {
    // no room for the title block: its rows go under the line
    y += 24 * k
    for (const [key, value] of rows) {
      caps(g, k, key, stage.w / 2 - 8 * k, y, 9, inks.label, 'right')
      caps(g, k, value, stage.w / 2 + 8 * k, y, 9, inks.label, 'left')
      y += 18 * k
    }
  }
}

const openSheet: Hand = (g, stage, s) => sheet(g, stage, s, s.subtitle, false)

/** An article's chapter opening: kicker, headline, standfirst, left aligned. */
const openChapter: Hand = (g, stage, s) => {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const x = stage.w * 0.08, width = stage.w * 0.84
  const kick = s.section ? `Slightly Parallel · ${s.section}` : 'Slightly Parallel'
  const title = fit(g, stage, tourName(s), width, 3, 80 * k, 40 * k, 700, 1.08)
  const sub = fit(g, stage, s.subtitle, Math.min(width, 760 * k), 3, 24 * k, 17 * k, 400, 1.45)
  const kickH = 13 * k * 2.6
  const gap = sub.rows.length ? 14 * k : 0
  const top = (stage.h - (kickH + title.h + gap + sub.h)) / 2
  caps(g, k, kick, x, top + 13 * k, 13, inks.lean, 'left', 2.2)
  rule(g, x, x + 48 * k, top + 13 * k * 1.7, inks.lean, Math.max(2, 3 * k))
  let y = put(g, stage, title, x, top + kickH + title.size * 0.95, 700, t.ink, 'left', 1.08)
  y += gap - title.size * 0.13 + sub.size * 0.6
  put(g, stage, sub, x, y, 400, t.muted, 'left', 1.45)
}

/** The s∥p plate, the tour's name and the subtitle under it. */
const openPlate: Hand = (g, stage, s) => {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const dark = inks.ink === SP_COLOURS.paper
  const ph = 112 * k
  const title = fit(g, stage, tourName(s), stage.w * 0.78, 2, 50 * k, 30 * k, 700, 1.12)
  const sub = fit(g, stage, s.subtitle, stage.w * 0.62, 3, 22 * k, 16 * k, 400, 1.45)
  const gapA = 48 * k, gapB = sub.rows.length ? 20 * k : 0
  const top = (stage.h - (ph + gapA + title.h + gapB + sub.h)) / 2
  plate(g, (stage.w - plateWidth(ph)) / 2, top, ph, inks, dark)
  let y = put(g, stage, title, stage.w / 2, top + ph + gapA + title.size * 0.9, 700, t.ink, 'center', 1.12)
  y += gapB - title.size * 0.2 + sub.size * 0.6
  put(g, stage, sub, stage.w / 2, y, 400, t.muted, 'center', 1.45)
}

/** The mark alone — two stems, the second leaning in — then the name. */
const openStems: Hand = (g, stage, s, u) => {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const H = stage.h * 0.3
  const sw = H * 0.12, gap = H * 0.1
  const wm = 40 * k
  const sub = fit(g, stage, s.subtitle, stage.w * 0.6, 2, 17 * k, 14 * k, 400, 1.45)
  const total = H + 70 * k + wm * (SP_METRICS.asc - SP_METRICS.desc) + (sub.rows.length ? 30 * k + sub.h : 0)
  const top = (stage.h - total) / 2
  const cx = stage.w / 2
  const radius = sw / 2
  const stem = (x: number) => {
    g.beginPath()
    g.moveTo(x + radius, top)
    g.arcTo(x + sw, top, x + sw, top + H, radius)
    g.arcTo(x + sw, top + H, x, top + H, radius)
    g.arcTo(x, top + H, x, top, radius)
    g.arcTo(x, top, x + sw, top, radius)
    g.closePath()
    g.fill()
  }
  g.save()
  g.fillStyle = inks.ink
  stem(cx - gap / 2 - sw)
  // the second stem turns about its foot, from upright to the brand's angle
  g.translate(cx + gap / 2 + sw / 2, top + H)
  g.rotate((-leanAt(u) * Math.PI) / 180)
  g.translate(-(cx + gap / 2 + sw / 2), -(top + H))
  g.fillStyle = inks.lean
  stem(cx + gap / 2)
  g.restore()
  // the name arrives once the stem has settled
  const arrive = clamp((u - 0.42) / 0.25)
  if (arrive <= 0) return
  g.save()
  g.globalAlpha *= arrive
  const width = SP_WORDMARK_WIDTH * wm
  const baseline = top + H + 70 * k + wm * SP_METRICS.asc
  drawWordmark(g, cx - width / 2, baseline, wm, inks.ink, inks.lean)
  put(g, stage, sub, cx, baseline - wm * SP_METRICS.desc + 30 * k, 400, t.muted, 'center', 1.45)
  g.restore()
}

/* ------------------------------- endings ------------------------------ */

/** The name and the closing line, centred. */
const endPlain: Hand = (g, stage, s) => {
  const t = stage.theme, k = scaleOf(stage)
  const title = fit(g, stage, nameOf(s), stage.w * 0.82, 2, 60 * k, 36 * k, 700, 1.1)
  const line = fit(g, stage, s.endline, stage.w * 0.72, 3, 30 * k, 20 * k, 400, 1.45)
  const gap = line.rows.length ? 28 * k : 0
  const top = (stage.h - (title.h + gap + line.h)) / 2
  let y = put(g, stage, title, stage.w / 2, top + title.size, 700, t.ink, 'center', 1.1)
  y += gap - title.size * 0.1 + line.size * 0.6
  put(g, stage, line, stage.w / 2, y, 400, t.muted, 'center', 1.45)
}

/** The wordmark and the closing line under it. */
const endWordmark: Hand = (g, stage, s) => {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const tall = stage.h > stage.w
  const size = tall ? (stage.w - 80 * k) / SP_WORDMARK_WIDTH : Math.min((stage.w - 300 * k) / SP_WORDMARK_WIDTH, 96 * k)
  const width = SP_WORDMARK_WIDTH * size
  const line = fit(g, stage, s.endline, stage.w * 0.66, 3, 24 * k, 17 * k, 400, 1.45)
  const gap = line.rows.length ? 52 * k : 0
  const total = size * (SP_METRICS.asc - SP_METRICS.desc) + gap + line.h
  const baseline = (stage.h - total) / 2 + size * SP_METRICS.asc
  drawWordmark(g, (stage.w - width) / 2, baseline, size, inks.ink, inks.lean)
  put(g, stage, line, stage.w / 2, baseline - size * SP_METRICS.desc + gap, 400, t.muted, 'center', 1.45)
}

const endSheet: Hand = (g, stage, s) => sheet(g, stage, s, s.endline, true)

/** The s∥p plate, the closing line, the name as a label. */
const endPlate: Hand = (g, stage, s) => {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const dark = inks.ink === SP_COLOURS.paper
  const ph = 104 * k
  const line = fit(g, stage, s.endline, stage.w * 0.7, 3, 28 * k, 18 * k, 500, 1.45)
  const gapA = line.rows.length ? 48 * k : 0
  const total = ph + gapA + line.h + 40 * k
  const top = (stage.h - total) / 2
  plate(g, (stage.w - plateWidth(ph)) / 2, top, ph, inks, dark)
  let y = top + ph + gapA + line.size * 0.9
  y = put(g, stage, line, stage.w / 2, y, 500, t.ink, 'center', 1.45)
  caps(g, k, 'Slightly Parallel', stage.w / 2, y - line.size * 0.4 + 30 * k, 11, t.muted, 'center', 3)
}

/** The steps of this tour as a list; the name in the corner. */
const endRecap: Hand = (g, stage, s) => {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const x = stage.w * 0.08, width = stage.w * 0.84
  const beats = live(s)
  const most = stage.h > stage.w ? 8 : 7
  const shown = beats.length > most ? beats.slice(0, most - 1) : beats
  const rest = beats.length - shown.length
  const size = Math.min(26 * k, (stage.h * 0.56) / ((shown.length + (rest ? 1 : 0)) * 1.7))
  const top = stage.h * 0.16
  caps(g, k, `In this tour · ${tourName(s)}`, x, top, 12, inks.lean, 'left', 2.2)
  rule(g, x, x + 48 * k, top + 12 * k, inks.lean, Math.max(2, 3 * k))
  g.save()
  g.font = font(stage, size, 500)
  let y = top + 12 * k + size * 1.9
  const numW = size * 1.8
  shown.forEach((b, i) => {
    g.fillStyle = t.muted
    g.textAlign = 'left'
    g.font = `500 ${Math.round(size * 0.55)}px ${MONO}`
    g.fillText(String(i + 1).padStart(2, '0'), x, y)
    g.font = font(stage, size, 500)
    g.fillStyle = t.ink
    g.fillText(lines(g, b.title, width - numW, 1)[0] ?? '', x + numW, y)
    y += size * 1.7
  })
  if (rest) {
    g.fillStyle = t.muted
    g.font = font(stage, size * 0.8, 400)
    g.fillText(`and ${rest} more`, x + numW, y)
  }
  g.restore()
  // the name, small, at the foot; the closing line beside it
  const wm = 18 * k
  const wmW = SP_WORDMARK_WIDTH * wm
  const foot = stage.h * 0.87
  rule(g, x, x + width, foot - wm * 1.4, t.rule, 1)
  drawWordmark(g, x + width - wmW, foot, wm, inks.ink, inks.lean)
  const line = fit(g, stage, s.endline, width - wmW - 40 * k, 1, 13 * k, 11 * k, 400, 1.3)
  put(g, stage, line, x, foot, 400, t.muted, 'left', 1.3)
}

/** The closing line as the statement; the name small under it. */
const endQuote: Hand = (g, stage, s) => {
  const t = stage.theme, k = scaleOf(stage)
  const inks = sheetInk(groundOf(stage))
  const x = stage.w * 0.1, width = stage.w * 0.8
  const line = fit(g, stage, s.endline || nameOf(s), width, 4, 46 * k, 26 * k, 650, 1.2)
  const wm = 22 * k
  const total = line.h + 44 * k + wm * (SP_METRICS.asc - SP_METRICS.desc)
  const top = (stage.h - total) / 2
  rule(g, x, x + 48 * k, top - 18 * k, inks.lean, Math.max(2, 3 * k))
  const y = put(g, stage, line, x, top + line.size * 0.95, 650, t.ink, 'left', 1.2)
  drawWordmark(g, x, y - line.size * 0.25 + 44 * k + wm * SP_METRICS.asc, wm, inks.ink, inks.lean)
}

/**
 * The product's intro (brand/video/intro-yard.html) across the lead: the
 * yard, the train, the drawing of the name. It paints the whole stage and
 * fades in and out on its own, so it is drawn at full strength.
 */
const openYard: Hand = (g, stage, _s, u) => drawYard(g, stage.w, stage.h, u * YARD_SECONDS)

const OPEN: Record<Opening, Hand> = {
  plain: openPlain, wordmark: openWordmark, sheet: openSheet, chapter: openChapter, plate: openPlate, stems: openStems,
  yard: openYard,
}
const END: Record<Ending, Hand> = {
  plain: endPlain, wordmark: endWordmark, sheet: endSheet, plate: endPlate, recap: endRecap, quote: endQuote,
}

export const openingOf = (s: Script): Opening => (s.opening && OPEN[s.opening] ? s.opening : DEFAULT_OPENING)
export const endingOf = (s: Script): Ending => (s.ending && END[s.ending] ? s.ending : DEFAULT_ENDING)

/** The opening card at `u` of the lead, 0..1, over a ground already painted. */
export function drawOpening(g: CanvasRenderingContext2D, stage: Stage, s: Script, u: number) {
  const alpha = openingOf(s) === 'yard' ? 1 : openAlpha(u)
  if (alpha <= 0) return
  g.save()
  g.globalAlpha = alpha
  g.textAlign = 'left'
  OPEN[openingOf(s)](g, stage, s, u)
  g.restore()
}

/** The closing card at `u` of the tail, 0..1. */
export function drawEnding(g: CanvasRenderingContext2D, stage: Stage, s: Script, u: number) {
  const alpha = endAlpha(u)
  if (alpha <= 0) return
  g.save()
  g.globalAlpha = alpha
  g.textAlign = 'left'
  END[endingOf(s)](g, stage, s, u)
  g.restore()
}
