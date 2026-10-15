/**
 * The Slightly Parallel bookends: the wordmark inside its construction
 * drawing — ascender, x-height, baseline, descender, the 5° arc at the
 * leaning l, a title block — drawn from outlines on the film's own ground.
 * The same drawing is brand/kit/files/drawing-dark.svg; here it carries the
 * project's name and numbers in the title block.
 */
import {
  SP_COLOURS, SP_LEAN_DEG, SP_LEAN_INDEX, SP_METRICS, SP_P, SP_S, SP_WORDMARK, SP_WORDMARK_WIDTH,
} from './spmark'

export type SheetInk = { ink: string; lean: string; hair: string; label: string }

/** Inks for the drawing on a ground: paper ink on a dark ground, ink on a light one. */
export function sheetInk(groundHex: string): SheetInk {
  const v = [1, 3, 5].map((i) => parseInt(groundHex.slice(i, i + 2), 16))
  const light = (v[0] * 299 + v[1] * 587 + v[2] * 114) / 1000 > 128
  return light
    ? { ink: SP_COLOURS.ink, lean: SP_COLOURS.rust, hair: SP_COLOURS.hair, label: SP_COLOURS.label }
    : { ink: SP_COLOURS.paper, lean: SP_COLOURS.rustOnDark, hair: SP_COLOURS.hairDark, label: SP_COLOURS.labelDark }
}

const paths = new Map<string, Path2D>()
const path2d = (d: string): Path2D => {
  let p = paths.get(d)
  if (!p) { p = new Path2D(d); paths.set(d, p) }
  return p
}

/**
 * The wordmark with its baseline at (x, y) and the em at `size` px. Returns
 * its width. `leanDeg` is the second l's angle: the brand's 5° unless a card
 * is leaning it in.
 */
export function drawWordmark(
  g: CanvasRenderingContext2D, x: number, y: number, size: number, ink: string, lean: string,
  leanDeg: number = SP_LEAN_DEG,
): number {
  SP_WORDMARK.forEach((r, i) => {
    g.save()
    g.translate(x + r.x * size, y)
    if (i === SP_LEAN_INDEX) {
      const cx = ((r.bb[0] + r.bb[1]) / 2) * size
      g.translate(cx, 0)
      g.rotate((-leanDeg * Math.PI) / 180)
      g.translate(-cx, 0)
    }
    g.scale(size, size)
    g.fillStyle = i === SP_LEAN_INDEX ? lean : ink
    g.fill(path2d(r.d))
    g.restore()
  })
  return SP_WORDMARK_WIDTH * size
}

function plateGeometry(h: number) {
  const size = h / 1.2029
  const pad = size * 0.14
  const sw = size * 0.135, gap = size * 0.085
  const xh = -SP_S.top * size
  const stemsX = SP_S.width * size + size * 0.08
  const px = stemsX + sw * 2 + gap + size * 0.08
  const w = px + SP_P.width * size + pad * 2
  return { size, pad, sw, gap, xh, stemsX, px, w }
}

/** The plate's width for a height. */
export const plateWidth = (h: number): number => plateGeometry(h).w

/** The monogram s∥p in its plate; `h` is the plate height. Returns its width. */
export function drawPlate(g: CanvasRenderingContext2D, x: number, y: number, h: number, lean: string): number {
  const { size, pad, sw, gap, xh, stemsX, px, w } = plateGeometry(h)
  g.save()
  g.translate(x, y)
  g.fillStyle = SP_COLOURS.ink
  rounded(g, 0, 0, w, h, w * 0.18)
  g.fill()
  g.translate(pad, pad + SP_METRICS.asc * size)
  g.fillStyle = SP_COLOURS.paper
  g.save(); g.scale(size, size); g.fill(path2d(SP_S.d)); g.restore()
  g.save(); g.translate(px, 0); g.scale(size, size); g.fill(path2d(SP_P.d)); g.restore()
  // the two stems, the second leaning
  rounded(g, stemsX, -xh, sw, xh, sw / 2); g.fill()
  g.save()
  g.translate(stemsX + sw + gap + sw / 2, 0)
  g.rotate((-SP_LEAN_DEG * Math.PI) / 180)
  g.fillStyle = lean
  rounded(g, -sw / 2, -xh, sw, xh, sw / 2); g.fill()
  g.restore()
  g.restore()
  return w
}

function rounded(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath()
  g.moveTo(x + r, y)
  g.arcTo(x + w, y, x + w, y + h, r)
  g.arcTo(x + w, y + h, x, y + h, r)
  g.arcTo(x, y + h, x, y, r)
  g.arcTo(x, y, x + w, y, r)
  g.closePath()
}

type Label = (text: string, x: number, y: number, size: number, align: CanvasTextAlign) => void

/**
 * The drawing: the wordmark across the width, its construction around it.
 * `label` draws mono caps the film's way. `block` fills the title block.
 */
export function drawSheet(
  g: CanvasRenderingContext2D, w: number, h: number, k: number, inks: SheetInk,
  label: Label, block: Array<[string, string]>, opts: { y?: number; size?: number; titleBlock?: boolean; labels?: boolean } = {},
): { baseline: number; size: number } {
  const size = opts.size ?? Math.min((w - 240 * k) / SP_WORDMARK_WIDTH, 112 * k)
  const width = SP_WORDMARK_WIDTH * size
  const x0 = (w - width) / 2
  const y0 = opts.y ?? h * 0.5
  const m = SP_METRICS
  const hair = (x1: number, y1: number, x2: number, y2: number, dash?: number[]) => {
    g.save()
    g.strokeStyle = inks.hair
    g.lineWidth = Math.max(1, k)
    if (dash) g.setLineDash(dash.map((d) => d * k))
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke()
    g.restore()
  }
  const rows: Array<[string, number]> = [['ASCENDER', m.asc], ['X-HEIGHT', m.xh], ['BASELINE', 0], ['DESCENDER', m.desc]]
  for (const [name, v] of rows) {
    const y = y0 - v * size
    const reach = opts.labels === false ? 24 * k : 60 * k
    hair(x0 - reach, y, x0 + width + reach, y, name === 'BASELINE' ? undefined : [2, 4])
    if (opts.labels !== false) label(`${name} · ${Math.round(Math.abs(v) * 1000)}`, x0 - 60 * k, y - 5 * k, 10, 'left')
  }
  drawWordmark(g, x0, y0, size, inks.ink, inks.lean)

  // the leaning l: its upright ghost, the leaning axis, the arc and the offset at the top
  const r = SP_WORDMARK[SP_LEAN_INDEX]
  const cx = x0 + (r.x + (r.bb[0] + r.bb[1]) / 2) * size
  const top = y0 + r.bb[2] * size
  const stemH = y0 - top
  const dx = stemH * Math.tan((SP_LEAN_DEG * Math.PI) / 180)
  hair(cx, y0 + 20 * k, cx, top - 40 * k, [3, 3])
  g.save()
  g.strokeStyle = inks.lean; g.lineWidth = Math.max(1, k); g.setLineDash([3 * k, 3 * k])
  g.beginPath(); g.moveTo(cx, y0); g.lineTo(cx + dx * 1.18, top - 0.18 * stemH); g.stroke()
  g.restore()
  const rad = stemH * 0.78, a = (SP_LEAN_DEG * Math.PI) / 180
  g.save()
  g.strokeStyle = inks.label; g.lineWidth = Math.max(1, k)
  g.beginPath(); g.arc(cx, y0, rad, -Math.PI / 2, -Math.PI / 2 + a); g.stroke()
  g.restore()
  label(`${SP_LEAN_DEG}°`, cx + rad * Math.sin(a / 2) + 10 * k, y0 - rad * Math.cos(a / 2) + 4 * k, 10, 'left')
  const t = 5 * k, yd = top - 46 * k
  hair(cx, yd, cx + dx, yd); hair(cx, yd - t, cx, yd + t); hair(cx + dx, yd - t, cx + dx, yd + t)
  label(`${Math.round(dx / k)} · AT THE TOP`, cx + dx / 2, yd - 6 * k, 10, 'center')
  const sx1 = x0 + (r.x + r.bb[0]) * size, sx2 = x0 + (r.x + r.bb[1]) * size, ys = y0 + 28 * k
  hair(sx1, ys, sx2, ys); hair(sx1, ys - t, sx1, ys + t); hair(sx2, ys - t, sx2, ys + t)
  label(`STEM ${Math.round((sx2 - sx1) / k)}`, (sx1 + sx2) / 2, ys + 14 * k, 10, 'center')

  if (opts.titleBlock !== false && block.length) {
    const bw = Math.min(360 * k, w - 32 * k), bh = 18 * k * block.length + 14 * k
    const bx = w - bw - 16 * k, by = h - bh - 16 * k
    g.save()
    g.strokeStyle = inks.hair; g.lineWidth = Math.max(1, k)
    g.strokeRect(bx, by, bw, bh)
    g.beginPath(); g.moveTo(bx + 120 * k, by); g.lineTo(bx + 120 * k, by + bh); g.stroke()
    block.forEach(([key, value], i) => {
      const yy = by + 18 * k * (i + 1) - 4 * k
      if (i) { g.beginPath(); g.moveTo(bx, yy - 13 * k); g.lineTo(bx + bw, yy - 13 * k); g.stroke() }
      label(key, bx + 8 * k, yy, 9, 'left')
      label(value, bx + bw - 8 * k, yy, 9, 'right')
    })
    g.restore()
  }
  return { baseline: y0, size }
}
