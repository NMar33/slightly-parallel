/**
 * The beats that are not a page: a slide and a terminal.
 *
 * A how-to film needs to say things no page shows — the repository and the
 * command that installs it, "from here on every chat is recorded", the
 * questions a first start raises. A slide is a title and a few lines on
 * the stage's own ground, with room for one picture (a QR code, a
 * diagram). A terminal is a window in which the commands of the caption
 * are typed and their answers appear, in the order written: no real
 * terminal is filmed, so no path of this computer ever reaches the film.
 *
 * Both are drawn from the beat's `title` and `text` alone, so the caption
 * editor edits them like any other beat; the live tour skips them.
 */

import type { Beat } from './script'
import { clamp } from './script'
import type { Stage } from './scene'
import { fitSize, lines, wrap } from './words'

type Rect = { x: number; y: number; w: number; h: number }

const MONO = 'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace'

const font = (stage: Stage, size: number, weight = 400, face = stage.face) => `${weight} ${size}px ${face}`

/** The lines of a caption, as written; blank ones are kept as spacing. */
export const rowsOf = (text: string): string[] => text.replace(/\r/g, '').split('\n').map((s) => s.trimEnd())

/* --------------------------------- slide -------------------------------- */

/**
 * A slide: the chapter as a kicker, the title large, the lines under it.
 * A line that starts with "- " gets a bullet; a line wrapped in backticks
 * is set in mono on a chip, the way a command reads in a README. The
 * lines appear one after another over the first part of the beat, so the
 * eye follows the order they were written in.
 */
export function drawSlide(
  g: CanvasRenderingContext2D, stage: Stage, beat: Beat, u: number, fade: number, footerH: number,
) {
  const pad = stage.w * 0.08
  const image = beat.image ? stage.images?.get(beat.image) ?? null : null
  const column = image ? stage.w * 0.5 : stage.w - pad * 2
  const top = stage.h * 0.17
  const bottom = stage.h - footerH - stage.h * 0.06

  g.save()
  g.globalAlpha = fade
  g.textAlign = 'left'
  g.textBaseline = 'alphabetic'

  // The kicker: the chapter, small capitals in mono.
  let y = top
  if (beat.chapter) {
    const k = stage.w * 0.014
    g.font = font(stage, k, 500, MONO)
    g.fillStyle = stage.theme.muted
    g.letterSpacing = `${k * 0.18}px`
    g.fillText(beat.chapter.toUpperCase(), pad, y)
    g.letterSpacing = '0px'
    y += k * 2.4
  }

  // The title, fitted to three lines.
  const hi = stage.w * 0.052
  const size = beat.title ? fitSize(g, beat.title, column, 3, hi, stage.w * 0.03, 700, stage.face) : hi
  g.font = font(stage, size, 700)
  g.fillStyle = stage.theme.ink
  const titleRows = beat.title ? lines(g, beat.title, column, 3) : []
  for (const row of titleRows) {
    g.fillText(row, pad, y + size)
    y += size * 1.12
  }
  if (titleRows.length) y += size * 0.55

  // The lines, in order, one after another.
  const rows = rowsOf(beat.text).filter((r, i, all) => r || (i > 0 && i < all.length - 1))
  const body = stage.w * 0.021
  const lead = body * 1.55
  let shown = 0
  for (const row of rows) {
    if (y + lead > bottom) break
    const at = clamp((u - 0.08 - shown * 0.035) / 0.06)
    if (!row) { y += lead * 0.6; continue }
    g.save()
    g.globalAlpha = fade * at
    const bullet = row.startsWith('- ')
    const chip = /^`[^`]+`$/.test(row)
    const large = row.startsWith('> ')
    const textOf = bullet || large ? row.slice(2) : chip ? row.slice(1, -1) : row
    let x = pad
    if (bullet) {
      g.fillStyle = stage.theme.down
      g.beginPath()
      g.arc(pad + body * 0.3, y + lead * 0.55, body * 0.16, 0, Math.PI * 2)
      g.fill()
      x = pad + body * 1.1
    }
    if (chip) {
      g.font = font(stage, body * 0.92, 500, MONO)
      const w = g.measureText(textOf).width + body * 1.2
      g.fillStyle = stage.theme.panel
      g.strokeStyle = stage.theme.rule
      g.lineWidth = Math.max(1, stage.w * 0.0008)
      roundRect(g, x, y + lead * 0.12, w, lead * 0.95, body * 0.3)
      g.fill()
      g.stroke()
      g.fillStyle = stage.theme.ink
      g.fillText(textOf, x + body * 0.6, y + lead * 0.72)
      y += lead * 1.15
    } else if (large) {
      // One line, as large as the column allows: a link or a command has no place to wrap.
      const big = fitOne(g, stage, textOf, column, body * 1.5, body * 0.9, 600)
      g.font = font(stage, big, 600)
      g.fillStyle = stage.theme.ink
      g.fillText(textOf, x, y + big * 1.1)
      y += big * 1.5 + lead * 0.3
    } else {
      g.font = font(stage, body, 400)
      g.fillStyle = stage.theme.ink
      const wrapped = wrap(g, textOf, column - (x - pad))
      for (const line of wrapped) {
        g.fillText(line, x, y + lead * 0.72)
        y += lead
      }
    }
    g.restore()
    shown += 1
  }

  // The picture, on the right, kept to its own shape.
  if (image) {
    const box: Rect = { x: pad + column + stage.w * 0.06, y: top, w: stage.w - pad * 2 - column - stage.w * 0.06, h: bottom - top }
    const iw = (image as HTMLImageElement).width || 1
    const ih = (image as HTMLImageElement).height || 1
    const k = Math.min(box.w / iw, box.h / ih, 1.2)
    const w = iw * k
    const h = ih * k
    g.drawImage(image, box.x + (box.w - w) / 2, box.y + (box.h - h) / 2, w, h)
  }
  g.restore()
}

/* ------------------------------- terminal ------------------------------ */

/** One line of a terminal beat, by what it is. */
export type TermLine =
  | { kind: 'command'; text: string }
  | { kind: 'comment'; text: string }
  | { kind: 'output'; text: string }

export function termLines(text: string): TermLine[] {
  return rowsOf(text).map((row) => (
    row.startsWith('$ ') ? { kind: 'command', text: row.slice(2) }
      : row.startsWith('# ') ? { kind: 'comment', text: row.slice(2) }
        : { kind: 'output', text: row }
  ))
}

/** How many characters of each line are on screen at `u`, and where the caret is. */
export function terminalReveal(all: TermLine[], u: number): { chars: number[]; caret: number } {
  // A command costs one unit per character, then a pause before its
  // answer; an answer is printed whole. The whole script fits in the
  // first three quarters of the beat, and the rest holds the result.
  const PAUSE = 10
  const OUTPUT = 5
  const costs = all.map((l) => (l.kind === 'command' ? l.text.length + PAUSE : OUTPUT))
  const total = costs.reduce((a, b) => a + b, 0) || 1
  let budget = clamp((u - 0.06) / 0.7) * total
  const chars: number[] = []
  let caret = -1
  let done = true
  for (let i = 0; i < all.length; i += 1) {
    const line = all[i]
    if (budget <= 0) { chars.push(0); done = false; continue }
    if (line.kind === 'command') {
      const typed = Math.min(line.text.length, Math.floor(budget))
      chars.push(typed)
      if (budget < costs[i]) { caret = i; done = false }
    } else {
      const whole = budget >= costs[i]
      chars.push(whole ? line.text.length : 0)
      if (!whole) done = false
    }
    budget -= costs[i]
  }
  // Everything printed: the caret waits on a new prompt line. Mid-way
  // through an answer there is no caret at all; the next thing is the answer.
  if (done) caret = all.length
  return { chars, caret }
}

export function drawTerminal(
  g: CanvasRenderingContext2D, stage: Stage, beat: Beat, u: number, fade: number, footerH: number,
) {
  const all = termLines(beat.text)
  const { chars, caret } = terminalReveal(all, u)
  const size = stage.w * 0.0168
  const rowH = size * 1.65
  const bar = size * 2.2
  const inset = size * 1.4
  const w = stage.w * 0.8
  const rows = all.length + (caret >= all.length ? 1 : 0)
  // The heading above the window: the beat's title, as a slide sets it.
  const head = beat.title ? stage.w * 0.036 : 0
  const headRoom = head ? head * 2.1 : 0
  const h = Math.min(bar + inset * 2 + rows * rowH, stage.h - footerH - stage.h * 0.12 - headRoom)
  const x = (stage.w - w) / 2
  const y = (stage.h - footerH - h + headRoom) / 2 + stage.h * 0.01

  g.save()
  g.globalAlpha = fade
  g.textAlign = 'left'
  g.textBaseline = 'alphabetic'
  if (head) {
    g.font = font(stage, head, 700)
    g.fillStyle = stage.theme.ink
    g.fillText(beat.title, x, y - head * 0.9)
  }

  // The window.
  g.fillStyle = stage.theme.panel
  g.strokeStyle = stage.theme.rule
  g.lineWidth = Math.max(1, stage.w * 0.001)
  roundRect(g, x, y, w, h, size * 0.7)
  g.fill()
  g.stroke()
  // The title bar: three dots and the name.
  for (let i = 0; i < 3; i += 1) {
    g.fillStyle = stage.theme.dim
    g.beginPath()
    g.arc(x + inset * 0.7 + i * size * 1.1, y + bar / 2, size * 0.3, 0, Math.PI * 2)
    g.fill()
  }
  g.font = font(stage, size * 0.8, 500, MONO)
  g.fillStyle = stage.theme.muted
  g.textAlign = 'center'
  g.fillText('bash', x + w / 2, y + bar / 2 + size * 0.3)
  g.textAlign = 'left'
  g.strokeStyle = stage.theme.rule
  g.beginPath()
  g.moveTo(x, y + bar)
  g.lineTo(x + w, y + bar)
  g.stroke()

  // The lines.
  g.font = font(stage, size, 400, MONO)
  const blink = Math.floor(u * 14) % 2 === 0
  let ly = y + bar + inset + size
  const prompt = '$ '
  const promptW = g.measureText(prompt).width
  for (let i = 0; i < all.length; i += 1) {
    if (ly > y + h - inset * 0.5) break
    const line = all[i]
    const n = chars[i]
    if (line.kind === 'command') {
      if (n === 0 && caret !== i) { continue }
      g.fillStyle = stage.theme.down
      g.fillText(prompt, x + inset, ly)
      g.fillStyle = stage.theme.ink
      const shown = line.text.slice(0, n)
      g.fillText(shown, x + inset + promptW, ly)
      if (caret === i && blink) {
        const cx = x + inset + promptW + g.measureText(shown).width + size * 0.1
        g.fillRect(cx, ly - size * 0.85, size * 0.5, size * 1.05)
      }
    } else if (n > 0) {
      g.fillStyle = line.kind === 'comment' ? stage.theme.dim : stage.theme.muted
      g.fillText(line.text, x + inset, ly)
    } else {
      continue
    }
    ly += rowH
  }
  if (caret >= all.length && ly <= y + h - inset * 0.5) {
    g.fillStyle = stage.theme.down
    g.fillText(prompt, x + inset, ly)
    if (blink) {
      g.fillStyle = stage.theme.ink
      g.fillRect(x + inset + promptW + size * 0.1, ly - size * 0.85, size * 0.5, size * 1.05)
    }
  }
  g.restore()
}

/** The largest size from `hi` down to `lo` at which one unbreakable line fits `max`. */
function fitOne(g: CanvasRenderingContext2D, stage: Stage, text: string, max: number, hi: number, lo: number, weight: number): number {
  for (let size = hi; size > lo; size *= 0.94) {
    g.font = font(stage, size, weight)
    if (g.measureText(text).width <= max) return size
  }
  return lo
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rad = Math.min(r, w / 2, h / 2)
  g.beginPath()
  g.moveTo(x + rad, y)
  g.arcTo(x + w, y, x + w, y + h, rad)
  g.arcTo(x + w, y + h, x, y + h, rad)
  g.arcTo(x, y + h, x, y, rad)
  g.arcTo(x, y, x + w, y, rad)
  g.closePath()
}
