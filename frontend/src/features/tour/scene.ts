/**
 * The tour, drawn.
 *
 * One pure function: give it a script, a bag of decoded shots and a time in
 * seconds, and it paints that instant. Playback, the contact sheet and the
 * GIF encoder all call the same one, so what you scrub to is what exports.
 *
 * Two rules keep it honest and keep the file small.
 *
 * The camera only moves when the beat asked it to. A slow drift over every
 * still would look like production value and would change every pixel of
 * every frame — in a GIF that is the difference between a held frame that
 * costs nothing and a megabyte of shimmer. Stillness is a choice here.
 *
 * The screen is drawn at the shot's own aspect, never stretched. A product
 * tour whose screenshots are 2% wide than life is a tour nobody trusts.
 */

import type { Theme } from '../timelapse/theme'
// `t` is the stage theme in this file's functions: the translator goes by another name.
import { t as tr } from '../../i18n/scope/shell'

import {
  clamp, ease, cueAt, kindOf,
  type Beat, type Panel, type Place, type Pointer, type Script, type ShotRect,
} from './script'
import { drawEnding, drawOpening } from './bookends'
import { drawGround } from './ground'
import { drawSlide, drawTerminal } from './slides'
import { fitSize, lines, wrap } from './words'

export type Shot = {
  frames: CanvasImageSource[]
  w: number
  h: number
  rect: ShotRect | null
  /** The page's own nav items, for the "you are here" rings. */
  nav: ShotRect[]
  /** Where the mouse was for each frame, when the beat had a hand in it. */
  pointer: (Pointer | null)[]
  /** The card a drag picked up. */
  grab: ShotRect | null
}

export type Stage = {
  w: number
  h: number
  theme: Theme
  face: string
  shots: Map<string, Shot>
  /** The pictures slides name, by their address. */
  images?: Map<string, CanvasImageSource>
  /** Draw the chapter and progress footer. */
  footer: boolean
  /** Title and end cards. */
  bookends: boolean
  /** Ring the page's own nav item. */
  highlight: boolean
  /** How the card is drawn. */
  panel: Panel
}

type Rect = { x: number; y: number; w: number; h: number }

/**
 * A rounded rectangle. `keep` adds to the open path instead of starting a
 * new one — which is how the spotlight cuts its hole: one path holding the
 * page and the subject, filled even-odd.
 */
function rr(
  g: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number, r: number,
  keep = false,
) {
  const rad = Math.min(r, w / 2, h / 2)
  if (!keep) g.beginPath()
  g.moveTo(x + rad, y)
  g.arcTo(x + w, y, x + w, y + h, rad)
  g.arcTo(x + w, y + h, x, y + h, rad)
  g.arcTo(x, y + h, x, y, rad)
  g.arcTo(x, y, x + w, y, rad)
  g.closePath()
}

function font(stage: Stage, size: number, weight = 400) {
  return `${weight} ${size}px ${stage.face}`
}

const lerp = (a: number, b: number, u: number) => a + (b - a) * u

const lerpRect = (a: Rect, b: Rect, u: number): Rect => ({
  x: lerp(a.x, b.x, u), y: lerp(a.y, b.y, u),
  w: lerp(a.w, b.w, u), h: lerp(a.h, b.h, u),
})

function paintGround(g: CanvasRenderingContext2D, stage: Stage) {
  const ground = stage.theme.ground
  if (typeof ground === 'string') {
    g.fillStyle = ground
  } else {
    // Vertical only: one colour per row is one long run in the GIF's
    // compressor, where a diagonal is a new run on every line.
    const grad = g.createLinearGradient(0, 0, 0, stage.h)
    grad.addColorStop(0, ground.from)
    grad.addColorStop(1, ground.to)
    g.fillStyle = grad
  }
  g.fillRect(0, 0, stage.w, stage.h)
}

/* ------------------------------- camera ------------------------------- */

/**
 * The smallest window a beat may crop to.
 *
 * Not a sharpness limit — a legibility one. Crop to a fifth of the page and
 * the viewer is looking at a button with no idea it is on a kanban board,
 * which is the opposite of what a tour is for.
 */
const MIN_VIEW = 0.5
/** Air around the thing being pointed at. */
const FOCUS_PAD = 0.05

function focusView(shot: Shot, aspect: number): Rect {
  const r = shot.rect
  if (!r) return { x: 0, y: 0, w: 1, h: 1 }
  const padX = FOCUS_PAD
  const padY = (FOCUS_PAD * shot.w) / shot.h
  let w = Math.max(MIN_VIEW, r.w + padX * 2)
  let h = Math.max(MIN_VIEW * (shot.w / shot.h) * (1 / aspect), r.h + padY * 2)
  // Grow whichever side is short so the window matches the screen's shape.
  const cur = (w * shot.w) / (h * shot.h)
  if (cur < aspect) w = (h * shot.h * aspect) / shot.w
  else h = (w * shot.w) / (shot.h * aspect)
  w = Math.min(1, w)
  h = Math.min(1, h)
  const cx = r.x + r.w / 2
  const cy = r.y + r.h / 2
  return {
    x: clamp(cx - w / 2, 0, 1 - w),
    y: clamp(cy - h / 2, 0, 1 - h),
    w,
    h,
  }
}

/** The window on the shot for this beat at this moment. */
export function viewFor(beat: Beat, shot: Shot, aspect: number, u: number): Rect {
  const full: Rect = { x: 0, y: 0, w: 1, h: 1 }
  if (!shot.rect || beat.zoom === 'full') return full
  const near = focusView(shot, aspect)
  if (beat.zoom === 'focus') return near
  // A move that starts and ends still, and is over before the sentence is.
  // A demonstration pushes in late, once its last step is on screen: the
  // page it started on is shown whole first.
  const travel = beat.steps?.length ? ease(clamp((u - 0.5) / 0.25)) : ease(clamp(u / 0.55))
  return beat.zoom === 'push' ? lerpRect(full, near, travel) : lerpRect(near, full, travel)
}

/* ------------------------------ the screen ---------------------------- */

/** Where the shot sits on the stage, at its own aspect. */
function screenBox(stage: Stage, shot: Shot, area: Rect): Rect {
  const a = shot.w / shot.h
  let w = area.w
  let h = w / a
  if (h > area.h) {
    h = area.h
    w = h * a
  }
  return { x: area.x + (area.w - w) / 2, y: area.y + (area.h - h) / 2, w, h }
}

function drawScreen(
  g: CanvasRenderingContext2D, stage: Stage, shot: Shot, box: Rect, view: Rect, frame: number,
) {
  const t = stage.theme
  const radius = Math.max(6, stage.w * 0.008)
  g.save()
  g.shadowColor = 'rgba(0,0,0,0.30)'
  g.shadowBlur = radius * 3
  g.shadowOffsetY = radius * 0.8
  g.fillStyle = t.panel
  rr(g, box.x, box.y, box.w, box.h, radius)
  g.fill()
  g.restore()

  g.save()
  rr(g, box.x, box.y, box.w, box.h, radius)
  g.clip()
  const img = shot.frames[Math.min(frame, shot.frames.length - 1)]
  if (img) {
    g.imageSmoothingEnabled = true
    g.imageSmoothingQuality = 'high'
    g.drawImage(
      img,
      view.x * shot.w, view.y * shot.h, view.w * shot.w, view.h * shot.h,
      box.x, box.y, box.w, box.h,
    )
  }
  g.restore()

  g.strokeStyle = t.rule
  g.lineWidth = 1
  rr(g, box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1, radius)
  g.stroke()
}

/** Where the focus rect landed on the stage, once the camera has it. */
function focusOnStage(box: Rect, view: Rect, rect: ShotRect): Rect {
  return {
    x: box.x + ((rect.x - view.x) / view.w) * box.w,
    y: box.y + ((rect.y - view.y) / view.h) * box.h,
    w: (rect.w / view.w) * box.w,
    h: (rect.h / view.h) * box.h,
  }
}

function spotlight(
  g: CanvasRenderingContext2D, stage: Stage, box: Rect, hole: Rect, alpha: number,
) {
  if (alpha <= 0.01) return
  const t = stage.theme
  const pad = stage.w * 0.006
  const r = { x: hole.x - pad, y: hole.y - pad, w: hole.w + pad * 2, h: hole.h + pad * 2 }
  const radius = Math.max(4, stage.w * 0.005)
  g.save()
  rr(g, box.x, box.y, box.w, box.h, Math.max(6, stage.w * 0.008))
  g.clip()
  // Dim the page, then cut the subject back out of the dimming.
  g.globalAlpha = alpha * 0.62
  g.fillStyle = typeof t.ground === 'string' ? t.ground : t.ground.to
  g.beginPath()
  g.rect(box.x, box.y, box.w, box.h)
  rr(g, r.x, r.y, r.w, r.h, radius, true)
  g.fill('evenodd')
  g.restore()

  g.save()
  g.globalAlpha = alpha
  g.strokeStyle = t.lanes[0]
  g.lineWidth = Math.max(2, stage.w * 0.0022)
  rr(g, r.x, r.y, r.w, r.h, radius)
  g.stroke()
  g.restore()
}

/* ------------------------------ the callout --------------------------- */

type Callout = {
  title: string; text: string; step: string; progress: number
  chapter: string; index: number; of: number
}

const MONO = 'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace'

/**
 * The card, in whichever dress the cut chose.
 *
 * Four, because one panel style makes every tour look like the same tour,
 * and the right one depends on where the film is going: a card for a product
 * page, a bar for something that reads like a subtitle, plain for a quiet
 * ground, terminal for an audience that lives in one.
 */
function drawCallout(
  g: CanvasRenderingContext2D, stage: Stage, at: Rect, c: Callout, alpha: number, fit = false,
) {
  if (alpha <= 0.01) return
  let box = at
  const t = stage.theme
  const style = stage.panel
  const mono = style === 'terminal'
  const bar = style === 'bar'
  const pad = Math.min(box.w * (bar ? 0.03 : 0.055), stage.w * 0.02)
  const titleSize = Math.max(14, Math.min(box.w * (bar ? 0.032 : 0.052), stage.w * 0.023))
  const bodySize = Math.max(11, Math.min(box.w * (bar ? 0.019 : 0.034), stage.w * (bar ? 0.0125 : 0.0145)))
  const radius = style === 'terminal' ? 0 : Math.max(6, stage.w * 0.008)
  const face = mono ? MONO : stage.face
  const rule = Math.max(2, stage.w * 0.0026)
  const plain = style === 'plain'
  const halo = typeof t.ground === 'string' ? t.ground : t.ground.to

  /**
   * A card as tall as its words. The size the placement reserved is for the
   * longest caption; a three-line caption in it left half the card empty,
   * covering the page for nothing. The edge nearer the stage's middle moves,
   * so a card in a corner stays in its corner. A band keeps its height.
   */
  if (fit && !bar) {
    const h = Math.min(box.h, calloutHeight(g, stage, c, box.w))
    const low = box.y + box.h / 2 > stage.h / 2
    box = { ...box, y: low ? box.y + box.h - h : box.y, h }
  }

  /**
   * Plain has no panel to sit on, so the text carries its own contrast: a
   * halo in the theme's ground colour, which is dark behind light ink and
   * light behind dark. Without it the style is only legible over whichever
   * half of the screenshot happens to be the right shade.
   */
  const write = (text: string, x: number, y: number) => {
    if (plain) {
      g.save()
      g.shadowColor = halo
      g.shadowBlur = stage.w * 0.006
      for (let i = 0; i < 3; i++) g.fillText(text, x, y)
      g.restore()
    }
    g.fillText(text, x, y)
  }

  g.save()
  g.globalAlpha = alpha

  if (style === 'plain') {
    // No box and no edge — the accent rule is the whole frame. Under the
    // words, a wash of the ground: the halo alone keeps a letter legible,
    // not a line, and over a dense page (the statistics table, the file
    // list) the page's own text ran between the caption's lines.
    g.save()
    g.fillStyle = halo
    g.globalAlpha = alpha * 0.84
    rr(g, box.x, box.y, box.w, box.h, radius)
    g.fill()
    g.restore()
    g.fillStyle = t.lanes[0]
    g.fillRect(box.x, box.y, rule, box.h)
  } else {
    g.save()
    if (style === 'card') {
      g.shadowColor = 'rgba(0,0,0,0.28)'
      g.shadowBlur = radius * 3
      g.shadowOffsetY = radius
    }
    g.fillStyle = t.panel
    g.globalAlpha = alpha * (bar ? 0.94 : 1)
    rr(g, box.x, box.y, box.w, box.h, radius)
    g.fill()
    g.restore()
    g.strokeStyle = style === 'terminal' ? t.lanes[0] : t.rule
    g.lineWidth = 1
    rr(g, box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1, radius)
    g.stroke()
  }

  // How much of this beat is left — the one number a viewer wants from a
  // tour. A bar wears it along its own top edge; a card across the panel.
  if (style !== 'plain') {
    const barH = Math.max(2, stage.w * 0.0026)
    g.save()
    rr(g, box.x, box.y, box.w, box.h, radius)
    g.clip()
    g.fillStyle = t.rule
    g.fillRect(box.x, box.y, box.w, barH)
    g.fillStyle = t.lanes[0]
    g.fillRect(box.x, box.y, box.w * clamp(c.progress), barH)
    g.restore()
  }

  const left = box.x + pad + (style === 'plain' ? rule * 3 : 0)
  const width = box.w - pad * 2 - (style === 'plain' ? rule * 3 : 0)
  let y = box.y + pad + titleSize

  g.fillStyle = t.ink
  g.font = `${mono ? 600 : 650} ${titleSize}px ${face}`
  const head = mono ? `▍ ${c.title}` : c.title
  for (const line of wrap(g, head, width).slice(0, 2)) {
    write(line, left, y)
    y += titleSize * 1.18
  }

  y += bodySize * (bar ? 0.35 : 0.5)
  // With no panel behind it, muted grey against a screenshot is mush however
  // strong the halo. Plain keeps the ink and loses a little weight instead.
  g.fillStyle = plain ? t.ink : t.muted
  g.globalAlpha = alpha * (plain ? 0.92 : 1)
  g.font = `400 ${bodySize}px ${face}`
  const room = box.y + box.h - pad - bodySize * 1.1
  for (const line of wrap(g, c.text, width)) {
    if (y > room) break
    write(line, left, y)
    y += bodySize * 1.52
  }

  g.globalAlpha = alpha
  g.fillStyle = plain ? t.muted : t.dim
  g.font = `600 ${Math.max(10, bodySize * 0.78)}px ${mono ? MONO : face}`
  const step = mono ? `[${c.step.replace(/\s/g, '')}]` : c.step.toUpperCase()
  write(step, left, box.y + box.h - pad * 0.9)
  g.restore()
}

/** How tall the card's words make it at width `w`: the card, the bar, plain and terminal alike. */
function calloutHeight(g: CanvasRenderingContext2D, stage: Stage, c: Callout, w: number): number {
  const style = stage.panel
  const mono = style === 'terminal'
  const bar = style === 'bar'
  const plain = style === 'plain'
  const pad = Math.min(w * (bar ? 0.03 : 0.055), stage.w * 0.02)
  const titleSize = Math.max(14, Math.min(w * (bar ? 0.032 : 0.052), stage.w * 0.023))
  const bodySize = Math.max(11, Math.min(w * (bar ? 0.019 : 0.034), stage.w * (bar ? 0.0125 : 0.0145)))
  const face = mono ? MONO : stage.face
  const rule = Math.max(2, stage.w * 0.0026)
  const width = w - pad * 2 - (plain ? rule * 3 : 0)
  g.save()
  g.font = `${mono ? 600 : 650} ${titleSize}px ${face}`
  const heads = Math.min(2, wrap(g, mono ? `▍ ${c.title}` : c.title, width).length)
  g.font = `400 ${bodySize}px ${face}`
  const lines = wrap(g, c.text, width).length
  g.restore()
  const last = pad + titleSize + heads * titleSize * 1.18 + bodySize * (bar ? 0.35 : 0.5)
    + Math.max(0, lines - 1) * bodySize * 1.52
  return last + pad + bodySize * 2.3
}

/** How big the card wants to be, before it is put anywhere. */
function cardSize(stage: Stage, place: Place, panel: Panel) {
  if (panel === 'bar') return { w: stage.w * 0.78, h: stage.h * 0.27 }
  if (place === 'top' || place === 'bottom') return { w: stage.w * 0.44, h: stage.h * 0.26 }
  return { w: stage.w * 0.29, h: stage.h * 0.33 }
}

/**
 * Where the card goes.
 *
 * `auto` puts it beside the subject when there is real room beside it, and
 * otherwise in the far corner — the failure to avoid is the card that just
 * fits and covers the row the subject belongs to. Every other value is the
 * operator overriding that for one beat, which is the only way to fix a page
 * whose interesting part happens to be exactly where the guess puts it.
 */
function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
}

function calloutBox(
  stage: Stage, screen: Rect, hole: Rect | null, place: Place, panel: Panel,
  avoid: Rect[] = [],
  size: { w: number; h: number } = cardSize(stage, place, panel),
): Rect {
  const { w, h } = size
  const margin = stage.w * 0.035
  const midY = screen.y + screen.h / 2 - h / 2
  const midX = screen.x + screen.w / 2 - w / 2
  if (place === 'left') return { x: screen.x + margin, y: midY, w, h }
  if (place === 'right') return { x: screen.x + screen.w - w - margin, y: midY, w, h }
  if (place === 'top') return { x: midX, y: screen.y + margin, w, h }
  if (place === 'bottom') return { x: midX, y: screen.y + screen.h - h - margin, w, h }

  /**
   * The corner, chosen against what is already lit.
   *
   * The nav rings live down the left edge, which is exactly where the card
   * used to land when a beat had nothing else to point at — so the tour
   * highlighted the sidebar and then covered it. Any corner that collides
   * with a ring loses to one that does not.
   */
  const corner = (bottom: boolean, right = false): Rect => ({
    x: right ? screen.x + screen.w - w - margin : screen.x + margin,
    y: bottom ? screen.y + screen.h - h - margin : screen.y + margin,
    w,
    h,
  })
  const pick = (bottom: boolean): Rect => {
    const left = corner(bottom)
    if (!avoid.some((r) => overlaps(left, r))) return left
    const other = corner(bottom, true)
    return avoid.some((r) => overlaps(other, r)) ? left : other
  }
  if (!hole) return pick(true)

  const leftRoom = hole.x - screen.x
  const rightRoom = screen.x + screen.w - (hole.x + hole.w)
  const room = Math.max(leftRoom, rightRoom)
  if (room < w + margin * 2.4) {
    return pick(hole.y + hole.h / 2 < screen.y + screen.h / 2)
  }
  // A subject in the middle makes the two sides equal, and then rounding
  // decides — which means the preview and the twice-as-large export can
  // disagree about which side the card is on. Settle ties in one direction.
  const x = rightRoom >= leftRoom - stage.w * 1e-6
    ? Math.min(hole.x + hole.w + margin, screen.x + screen.w - w - margin * 0.4)
    : Math.max(hole.x - w - margin, screen.x + margin * 0.4)
  const y = clamp(
    hole.y + hole.h / 2 - h / 2,
    screen.y + margin * 0.5,
    screen.y + screen.h - h - margin * 0.5,
  )
  return { x, y, w, h }
}

/**
 * "You are here."
 *
 * A tour that says "open a project" while showing a project page leaves the
 * viewer to find where that lives. Ringing the nav item the page sits under
 * answers it without a sentence — and it is the page's own nav item, found
 * by its own href, not a rectangle drawn from memory.
 */
function drawNav(
  g: CanvasRenderingContext2D, stage: Stage, box: Rect, view: Rect, at: Rect, alpha: number,
) {
  const t = stage.theme
  const { x, y, w, h } = at
  if (w < 4 || h < 4) return
  if (x + w < box.x || x > box.x + box.w) return
  const pad = stage.w * 0.004
  const radius = Math.max(3, stage.w * 0.004)
  g.save()
  g.globalAlpha = alpha
  rr(g, box.x, box.y, box.w, box.h, Math.max(6, stage.w * 0.008))
  g.clip()
  g.fillStyle = t.lanes[0]
  g.globalAlpha = alpha * 0.16
  rr(g, x - pad, y - pad, w + pad * 2, h + pad * 2, radius)
  g.fill()
  g.globalAlpha = alpha
  g.strokeStyle = t.lanes[0]
  g.lineWidth = Math.max(1.5, stage.w * 0.0016)
  rr(g, x - pad, y - pad, w + pad * 2, h + pad * 2, radius)
  g.stroke()
  g.restore()
}

/* ------------------------------- footer ------------------------------- */

function drawFooter(
  g: CanvasRenderingContext2D, stage: Stage, chapter: string, step: string, through: number,
) {
  const t = stage.theme
  const size = Math.max(9, stage.w * 0.0115)
  const y = stage.h - stage.h * 0.032
  g.save()
  g.fillStyle = t.dim
  g.font = font(stage, size, 600)
  g.fillText(chapter.toUpperCase(), stage.w * 0.04, y)
  g.textAlign = 'right'
  g.fillText(step, stage.w * 0.96, y)
  g.textAlign = 'left'
  const barY = stage.h - stage.h * 0.018
  const barW = stage.w * 0.92
  g.fillStyle = t.rule
  g.fillRect(stage.w * 0.04, barY, barW, 2)
  g.fillStyle = t.lanes[0]
  g.fillRect(stage.w * 0.04, barY, barW * clamp(through), 2)
  g.restore()
}

/* -------------------------------- draw -------------------------------- */

/** How many stops a progress bar has inside one beat. */
const PROGRESS_STEPS = 8


/* -------------------------------- the hand ---------------------------- */

/**
 * The cursor, and the card under it.
 *
 * A screenshot of a drag shows a board sitting still: the browser paints the
 * cursor and the card it is carrying into a layer no screenshot captures. So
 * the capture records where the mouse actually was for each frame, and this
 * puts it back — the ghost card is the real card's size, moving along the
 * real path. Without it the most important gesture in the product is a
 * sequence of pictures in which nothing appears to happen.
 */
function drawHand(
  g: CanvasRenderingContext2D, stage: Stage, box: Rect, view: Rect,
  at: Pointer, grab: ShotRect | null, tap: number,
) {
  const t = stage.theme
  const px = box.x + ((at.x - view.x) / view.w) * box.w
  const py = box.y + ((at.y - view.y) / view.h) * box.h
  if (px < box.x - 40 || px > box.x + box.w + 40) return

  if (at.down && grab) {
    const gw = (grab.w / view.w) * box.w
    const gh = (grab.h / view.h) * box.h
    const gx = px - gw / 2
    const gy = py - gh / 2
    const radius = Math.max(3, stage.w * 0.004)
    g.save()
    g.globalAlpha = 0.92
    g.shadowColor = 'rgba(0,0,0,0.45)'
    g.shadowBlur = stage.w * 0.012
    g.shadowOffsetY = stage.w * 0.004
    g.fillStyle = t.panel
    rr(g, gx, gy, gw, gh, radius)
    g.fill()
    g.restore()
    g.save()
    g.globalAlpha = 0.95
    g.strokeStyle = t.lanes[0]
    g.lineWidth = Math.max(2, stage.w * 0.0018)
    rr(g, gx, gy, gw, gh, radius)
    g.stroke()
    // Two bars standing in for the card's title and body: a filled rectangle
    // reads as a hole in the board, a card reads as a card.
    g.globalAlpha = 0.5
    g.fillStyle = t.ink
    g.fillRect(gx + gw * 0.08, gy + gh * 0.22, gw * 0.62, Math.max(2, gh * 0.09))
    g.globalAlpha = 0.28
    g.fillRect(gx + gw * 0.08, gy + gh * 0.45, gw * 0.78, Math.max(2, gh * 0.07))
    g.fillRect(gx + gw * 0.08, gy + gh * 0.62, gw * 0.5, Math.max(2, gh * 0.07))
    g.restore()
  }

  // A ring that opens once, where the click landed.
  if (tap > 0 && tap < 1) {
    g.save()
    g.globalAlpha = (1 - tap) * 0.8
    g.strokeStyle = t.lanes[0]
    g.lineWidth = Math.max(2, stage.w * 0.002)
    g.beginPath()
    g.arc(px, py, stage.w * (0.006 + 0.022 * tap), 0, Math.PI * 2)
    g.stroke()
    g.restore()
  }

  // The arrow itself: white body, dark edge, so it survives any background.
  const s = stage.w * 0.013
  g.save()
  g.translate(px, py)
  g.beginPath()
  g.moveTo(0, 0)
  g.lineTo(0, s * 1.5)
  g.lineTo(s * 0.36, s * 1.14)
  g.lineTo(s * 0.6, s * 1.72)
  g.lineTo(s * 0.83, s * 1.6)
  g.lineTo(s * 0.6, s * 1.04)
  g.lineTo(s * 1.02, s * 0.98)
  g.closePath()
  g.fillStyle = '#FFFFFF'
  g.shadowColor = 'rgba(0,0,0,0.5)'
  g.shadowBlur = s * 0.7
  g.fill()
  g.shadowColor = 'transparent'
  g.strokeStyle = '#11151C'
  g.lineWidth = Math.max(1, s * 0.09)
  g.stroke()
  g.restore()
}

/* ------------------------------- the skins ---------------------------- */

/**
 * Six more ways to say the same sentence.
 *
 * The four dresses above are one card in four fabrics: a box in a corner.
 * These change where the words live — on the subject, under the film, in a
 * column beside it — because the article a GIF ends up in decides how loud
 * the caption may be, and a tooltip and a headline are different sentences
 * even when the words are the same.
 *
 * Everything is measured in `unit`, a fraction of the stage, so the preview
 * and the twice-as-large export lay out the same frame.
 */
const unit = (stage: Stage) => (stage.w + stage.h) / 2500

type Pt = { x: number; y: number }

/** A tail: the triangle on the box's edge, and the line that carries on to the subject. */
type Tail = { a: Pt; b: Pt; apex: Pt; end: Pt }

/** How far the spotlight's ring stands off its subject — a tail ends on the ring. */
const ringPad = (stage: Stage) => stage.w * 0.006

function rgbOf(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h.slice(0, 6)
  const n = parseInt(full, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function rgba(hex: string, a: number): string {
  const [r, g, b] = rgbOf(hex)
  return `rgba(${r},${g},${b},${a})`
}

function luminance(hex: string): number {
  const [r, g, b] = rgbOf(hex).map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (hi + 0.05) / (lo + 0.05)
}

const groundOf = (t: Theme) => (typeof t.ground === 'string' ? t.ground : t.ground.to)

/**
 * The accent, when it is set as words.
 *
 * The first lane is the theme's accent and reads well as a ring; as small
 * type it can sink — Midnight's blue on Midnight's panel is a ring you see
 * and a word you squint at. Below the contrast body text needs, the
 * theme's other bright colour stands in.
 */
function accentInk(t: Theme, on: string): string {
  for (const c of [t.lanes[0], t.up]) if (contrast(c, on) >= 4.5) return c
  return t.ink
}

/** Ink or ground, whichever reads on this fill. */
const inkOn = (t: Theme, fill: string) =>
  (contrast(t.ink, fill) >= contrast(groundOf(t), fill) ? t.ink : groundOf(t))

/** A small capital label, spaced out — the one line above a title that says what this is. */
function kicker(
  g: CanvasRenderingContext2D, stage: Stage, text: string, x: number, y: number,
  size: number, colour: string, align: CanvasTextAlign = 'left',
) {
  g.save()
  g.font = font(stage, size, 700)
  g.fillStyle = colour
  g.letterSpacing = `${size * 0.14}px`
  g.textAlign = align
  // Spacing trails the last letter too; centred, that pushes the word left.
  g.fillText(text.toUpperCase(), align === 'center' ? x + size * 0.07 : x, y)
  g.restore()
}

/** The part of `r` inside `by`, or nothing when they barely touch. */
function within(r: Rect, by: Rect): Rect | null {
  const x = Math.max(r.x, by.x)
  const y = Math.max(r.y, by.y)
  const w = Math.min(r.x + r.w, by.x + by.w) - x
  const h = Math.min(r.y + r.h, by.y + by.h) - y
  return w > 1 && h > 1 ? { x, y, w, h } : null
}

/**
 * The tail from a box to the subject it explains.
 *
 * A short triangle on the box's facing edge, and — when the subject is
 * further than the triangle reaches — a thin line on to the spotlight's
 * ring. A tooltip whose tail stretched the whole way would be a wedge
 * across the page; one whose tail stopped short would point at nothing.
 * Null when the box sits over the subject and has no edge facing it.
 */
function tailFor(stage: Stage, box: Rect, subject: Rect): Tail | null {
  const ring = ringPad(stage)
  const s = { x: subject.x - ring, y: subject.y - ring, w: subject.w + ring * 2, h: subject.h + ring * 2 }
  const len = stage.w * 0.014
  const half = stage.w * 0.008
  const inset = Math.max(6, stage.w * 0.008) + half
  const along = (lo: number, hi: number, want: number) => clamp(want, lo + inset, hi - inset)
  const cx = s.x + s.w / 2
  const cy = s.y + s.h / 2
  let a: Pt, b: Pt, end: Pt
  if (box.y >= s.y + s.h) {
    const x = along(box.x, box.x + box.w, cx)
    a = { x: x - half, y: box.y }
    b = { x: x + half, y: box.y }
    end = { x: clamp(x, s.x, s.x + s.w), y: s.y + s.h }
  } else if (box.y + box.h <= s.y) {
    const x = along(box.x, box.x + box.w, cx)
    a = { x: x - half, y: box.y + box.h }
    b = { x: x + half, y: box.y + box.h }
    end = { x: clamp(x, s.x, s.x + s.w), y: s.y }
  } else if (box.x >= s.x + s.w) {
    const y = along(box.y, box.y + box.h, cy)
    a = { x: box.x, y: y - half }
    b = { x: box.x, y: y + half }
    end = { x: s.x + s.w, y: clamp(y, s.y, s.y + s.h) }
  } else if (box.x + box.w <= s.x) {
    const y = along(box.y, box.y + box.h, cy)
    a = { x: box.x + box.w, y: y - half }
    b = { x: box.x + box.w, y: y + half }
    end = { x: s.x, y: clamp(y, s.y, s.y + s.h) }
  } else {
    return null
  }
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
  const dist = Math.hypot(end.x - mid.x, end.y - mid.y)
  const reach = Math.min(len, dist)
  const apex = dist > 0
    ? { x: mid.x + ((end.x - mid.x) / dist) * reach, y: mid.y + ((end.y - mid.y) / dist) * reach }
    : mid
  return { a, b, apex, end }
}

/**
 * Where a tooltip of `w`×`h` sits against its subject.
 *
 * Under it first, as a tooltip does; then above, right, left — the first
 * side with room that also leaves the lit nav items alone. A subject too
 * big for any side gets the tooltip in the corner furthest from it, still
 * tied to it. No subject: the lower corner, no tail.
 */
function tipLayout(
  stage: Stage, screen: Rect, hole: Rect | null, w: number, h: number, avoid: Rect[] = [],
): { box: Rect; tail: Tail | null } {
  const m = stage.w * 0.014
  const gap = ringPad(stage) + stage.w * 0.014
  const lo = { x: screen.x + m, y: screen.y + m }
  const hi = { x: screen.x + screen.w - m, y: screen.y + screen.h - m }
  const put = (x: number, y: number): Rect => ({
    x: clamp(x, lo.x, Math.max(lo.x, hi.x - w)),
    y: clamp(y, lo.y, Math.max(lo.y, hi.y - h)),
    w, h,
  })
  const clear = (r: Rect) => !avoid.some((a) => overlaps(r, a))
  const s = hole && within(hole, screen)
  if (!s) {
    const left = put(lo.x, hi.y - h)
    const right = put(hi.x - w, hi.y - h)
    return { box: clear(left) || !clear(right) ? left : right, tail: null }
  }
  const cx = s.x + s.w / 2
  const cy = s.y + s.h / 2
  const sides = [
    { ok: s.y + s.h + gap + h <= hi.y, box: put(cx - w / 2, s.y + s.h + gap) },
    { ok: s.y - gap - h >= lo.y, box: put(cx - w / 2, s.y - gap - h) },
    { ok: s.x + s.w + gap + w <= hi.x, box: put(s.x + s.w + gap, cy - h / 2) },
    { ok: s.x - gap - w >= lo.x, box: put(s.x - gap - w, cy - h / 2) },
  ].filter((c) => c.ok)
  const pick = sides.find((c) => clear(c.box)) ?? sides[0]
  if (pick) return { box: pick.box, tail: tailFor(stage, pick.box, s) }
  const box = put(
    cx < screen.x + screen.w / 2 ? hi.x - w : lo.x,
    cy < screen.y + screen.h / 2 ? hi.y - h : lo.y,
  )
  return { box, tail: tailFor(stage, box, s) }
}

/**
 * Where the subtitle goes: across the bottom of the film, as subtitles do,
 * unless that is where the subject is — then across the top.
 */
function subtitleSpot(screen: Rect, hole: Rect | null, w: number, h: number, m: number): Rect {
  const x = screen.x + (screen.w - w) / 2
  const low = { x, y: screen.y + screen.h - h - m, w, h }
  const high = { x, y: screen.y + m, w, h }
  return hole && overlaps(low, hole) && !overlaps(high, hole) ? high : low
}

/** Skins that take the stage apart: the film on one side, the words on the other. */
type Split = { area: Rect; side: Rect; at: 'left' | 'right' | 'top' | 'below' }

/**
 * The stage, divided.
 *
 * Headline puts its column on the left, where a reader starts. Ring puts it
 * on the side its subject leans towards, so the leader line is short and
 * crosses as little of the page as it can. A square or tall stage has no
 * side to spare: headline goes on top, ring underneath, in a band as tall
 * as its words (`need`) against a film of the shot's own shape (`aspect`).
 */
function splitStage(
  stage: Stage, panel: Panel, rect: ShotRect | null, footerH: number, pad: number,
  need = stage.h * 0.3, aspect = 1.6,
): Split {
  const wide = stage.w / stage.h > 1.2
  const top = pad
  const bottom = stage.h - footerH
  if (wide) {
    const colW = stage.w * (panel === 'headline' ? 0.34 : 0.28)
    const gap = pad * 0.7
    const leftSide = panel === 'headline' || (!!rect && rect.x + rect.w / 2 < 0.5)
    const side: Rect = {
      x: leftSide ? pad : stage.w - pad - colW, y: top, w: colW, h: bottom - top,
    }
    const area: Rect = {
      x: leftSide ? side.x + colW + gap : pad, y: top,
      w: stage.w - pad * 2 - colW - gap, h: bottom - top,
    }
    return { area, side, at: leftSide ? 'left' : 'right' }
  }
  const onTop = panel === 'headline'
  const { film, band } = bandStage(stage, aspect, footerH, pad, need, onTop)
  return { area: film, side: band, at: onTop ? 'top' : 'below' }
}

/**
 * The film and a band of words, stacked: the band as tall as its words
 * (`need`), the film as large as the rest allows at its own shape, the pair
 * centred between the top and the footer. A band of a fixed share of the
 * stage left a third of a square post empty under a one-line caption.
 */
function bandStage(
  stage: Stage, aspect: number, footerH: number, pad: number, need: number, onTop = false,
): { film: Rect; band: Rect } {
  const top = pad
  const bottom = stage.h - footerH
  const gap = stage.h * 0.025
  const full = stage.w - pad * 2
  const words = Math.min(need, (bottom - top) * 0.5)
  let w = full
  let h = w / aspect
  const room = Math.max(1, bottom - top - words - gap)
  if (h > room) {
    h = room
    w = h * aspect
  }
  const y = top + Math.max(0, bottom - top - h - gap - words) / 2
  const film: Rect = { x: pad + (full - w) / 2, y: onTop ? y + words + gap : y, w, h }
  const band: Rect = { x: pad, y: onTop ? y : y + h + gap, w: full, h: words }
  return { film, band }
}

/** How tall a band must be for this caption in this skin, `width` across. */
function bandNeed(g: CanvasRenderingContext2D, stage: Stage, c: Callout, width: number): number {
  const em = unit(stage)
  g.save()
  try {
    switch (stage.panel) {
      // The tip stands a little below the film's edge, room for its tail.
      case 'tip': return tipWords(g, stage, c, Math.min(width, 640 * em), true).h + stage.w * 0.016
      case 'subtitle': return subtitleWords(g, stage, c, width, true).h
      case 'chapter': return chapterWords(g, stage, c, width).blockH
      case 'numbered': return numberedWords(g, stage, c, width, true).h
      case 'headline': return headlineWords(g, stage, c, width, true).blockH
      case 'ring': return ringWords(g, stage, c, width - 12 * em, true).blockH
      default: return calloutHeight(g, stage, c, width)
    }
  } finally {
    g.restore()
  }
}

/** The panel every boxed skin stands on: fill, a hairline, and a shadow over a picture. */
function slab(
  g: CanvasRenderingContext2D, stage: Stage, r: Rect, radius: number,
  edge: string, shadow = true, fill = stage.theme.panel,
) {
  g.save()
  if (shadow) {
    g.shadowColor = 'rgba(0,0,0,0.30)'
    g.shadowBlur = radius * 3
    g.shadowOffsetY = radius * 0.8
  }
  g.fillStyle = fill
  rr(g, r.x, r.y, r.w, r.h, radius)
  g.fill()
  g.restore()
  g.save()
  g.strokeStyle = edge
  g.lineWidth = Math.max(1, stage.w * 0.0009)
  rr(g, r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1, radius)
  g.stroke()
  g.restore()
}

/** A filled circle carrying the step number. */
function badge(g: CanvasRenderingContext2D, stage: Stage, at: Pt, r: number, n: number) {
  const t = stage.theme
  g.save()
  g.fillStyle = t.lanes[0]
  g.beginPath()
  g.arc(at.x, at.y, r, 0, Math.PI * 2)
  g.fill()
  g.fillStyle = inkOn(t, t.lanes[0])
  g.font = font(stage, r * 1.05, 700)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillText(String(n), at.x, at.y + r * 0.05)
  g.restore()
}

/** A leader: a hairline with a dot where it lands. */
function leader(g: CanvasRenderingContext2D, stage: Stage, from: Pt, to: Pt) {
  const t = stage.theme
  g.save()
  g.strokeStyle = t.lanes[0]
  g.lineWidth = Math.max(1.5, stage.w * 0.0012)
  g.beginPath()
  g.moveTo(from.x, from.y)
  g.lineTo(to.x, to.y)
  g.stroke()
  g.fillStyle = t.lanes[0]
  g.beginPath()
  g.arc(to.x, to.y, Math.max(2.5, stage.w * 0.0024), 0, Math.PI * 2)
  g.fill()
  g.restore()
}

/** Title over text, left-aligned, from `y` (the first baseline); returns where it stopped. */
function stack(
  g: CanvasRenderingContext2D, stage: Stage, x: number, y: number, width: number,
  title: string[], titleSize: number, text: string[], textSize: number,
  ink: string, muted: string,
): number {
  g.fillStyle = ink
  g.font = font(stage, titleSize, 650)
  for (const line of title) {
    g.fillText(line, x, y)
    y += titleSize * 1.2
  }
  y += textSize * 0.35 - titleSize * 0.2
  g.fillStyle = muted
  g.font = font(stage, textSize, 400)
  for (const line of text) {
    y += textSize * 1.1
    g.fillText(line, x, y)
    y += textSize * 0.42
  }
  return y
}

/** How tall `stack` will be for these lines, from the top of the first. */
const stackHeight = (titleLines: number, titleSize: number, textLines: number, textSize: number) =>
  textLines
    ? titleSize * (0.75 + titleLines * 1.2) + textSize * (textLines * 1.52 + 0.18)
    : titleSize * (titleLines * 1.2)

/* tip — a tooltip on the subject, its tail on the spotlight's ring */

/** The tip's words at width `w`, and how tall the box around them is. */
function tipWords(g: CanvasRenderingContext2D, stage: Stage, c: Callout, w: number, banded: boolean) {
  const em = unit(stage)
  const pad = 18 * em
  const textSize = 17 * em
  const inner = w - pad * 2
  // A long title steps down a size before it takes a third line.
  const titleSize = fitSize(g, c.title, inner, 2, 22 * em, 19 * em, 650, stage.face)
  const title = lines(g, c.title, inner, 3)
  g.font = font(stage, textSize, 400)
  const text = lines(g, c.text, inner, banded ? 3 : 4)
  const h = pad * 2 + stackHeight(title.length, titleSize, text.length, textSize)
  return { pad, textSize, inner, titleSize, title, text, h }
}

function drawTip(
  g: CanvasRenderingContext2D, stage: Stage, screen: Rect, hole: Rect | null,
  band: Rect | null, c: Callout, avoid: Rect[],
) {
  const t = stage.theme
  const em = unit(stage)
  const w = band ? Math.min(band.w, 640 * em) : Math.min(460 * em, screen.w * 0.46)
  const { pad, textSize, inner, titleSize, title, text, h } = tipWords(g, stage, c, w, !!band)
  const radius = Math.max(5, 7 * em)

  let box: Rect
  let tail: Tail | null
  if (band) {
    const s = hole && within(hole, screen)
    const cx = s ? s.x + s.w / 2 : band.x + w / 2
    box = {
      x: clamp(cx - w / 2, band.x, band.x + band.w - w),
      y: band.y + stage.w * 0.016,
      w, h: Math.min(h, band.h - stage.w * 0.016),
    }
    tail = s ? tailFor(stage, box, s) : null
  } else {
    ({ box, tail } = tipLayout(stage, screen, hole, w, h, avoid))
  }

  if (tail) leader(g, stage, tail.apex, tail.end)
  slab(g, stage, box, radius, t.lanes[0])
  if (tail) {
    // The triangle over the box's own hairline, so box and tail are one shape.
    g.save()
    g.fillStyle = t.panel
    g.strokeStyle = t.lanes[0]
    g.lineWidth = Math.max(1, stage.w * 0.0009)
    g.beginPath()
    g.moveTo(tail.a.x, tail.a.y)
    g.lineTo(tail.apex.x, tail.apex.y)
    g.lineTo(tail.b.x, tail.b.y)
    g.closePath()
    g.fill()
    g.beginPath()
    g.moveTo(tail.a.x, tail.a.y)
    g.lineTo(tail.apex.x, tail.apex.y)
    g.lineTo(tail.b.x, tail.b.y)
    g.stroke()
    g.restore()
  }
  g.save()
  rr(g, box.x, box.y, box.w, box.h, radius)
  g.clip()
  stack(g, stage, box.x + pad, box.y + pad + titleSize * 0.95, inner,
    title, titleSize, text, textSize, t.ink, t.muted)
  g.restore()
}

/* subtitle — under the film, centred, the title as a small kicker */

/** The subtitle's words in a room `roomW` wide, and the box around them. */
function subtitleWords(g: CanvasRenderingContext2D, stage: Stage, c: Callout, roomW: number, banded: boolean) {
  const em = unit(stage)
  const max = Math.min(roomW * (banded ? 0.92 : 0.72), 1100 * em)
  const kick = 15 * em
  const size = fitSize(g, c.text, max, 2, 29 * em, 22 * em, 500, stage.face)
  g.font = font(stage, size, 500)
  const body = lines(g, c.text, max, 3)
  const widest = Math.max(...body.map((l) => g.measureText(l).width))
  g.font = font(stage, kick, 700)
  g.letterSpacing = `${kick * 0.14}px`
  const kickW = Math.min(max, g.measureText(c.title.toUpperCase()).width)
  g.letterSpacing = '0px'
  const padX = 26 * em
  const padY = 16 * em
  const w = Math.max(widest, kickW) + padX * 2
  const h = padY * 2 + kick * 1.65 + size * 1.05 + (body.length - 1) * size * 1.32 + size * 0.25
  return { max, kick, size, body, padY, w, h }
}

function drawSubtitle(
  g: CanvasRenderingContext2D, stage: Stage, screen: Rect, hole: Rect | null,
  band: Rect | null, c: Callout,
) {
  const t = stage.theme
  const em = unit(stage)
  const room = band ?? screen
  const { max, kick, size, body, padY, w, h } = subtitleWords(g, stage, c, room.w, !!band)
  const m = stage.w * 0.022
  const box = band
    ? { x: band.x + (band.w - w) / 2, y: band.y + (band.h - h) / 2, w, h }
    : subtitleSpot(screen, hole, w, h, m)

  g.save()
  g.globalAlpha *= 0.94
  slab(g, stage, box, Math.max(5, 8 * em), t.rule, !band)
  g.restore()
  const cx = box.x + box.w / 2
  let y = box.y + padY + kick * 0.9
  g.save()
  rr(g, box.x, box.y, box.w, box.h, 8 * em)
  g.clip()
  kicker(g, stage, lines(g, c.title, max, 1)[0] ?? '', cx, y, kick, accentInk(t, t.panel), 'center')
  y += kick * 0.75 + size * 1.05
  g.fillStyle = t.ink
  g.font = font(stage, size, 500)
  g.textAlign = 'center'
  for (const line of body) {
    g.fillText(line, cx, y)
    y += size * 1.32
  }
  g.restore()
}

/* headline — a statement in a column, the page smaller beside it */

/** The headline's words at `width`, and how tall the block is. */
function headlineWords(g: CanvasRenderingContext2D, stage: Stage, c: Callout, width: number, across: boolean) {
  const em = unit(stage)
  const kick = 16 * em
  const titleMax = across ? 2 : 4
  const titleSize = fitSize(g, c.title, width, titleMax, (across ? 52 : 58) * em, 30 * em, 700, stage.face)
  g.font = font(stage, titleSize, 700)
  const title = lines(g, c.title, width, titleMax)
  const textSize = (across ? 20 : 21) * em
  g.font = font(stage, textSize, 400)
  const text = lines(g, c.text, width, across ? 3 : 6)
  const rule = 4 * em
  const blockH = rule + kick * 2.6 + title.length * titleSize * 1.12 + textSize * 1.1
    + text.length * textSize * 1.5
  return { kick, titleSize, title, textSize, text, rule, blockH }
}

function drawHeadline(
  g: CanvasRenderingContext2D, stage: Stage, split: Split, screen: Rect, c: Callout,
) {
  const t = stage.theme
  const em = unit(stage)
  const col = split.side
  const across = split.at === 'top'
  const inset = across ? 0 : col.w * 0.04
  const width = col.w - inset * 2
  const { kick, titleSize, title, textSize, text, rule, blockH } = headlineWords(g, stage, c, width, across)
  const centre = across ? col.y + col.h / 2 : screen.y + screen.h / 2
  let y = clamp(centre - blockH / 2, col.y, Math.max(col.y, col.y + col.h - blockH))
  const x = col.x + inset

  g.fillStyle = t.lanes[0]
  g.fillRect(x, y, 44 * em, rule)
  y += rule + kick * 2
  kicker(g, stage, `${c.chapter}  ·  ${c.step.replace(/\s/g, '')}`, x, y, kick, accentInk(t, groundOf(t)))
  y += kick * 0.6
  g.fillStyle = t.ink
  g.font = font(stage, titleSize, 700)
  for (const line of title) {
    y += titleSize * 1.12
    g.fillText(line, x, y - titleSize * 0.12)
  }
  y += textSize * 1.1
  g.fillStyle = t.muted
  g.font = font(stage, textSize, 400)
  for (const line of text) {
    y += textSize * 1.5
    g.fillText(line, x, y - textSize * 0.4)
  }
}

/* chapter — the chapter, the title, one line, top-left over a soft fade */

/** The chapter's words at `width`, and how tall the block is. */
function chapterWords(g: CanvasRenderingContext2D, stage: Stage, c: Callout, width: number) {
  const em = unit(stage)
  const kick = 15 * em
  const titleSize = fitSize(g, c.title, width, 2, 42 * em, 26 * em, 700, stage.face)
  g.font = font(stage, titleSize, 700)
  const title = lines(g, c.title, width, 2)
  const textSize = fitSize(g, c.text, width, 1, 22 * em, 17 * em, 400, stage.face)
  g.font = font(stage, textSize, 400)
  const text = lines(g, c.text, width, 2)
  const blockH = kick * 1.9 + title.length * titleSize * 1.12 + textSize * 0.55 + text.length * textSize * 1.45
  return { kick, titleSize, title, textSize, text, blockH }
}

function drawChapter(
  g: CanvasRenderingContext2D, stage: Stage, screen: Rect, hole: Rect | null,
  band: Rect | null, c: Callout, place: Place = 'auto',
) {
  const t = stage.theme
  const em = unit(stage)
  const ground = groundOf(t)
  const room = band ?? screen
  const pad = band ? 0 : 30 * em
  const width = Math.min(room.w - pad * 2, band ? room.w : room.w * 0.64)
  const { kick, titleSize, title, textSize, text, blockH } = chapterWords(g, stage, c, width)

  // Top, unless the subject is up there and the bottom is clear. "Up
  // there" is the whole fade, not only the words: a subject just under
  // the words (the group-by pills, the architecture's mode pills) sat in
  // the dark half of the fade, ringed and unreadable.
  const topBlock = { x: room.x, y: room.y, w: width + pad * 2, h: blockH + pad * 2 }
  const lowBlock = { ...topBlock, y: room.y + room.h - topBlock.h }
  const reach = Math.min(screen.h * 0.7, topBlock.h * 2.3)
  const topFade = { x: screen.x, y: screen.y, w: screen.w, h: reach * 0.75 }
  const lowFade = { ...topFade, y: screen.y + screen.h - topFade.h }
  // A short page keeps all it has at the top (the prompts, the starred
  // things); with no subject to steer by, the beat says so with "bottom".
  const low = !band && (place === 'bottom'
    || (!!hole && overlaps(topFade, hole) && !overlaps(lowFade, hole)))

  if (!band) {
    // The fade: the page's ground colour, solid behind the words and gone
    // well before the middle of the picture. Vertical, for the encoder.
    const y0 = low ? screen.y + screen.h : screen.y
    const y1 = low ? y0 - reach : y0 + reach
    const grad = g.createLinearGradient(0, y0, 0, y1)
    grad.addColorStop(0, rgba(ground, 0.95))
    grad.addColorStop(clamp(topBlock.h / reach), rgba(ground, 0.88))
    grad.addColorStop(1, rgba(ground, 0))
    g.save()
    rr(g, screen.x, screen.y, screen.w, screen.h, Math.max(6, stage.w * 0.008))
    g.clip()
    g.fillStyle = grad
    g.fillRect(screen.x, Math.min(y0, y1), screen.w, reach)
    g.restore()
  }

  const x = room.x + pad
  let y = (low ? lowBlock.y : band ? room.y + (room.h - blockH) / 2 : topBlock.y) + pad + kick
  kicker(g, stage, c.chapter, x, y, kick, accentInk(t, ground))
  y += kick * 0.9
  g.fillStyle = t.ink
  g.font = font(stage, titleSize, 700)
  for (const line of title) {
    y += titleSize * 1.12
    g.fillText(line, x, y - titleSize * 0.14)
  }
  y += textSize * 0.55
  g.save()
  g.fillStyle = t.ink
  g.globalAlpha *= 0.82
  g.font = font(stage, textSize, 400)
  for (const line of text) {
    y += textSize * 1.45
    g.fillText(line, x, y - textSize * 0.4)
  }
  g.restore()
}

/* ring — a numbered ring on the subject, a leader to the words beside the film */

/** Where the ring's number sits: the hole's corner that faces the words. */
function ringBadge(split: Split, hole: Rect, ring: number): Pt {
  const x = split.at === 'left' || split.at === 'below' ? hole.x - ring : hole.x + hole.w + ring
  const y = split.at === 'below' ? hole.y + hole.h + ring : hole.y - ring
  return { x, y }
}

/** The ring's words at `width`, under the number's row, and how tall the block is. */
function ringWords(g: CanvasRenderingContext2D, stage: Stage, c: Callout, width: number, across: boolean) {
  const em = unit(stage)
  const r = 15 * em
  const titleSize = fitSize(g, c.title, width, 3, 28 * em, 20 * em, 650, stage.face)
  g.font = font(stage, titleSize, 650)
  const title = lines(g, c.title, width, 3)
  const textSize = 17 * em
  g.font = font(stage, textSize, 400)
  const text = lines(g, c.text, width, across ? 2 : 7)
  const row = r * 2 + 16 * em
  const blockH = row + stackHeight(title.length, titleSize, text.length, textSize)
  return { titleSize, title, textSize, text, row, blockH }
}

function drawRing(
  g: CanvasRenderingContext2D, stage: Stage, split: Split, screen: Rect, hole: Rect | null,
  c: Callout,
) {
  const t = stage.theme
  const em = unit(stage)
  const col = split.side
  const r = 15 * em
  const across = split.at === 'below'
  const inset = across ? 6 * em : col.w * 0.05
  const x = col.x + inset
  const width = col.w - inset * 2
  const { titleSize, title, textSize, text, row, blockH } = ringWords(g, stage, c, width, across)

  const s = hole && within(hole, screen)
  const on = s ? ringBadge(split, s, ringPad(stage)) : null
  const want = across
    ? col.y + (col.h - blockH) / 2
    : (on ? on.y - r : screen.y + screen.h / 2 - blockH / 2)
  const top = clamp(want, col.y, Math.max(col.y, col.y + col.h - blockH))
  const mine = { x: x + r, y: top + r }

  // The number heads the block on a row of its own, so the leader reaches
  // it along that row and never crosses a word.
  if (on) {
    const dock = across
      ? { x: on.x, y: mine.y }
      : { x: split.at === 'left' ? col.x + col.w : col.x, y: mine.y }
    g.save()
    g.strokeStyle = t.lanes[0]
    g.lineWidth = Math.max(1.5, stage.w * 0.0012)
    g.beginPath()
    g.moveTo(on.x, on.y)
    g.lineTo(dock.x, dock.y)
    g.lineTo(mine.x, mine.y)
    g.stroke()
    g.restore()
    badge(g, stage, on, r, c.index + 1)
  }
  badge(g, stage, mine, r, c.index + 1)
  if (!on) kicker(g, stage, c.chapter, mine.x + r + 12 * em, mine.y + 5 * em, 14 * em, accentInk(t, groundOf(t)))
  stack(g, stage, x, top + row + titleSize * 0.95, width, title, titleSize, text, textSize, t.ink, t.muted)
}

/* numbered — the step as a big number, the title, the text, a tick per step */

/** The numbered card's words at width `w`, and how tall the card is. */
function numberedWords(g: CanvasRenderingContext2D, stage: Stage, c: Callout, w: number, banded: boolean) {
  const em = unit(stage)
  const pad = 22 * em
  const inner = w - pad * 2
  const num = 46 * em
  const textSize = 17 * em
  const titleSize = fitSize(g, c.title, inner, 2, 24 * em, 20 * em, 650, stage.face)
  const title = lines(g, c.title, inner, 3)
  g.font = font(stage, textSize, 400)
  const text = lines(g, c.text, inner, banded ? 3 : 4)
  const tick = 4 * em
  const h = pad * 2 + num * 0.95 + titleSize * 0.7
    + stackHeight(title.length, titleSize, text.length, textSize) + pad * 0.9 + tick
  return { inner, num, textSize, titleSize, title, text, tick, h }
}

function drawNumbered(
  g: CanvasRenderingContext2D, stage: Stage, screen: Rect, hole: Rect | null,
  band: Rect | null, place: Place, c: Callout, avoid: Rect[],
) {
  const t = stage.theme
  const em = unit(stage)
  const pad = 22 * em
  const w = band ? band.w : cardSize(stage, place, 'card').w
  const { inner, num, textSize, titleSize, title, text, tick, h } = numberedWords(g, stage, c, w, !!band)
  const box = band
    ? { ...band, y: band.y + Math.max(0, (band.h - h) / 2), h: Math.min(h, band.h) }
    : calloutBox(stage, screen, hole, place, 'card', avoid, { w, h })
  const radius = Math.max(6, 9 * em)
  slab(g, stage, box, radius, t.rule, !band)

  const x = box.x + pad
  let y = box.y + pad + num * 0.8
  const accent = accentInk(t, t.panel)
  g.fillStyle = accent
  g.font = font(stage, num, 700)
  const n = String(c.index + 1).padStart(2, '0')
  g.fillText(n, x, y)
  const nw = g.measureText(n).width
  g.fillStyle = t.dim
  g.font = font(stage, num * 0.42, 600)
  g.fillText(`/ ${String(c.of).padStart(2, '0')}`, x + nw + 8 * em, y)
  kicker(g, stage, c.chapter, box.x + box.w - pad, y - num * 0.5, 13 * em, t.muted, 'right')
  y += num * 0.15 + titleSize * 0.7
  g.save()
  rr(g, box.x, box.y, box.w, box.h, radius)
  g.clip()
  stack(g, stage, x, y + titleSize * 0.95, inner, title, titleSize, text, textSize, t.ink, t.muted)

  // A tick per step: done, this one filling, still to come.
  const gap = Math.max(2, 4 * em)
  const each = (inner - gap * (c.of - 1)) / c.of
  const ty = box.y + box.h - pad * 0.9 - tick
  for (let i = 0; i < c.of; i++) {
    const tx = x + i * (each + gap)
    g.fillStyle = i < c.index ? t.lanes[0] : t.rule
    g.fillRect(tx, ty, each, tick)
    if (i === c.index) {
      g.fillStyle = t.lanes[0]
      g.fillRect(tx, ty, each * clamp(c.progress), tick)
    }
  }
  g.restore()
}

/** The panels drawn by their own hand rather than by drawCallout. */
const SKINS = new Set<Panel>(['tip', 'subtitle', 'headline', 'chapter', 'ring', 'numbered'])

/**
 * Where the card goes: over the screenshot, or in a band beneath it.
 *
 * Over is right for most beats — the page has quiet corners and the tour
 * feels like it is happening on the product. It is wrong when the thing
 * being described fills the middle of the screen, which is exactly when the
 * card would cover it. A tall or square stage always uses the band.
 *
 * So does the bar, on any stage: a strip as wide as the film has no quiet
 * corner to sit in. Laid over the page it took a third of the picture, the
 * board's columns, the open task, the "next turn" its own caption names.
 */
function overlays(stage: Stage, beat: Beat) {
  return stage.w / stage.h > 1.2 && stage.panel !== 'bar' && (beat.place ?? 'auto') !== 'below'
}

export function drawTour(
  g: CanvasRenderingContext2D, script: Script, t: number, stage: Stage,
) {
  g.save()
  g.textBaseline = 'alphabetic'
  g.textAlign = 'left'
  paintGround(g, stage)

  const cue = cueAt(script, t)
  if (cue.phase === 'title') {
    if (stage.bookends) drawOpening(g, stage, script, cue.u)
    g.restore()
    return
  }
  if (cue.phase === 'end') {
    if (stage.bookends) drawEnding(g, stage, script, cue.u)
    g.restore()
    return
  }

  drawGround(g, stage, script)
  const { slot, u, of } = cue
  const beat = slot.beat
  const shot = stage.shots.get(beat.id)
  const footerH = stage.footer ? stage.h * 0.075 : stage.h * 0.02
  const pad = stage.w * 0.035
  const step = `${slot.index + 1} / ${of}`
  const q = Math.round(u * PROGRESS_STEPS) / PROGRESS_STEPS

  if (kindOf(beat) !== 'page') {
    // Drawn, not photographed: the same fade and footer as a page.
    const fade = clamp(u / 0.1) * (1 - clamp((u - 0.93) / 0.07))
    if (kindOf(beat) === 'slide') drawSlide(g, stage, beat, u, fade, footerH)
    else drawTerminal(g, stage, beat, u, fade, footerH)
    if (stage.footer) drawFooter(g, stage, beat.chapter, step, (slot.index + q) / of)
    g.restore()
    return
  }

  if (!shot || !shot.frames.length) {
    g.fillStyle = stage.theme.dim
    g.font = font(stage, stage.w * 0.02, 600)
    g.textAlign = 'center'
    g.fillText(tr('No picture for "{id}". Capture the pictures first.', { id: beat.id }), stage.w / 2, stage.h / 2)
    g.textAlign = 'left'
    g.restore()
    return
  }

  // Progress in steps, not in a smooth slide. A bar that advances by one
  // pixel per frame makes every frame of a still beat different, and the
  // encoder can no longer hold one picture for five seconds — which on a
  // seventeen-beat tour is the difference between a post-sized GIF and a
  // fifteen-megabyte one. Nothing else on a still beat moves; this must not
  // either.
  const card: Callout = {
    title: beat.title, text: beat.text, step, progress: q,
    chapter: beat.chapter, index: slot.index, of,
  }

  const skin = stage.panel
  const splits = skin === 'headline' || skin === 'ring'
  const banded = splits ? stage.w / stage.h <= 1.2 : !overlays(stage, beat)
  const need = banded ? bandNeed(g, stage, card, stage.w - pad * 2) : 0
  const split = splits
    ? splitStage(stage, skin, shot.rect, footerH, pad, need, shot.w / shot.h)
    : null
  const stacked = !split && banded ? bandStage(stage, shot.w / shot.h, footerH, pad, need) : null
  const area: Rect = split?.area ?? stacked?.film ?? {
    x: pad,
    y: pad,
    w: stage.w - pad * 2,
    h: stage.h - pad - footerH,
  }
  const box = screenBox(stage, shot, area)
  const view = viewFor(beat, shot, box.w / box.h, u)

  // An action plays early and then holds. The gesture is over by halfway,
  // which leaves the second half of the beat showing what it produced — the
  // opened panel, the card in its new column — for as long as it takes to
  // read the sentence. Running the burst late leaves the reader looking at
  // the state before the click for most of the beat.
  // A demonstration (steps) spreads its frames over the whole beat instead,
  // with a moment on the first and the last.
  const burst = shot.frames.length
  const frame = burst <= 1 ? 0
    : beat.steps?.length ? Math.round(clamp((u - 0.1) / 0.8) * (burst - 1))
      : Math.round(clamp((u - 0.15) / 0.35) * (burst - 1))

  drawScreen(g, stage, shot, box, view, frame)

  const at = shot.pointer[frame] ?? null
  if (at) {
    // The tap ring runs over the two frames after a click, and never on a
    // drag — a drag has the card to show for itself.
    const tapping = at.down && !shot.grab
    drawHand(g, stage, box, view, at, shot.grab, tapping ? 0.35 : 0)
  }

  const wantsLight = shot.rect && beat.zoom !== 'full'
  if (wantsLight && shot.rect) {
    const settle = beat.zoom === 'push' ? (beat.steps?.length ? clamp((u - 0.55) / 0.2) : clamp((u - 0.4) / 0.2)) : 1
    spotlight(g, stage, box, focusOnStage(box, view, shot.rect), settle)
  }

  const fade = clamp(u / 0.1) * (1 - clamp((u - 0.93) / 0.07))
  const lit = stage.highlight
    ? shot.nav.map((at) => focusOnStage(box, view, at))
    : []
  for (const at of lit) drawNav(g, stage, box, view, at, fade)

  const hole = wantsLight && shot.rect ? focusOnStage(box, view, shot.rect) : null
  const place = beat.place ?? 'auto'
  const band: Rect | null = stacked?.band ?? null
  if (fade > 0.01) {
    g.save()
    g.globalAlpha = fade
    if (split && skin === 'headline') drawHeadline(g, stage, split, box, card)
    else if (split) drawRing(g, stage, split, box, hole, card)
    else if (skin === 'tip') drawTip(g, stage, box, hole, band, card, lit)
    else if (skin === 'subtitle') drawSubtitle(g, stage, box, hole, band, card)
    else if (skin === 'chapter') drawChapter(g, stage, box, hole, band, card, place)
    else if (skin === 'numbered') drawNumbered(g, stage, box, hole, band, place, card, lit)
    g.restore()
  }
  if (!SKINS.has(skin)) {
    drawCallout(g, stage, band ?? calloutBox(stage, box, hole, place, skin, lit), card, fade, !band)
  }

  if (stage.footer) {
    drawFooter(g, stage, beat.chapter, step, (slot.index + q) / of)
  }
  g.restore()
}

/** Stage sizes, by the shape a post wants. */
export const ASPECTS: Array<{ id: string; name: string; w: number; h: number; note: string }> = [
  { id: '16:9', name: tr('Wide'), w: 1600, h: 900, note: tr('an article, a README, a slide') },
  { id: '1:1', name: tr('Square'), w: 1080, h: 1080, note: tr('a feed') },
  { id: '9:16', name: tr('Tall'), w: 900, h: 1600, note: tr('a phone') },
]

export const stageSize = (aspect: string) =>
  ASPECTS.find((a) => a.id === aspect) ?? ASPECTS[0]

export const __test = {
  wrap, focusView, screenBox, lerpRect, calloutBox,
  tipLayout, tailFor, subtitleSpot, splitStage, bandStage, bandNeed, contrast, accentInk,
}
