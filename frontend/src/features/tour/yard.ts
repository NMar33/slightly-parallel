/**
 * Intro "yard", as an opening of the tour: brand/video/intro-yard.html,
 * drawn on the tour's own canvas so a video carries the intro in the same
 * file. 8 seconds. The yard at night, lamps on, the drawing of the name over it.
 *
 *  0.0–1.0  the drawing holds       1.0–1.9  it fades, the yard brightens
 *  1.6–6.0  a container train comes out of the distance on the third track and passes the camera
 *  6.0–7.0  the yard dims, the drawing returns   7.0–8.0  hold; the last frame is the first
 *
 * Deterministic: drawYard(t) with t in seconds. The picture is composed on
 * 1920×1080 and fitted to the stage: by height on 16:9, by width on 1:1 and
 * 9:16. What the stage shows beyond the composition is the same yard carried
 * on — sky above, ground and rails below, under the same vignette — so there
 * is no band and no seam. The drawing of the name is spcard's drawSheet, the
 * same outlines as brand/kit (SP-36, the end card over the dimmed yard),
 * drawn at the stage's own scale rather than from an embedded picture.
 */

import { SP_COLOURS } from '../timelapse/spmark'
import { drawSheet, sheetInk } from '../timelapse/spcard'

export const YARD_SECONDS = 8

const W = 1920, H = 1080
const VP = { x: W * 0.52, y: H * 0.42 } // vanishing point
const HORIZON = VP.y
const JADE = '#4FB39A', INK = '#F2F4F3'
const TRACKS = 8
const WORDS = ['scan', 'standup', 'decision', 'sprint', 'task', 'chat']
const COLORS = ['#7A6CC5', '#B5533C', '#D99A2B', '#4A5FC0', '#4FB39A', '#9AA6AB']
const MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace'
/** The stencil on the boxes; a condensed face where the display one is not installed. */
const STENCIL = '"Big Shoulders Display", "Roboto Condensed", "DejaVu Sans Condensed", "Arial Narrow", sans-serif'
/** The title block of the end card (brand/kit/build.py, TB). */
const TITLE_BLOCK: Array<[string, string]> = [
  ['DRAWING', 'WORDMARK, LOWERCASE'], ['SCALE', '1 : 1'], ['LEAN', '5° · SECOND L'], ['SHEET', '1 OF 1'], ['REV', 'A · 2026-10-06'],
]

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))
const ease = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : t * t * (3 - 2 * t))
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
// a track i at bottom-x position bx converges to VP. Rail pair spacing at bottom ~ 150.
const trackBottomX = (i: number) => W * 0.5 + (i - 3.5) * 300
const railAt = (bx: number, d: number) => VP.x + (bx - VP.x) * d // d: 0 at horizon .. 1 at bottom
const yAt = (d: number) => lerp(HORIZON, H + 40, d)

/** The part of the composition the stage shows, in composition px. */
type View = { x0: number; y0: number; x1: number; y1: number }

function drawSky(g: CanvasRenderingContext2D, v: View) {
  const sky = g.createLinearGradient(0, 0, 0, HORIZON)
  sky.addColorStop(0, '#05070A'); sky.addColorStop(1, '#0D1419')
  g.fillStyle = sky; g.fillRect(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0) // under the ground too: no seam at the horizon
  // ground
  const gr = g.createLinearGradient(0, HORIZON, 0, H)
  gr.addColorStop(0, '#0D1419'); gr.addColorStop(1, '#15191C')
  g.fillStyle = gr; g.fillRect(v.x0, HORIZON, v.x1 - v.x0, v.y1 - HORIZON)
  // horizon haze
  const hz = g.createRadialGradient(VP.x, VP.y, 0, VP.x, VP.y, 900)
  hz.addColorStop(0, 'rgba(232,163,61,0.16)'); hz.addColorStop(0.5, 'rgba(232,163,61,0.04)'); hz.addColorStop(1, 'rgba(0,0,0,0)')
  g.fillStyle = hz; g.fillRect(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0)
}

function drawTracks(g: CanvasRenderingContext2D, dim: number, v: View) {
  // the deepest the stage reaches below the composition: rails and ties carry on to it
  const far = Math.max(1, (v.y1 + 40 - HORIZON) / (H + 40 - HORIZON))
  for (let i = 0; i < TRACKS; i++) {
    const bx = trackBottomX(i)
    const near = Math.abs(i - 3.5) < 1.5
    // ties
    const tie = (d: number) => {
      const y = yAt(d), xL = railAt(bx - 80, d), xR = railAt(bx + 80, d)
      g.strokeStyle = `rgba(90,98,104,${0.35 * Math.min(d, 1) * (1 - dim)})`; g.lineWidth = Math.max(1, 6 * d)
      g.beginPath(); g.moveTo(xL, y); g.lineTo(xR, y); g.stroke()
    }
    g.save()
    for (let k = 0; k < 60; k++) tie(1 - Math.pow(k / 60, 0.55)) // depth 1 bottom .. 0 horizon (denser far)
    // below the composition, at the spacing the nearest ties have
    for (let z = 1 - 0.117; z > 0 && 1 / z <= far; z -= 0.117) tie(1 / z)
    g.restore()
    // rails: two lines from bottom to vanishing point
    for (const off of [-64, 64]) {
      const x0 = railAt(bx + off, 1), y0 = yAt(1), x1 = railAt(bx + off, 0), y1 = yAt(0)
      const a = near ? 0.95 : 0.6
      g.lineCap = 'round'
      if (far > 1) {
        g.strokeStyle = `rgba(190,200,205,${a * (1 - dim)})`; g.lineWidth = near ? 7 : 4
        g.beginPath(); g.moveTo(railAt(bx + off, far), yAt(far)); g.lineTo(x0, y0); g.stroke()
      }
      const grad = g.createLinearGradient(x0, y0, x1, y1)
      grad.addColorStop(0, `rgba(190,200,205,${a * (1 - dim)})`); grad.addColorStop(1, 'rgba(190,200,205,0)')
      g.strokeStyle = grad; g.lineWidth = near ? 7 : 4
      g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke()
      // wet reflection highlight
      g.strokeStyle = `rgba(232,163,61,${0.18 * (1 - dim)})`; g.lineWidth = near ? 9 : 5
      g.beginPath(); g.moveTo(railAt(bx + off, far), yAt(far)); g.lineTo(lerp(x0, x1, 0.6), lerp(y0, y1, 0.6)); g.stroke()
    }
  }
}

function drawLamps(g: CanvasRenderingContext2D, dim: number) {
  // lamps along the yard, left side
  for (let k = 0; k < 6; k++) {
    const d = 0.95 - k * 0.15
    const x = railAt(trackBottomX(0) - 260, d), yg = yAt(d), h = lerp(40, 420, d)
    g.strokeStyle = `rgba(60,66,70,${0.9 * (1 - dim)})`; g.lineWidth = Math.max(2, 10 * d)
    g.beginPath(); g.moveTo(x, yg); g.lineTo(x, yg - h); g.stroke()
    const r = lerp(30, 200, d)
    const gl = g.createRadialGradient(x, yg - h, 0, x, yg - h, r)
    gl.addColorStop(0, `rgba(232,163,61,${0.9 * (1 - dim)})`); gl.addColorStop(0.15, `rgba(232,163,61,${0.35 * (1 - dim)})`); gl.addColorStop(1, 'rgba(232,163,61,0)')
    g.fillStyle = gl; g.beginPath(); g.arc(x, yg - h, r, 0, 7); g.fill()
    // ground pool
    const pool = g.createRadialGradient(x, yg, 0, x, yg, r * 1.6)
    pool.addColorStop(0, `rgba(232,163,61,${0.25 * (1 - dim)})`); pool.addColorStop(1, 'rgba(232,163,61,0)')
    g.fillStyle = pool; g.save(); g.scale(1, 0.35); g.beginPath(); g.arc(x, yg / 0.35, r * 1.6, 0, 7); g.fill(); g.restore()
  }
}

const BOXH = 360, BOXHW = 118, BOXL = 1.5, LOCOL = 2.0 // world: half-width in bottom-scale px, length in z units
const TRACK_I = 2
function zOf(t: number) {
  const p = clamp((t - 1.6) / 4.4, 0, 1)
  return p < 0.62 ? 34 * Math.pow(1 / 34, p / 0.62) : 1 - ((p - 0.62) / 0.38) * 14
}
function quad(g: CanvasRenderingContext2D, pts: Array<[number, number]>, fill: string) {
  g.fillStyle = fill; g.beginPath(); g.moveTo(pts[0][0], pts[0][1])
  for (const p of pts.slice(1)) g.lineTo(p[0], p[1])
  g.closePath(); g.fill()
}
const shade = (hex: string, k: number) => {
  const n = parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255, gg = (n >> 8) & 255, b = n & 255
  return `rgb(${(r * k) | 0},${(gg * k) | 0},${(b * k) | 0})`
}

/** The stencil for one box, 600×200; null where there is no offscreen canvas (a test). */
let stencil: OffscreenCanvasRenderingContext2D | null | undefined
function stencilFor(word: string, color: string): OffscreenCanvas | null {
  if (stencil === undefined) stencil = typeof OffscreenCanvas === 'undefined' ? null : new OffscreenCanvas(600, 200).getContext('2d')
  const c = stencil
  if (!c) return null
  c.clearRect(0, 0, 600, 200)
  c.fillStyle = color; c.font = `700 150px ${STENCIL}`; c.textAlign = 'center'; c.textBaseline = 'middle'
  // a face wider than the display one is squeezed to the box, not cut by it
  const wide = c.measureText(word).width
  c.save(); c.translate(300, 86); c.scale(Math.min(1, 580 / Math.max(1, wide)), 1); c.fillText(word, 0, 0); c.restore()
  c.font = `500 26px ${MONO}`; c.fillStyle = 'rgba(242,244,243,0.75)'
  c.fillText(`SPLU 00000${WORDS.indexOf(word.toLowerCase()) + 1} 7`, 300, 166)
  return c.canvas
}

function sideText(g: CanvasRenderingContext2D, word: string, bx: number, dn: number, df: number, color: string, alpha: number) {
  // right side face between depths dn (near) and df (far), sliced perspective text
  const tmp = stencilFor(word, color)
  if (!tmp || alpha <= 0) return
  const N = 36
  g.save(); g.globalAlpha *= alpha
  for (let k = 0; k < N; k++) {
    const a = k / N, b = (k + 1) / N
    // text left->right = far->near on the right-side face
    const d0 = lerp(dn, df, a), d1 = lerp(dn, df, b)
    const x0 = railAt(bx + BOXHW, d0), x1 = railAt(bx + BOXHW, d1)
    const yb0 = yAt(d0) - BOXH * d0 * 0.09, h0 = BOXH * d0 * 0.91
    const pad = 0.2 // vertical padding of text within face
    const sx = (k * 600) / N, sw = 600 / N
    g.drawImage(tmp, sx, 0, sw, 200, Math.min(x0, x1), yb0 - h0 * (1 - pad / 2), Math.abs(x1 - x0) + 1, h0 * (1 - pad))
  }
  g.restore()
}

function drawTrain(g: CanvasRenderingContext2D, t: number, dim: number, v: View) {
  if (t < 1.6) return
  const z = zOf(t)
  const bx = trackBottomX(TRACK_I)
  // list cars far->near: loco at z, then containers behind (greater z)
  const cars: Array<{ kind: 'loco' | 'box'; z0: number; len: number; i: number }> = [{ kind: 'loco', z0: z, len: LOCOL, i: -1 }]
  let zz = z + LOCOL + 0.15
  for (let i = 0; i < WORDS.length; i++) { cars.push({ kind: 'box', z0: zz, len: BOXL, i }); zz += BOXL + 0.12 }
  for (const car of cars.slice().reverse()) {
    const dn = 1 / car.z0, df = 1 / (car.z0 + car.len)
    if (car.z0 + car.len <= 0.3 || car.z0 <= 0.3 || dn < 0.02) continue
    const col = car.kind === 'loco' ? JADE : COLORS[car.i]
    const xl = (d: number) => railAt(bx - BOXHW, d), xr = (d: number) => railAt(bx + BOXHW, d)
    const yb = (d: number) => yAt(d) - BOXH * d * 0.09, yt = (d: number) => yAt(d) - BOXH * d
    quad(g, [[railAt(bx - BOXHW * 0.8, dn), yb(dn)], [railAt(bx + BOXHW * 0.8, dn), yb(dn)], [railAt(bx + BOXHW * 0.8, df), yAt(df)], [railAt(bx - BOXHW * 0.8, df), yAt(df)]], '#14181B')
    quad(g, [[railAt(bx - BOXHW * 0.8, dn), yb(dn)], [railAt(bx + BOXHW * 0.8, dn), yb(dn)], [railAt(bx + BOXHW * 0.8, dn), yAt(dn)], [railAt(bx - BOXHW * 0.8, dn), yAt(dn)]], '#1B2024')
    // top
    quad(g, [[xl(dn), yt(dn)], [xr(dn), yt(dn)], [xr(df), yt(df)], [xl(df), yt(df)]], shade(col, 0.55))
    // right side
    quad(g, [[xr(dn), yt(dn)], [xr(dn), yb(dn)], [xr(df), yb(df)], [xr(df), yt(df)]], shade(col, 0.8))
    // corrugation on side: thin dark lines along z
    g.save(); g.strokeStyle = 'rgba(0,0,0,0.22)'; g.lineWidth = Math.max(1, 2.5 * dn)
    const nC = Math.max(6, Math.round(car.len * 14))
    for (let k = 1; k < nC; k++) {
      const d = 1 / (car.z0 + (car.len * k) / nC)
      g.beginPath(); g.moveTo(xr(d), yt(d)); g.lineTo(xr(d), yb(d)); g.stroke()
    }
    g.restore()
    if (car.kind === 'box') {
      const near = clamp((dn - 0.12) / 0.5, 0, 1)
      sideText(g, WORDS[car.i].toUpperCase(), bx, dn, df, 'rgba(242,244,243,0.92)', near * (1 - dim))
    }
    // end face (toward camera)
    quad(g, [[xl(dn), yt(dn)], [xr(dn), yt(dn)], [xr(dn), yb(dn)], [xl(dn), yb(dn)]], col)
    const w = xr(dn) - xl(dn), h = BOXH * dn
    if (car.kind === 'loco') {
      // windscreen + headlamp
      g.fillStyle = '#0B0F12'; g.fillRect(xl(dn) + w * 0.12, yt(dn) + h * 0.12, w * 0.76, h * 0.3)
      const hx = xl(dn) + w * 0.5, hy = yt(dn) + h * 0.62
      g.fillStyle = INK; g.beginPath(); g.arc(hx, hy, Math.max(2, w * 0.05), 0, 7); g.fill()
      const gl = g.createRadialGradient(hx, hy, 0, hx, hy, w * 0.9)
      gl.addColorStop(0, 'rgba(242,244,243,0.55)'); gl.addColorStop(1, 'rgba(242,244,243,0)')
      g.fillStyle = gl; g.fillRect(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0)
    } else {
      // container doors: two vertical bars
      g.fillStyle = 'rgba(0,0,0,0.3)'
      g.fillRect(xl(dn) + w * 0.5 - w * 0.01, yt(dn), w * 0.02, h)
      for (const fx of [0.3, 0.42, 0.58, 0.7]) g.fillRect(xl(dn) + w * fx, yt(dn) + h * 0.08, Math.max(1, w * 0.015), h * 0.84)
    }
  }
}

function grain(g: CanvasRenderingContext2D, v: View) {
  // cheap film grain: sparse dots, as many to the area as on the composition
  const vw = v.x1 - v.x0, vh = v.y1 - v.y0
  const n = Math.round((4000 * vw * vh) / (W * H))
  g.save(); g.globalAlpha *= 0.05; g.fillStyle = '#fff'
  let s = 1234
  const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647
  for (let i = 0; i < n; i++) g.fillRect(v.x0 + rnd() * vw, v.y0 + rnd() * vh, 1.5, 1.5)
  g.restore()
}

const sheetAlpha = (t: number) => (t < 1.0 ? 1 : t < 1.9 ? 1 - ease((t - 1.0) / 0.9) : t < 6.0 ? 0 : ease((t - 6.0) / 1.0))

/** A mono caps label, the kit's way (JetBrains Mono 500, tracked). */
function label(
  g: CanvasRenderingContext2D, k: number, text: string, x: number, y: number,
  size: number, colour: string, align: CanvasTextAlign, tracking = 1.6,
) {
  g.save()
  g.fillStyle = colour
  g.font = `500 ${size * k}px ${MONO}`
  g.textAlign = align
  g.letterSpacing = `${(tracking * k).toFixed(2)}px`
  g.fillText(text, x, y)
  g.restore()
}

/**
 * The end card over the yard: the dot grid, the drawing, the line under it
 * and the title block, in stage px at the composition's scale `k`.
 */
function sheet(g: CanvasRenderingContext2D, w: number, h: number, k: number, ox: number, oy: number) {
  const inks = sheetInk(SP_COLOURS.dark)
  // the grid runs to the stage's edges, on the composition's pitch
  g.save()
  g.fillStyle = '#1C2321'
  const pitch = 24 * k
  for (let x = ox + ((-ox / pitch) | 0) * pitch - pitch; x < w; x += pitch) {
    if (x + pitch < 0) continue
    for (let y = oy + ((-oy / pitch) | 0) * pitch - pitch; y < h; y += pitch) {
      if (y + pitch < 0) continue
      g.beginPath(); g.arc(x + k, y + k, 0.8 * k, 0, 7); g.fill()
    }
  }
  g.restore()
  const base = oy + H * 0.58 * k
  drawSheet(
    g, w, h, k, inks,
    (text, x, y, size, align) => label(g, k, text, x, y, size, inks.label, align),
    [], { y: base, size: 160 * k, titleBlock: false },
  )
  label(g, k, 'AGENTS, SIDE BY SIDE', w / 2, base + 120 * k, 22, inks.label, 'center', 8)
  // title block, bottom right of the composition
  const bw = 300 * k, bh = (18 * TITLE_BLOCK.length + 14) * k
  const bx = ox + (W - 16) * k - bw, by = oy + (H - 16) * k - bh
  g.save()
  g.strokeStyle = inks.hair; g.lineWidth = Math.max(1, k)
  g.strokeRect(bx, by, bw, bh)
  g.beginPath(); g.moveTo(bx + 110 * k, by); g.lineTo(bx + 110 * k, by + bh); g.stroke()
  TITLE_BLOCK.forEach(([key, value], i) => {
    const yy = by + (18 * (i + 1) - 4) * k
    if (i) { g.beginPath(); g.moveTo(bx, yy - 13 * k); g.lineTo(bx + bw, yy - 13 * k); g.stroke() }
    label(g, k, key, bx + 8 * k, yy, 9, inks.label, 'left')
    label(g, k, value, bx + bw - 8 * k, yy, 9, inks.ink, 'right')
  })
  g.restore()
}

/** The intro at `t` seconds (0..8) on a `w`×`h` stage; it paints the whole stage. */
export function drawYard(g: CanvasRenderingContext2D, w: number, h: number, t: number) {
  t = clamp(t, 0, YARD_SECONDS)
  const k = Math.min(w / W, h / H)
  const ox = (w - W * k) / 2, oy = (h - H * k) / 2
  const v: View = { x0: -ox / k, y0: -oy / k, x1: (w - ox) / k, y1: (h - oy) / k }
  const sh = sheetAlpha(t), dim = sh * 0.62
  g.save()
  g.translate(ox, oy)
  g.scale(k, k)
  drawSky(g, v)
  drawTracks(g, dim, v)
  drawLamps(g, dim)
  drawTrain(g, t, dim, v)
  // vignette
  const vg = g.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.9)
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,0.75)')
  g.fillStyle = vg; g.fillRect(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0)
  grain(g, v)
  g.restore()
  if (sh > 0) {
    g.save()
    g.globalAlpha *= sh
    sheet(g, w, h, k, ox, oy)
    g.restore()
  }
}
