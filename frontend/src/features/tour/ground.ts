/**
 * What is drawn on the ground before a beat: the brand's hand, faintly.
 *
 * A film of slides on a plain dark ground reads as any deck. The identity
 * is a drawing sheet — construction lines, a title block, the monogram on
 * its plate, two stems one of which leans — and a little of it under
 * every beat ties the film to the product without competing with the page
 * in the picture. Each hand is drawn at a low alpha and never moves: a
 * still ground costs the encoder nothing.
 */

import { drawPlate, plateWidth, sheetInk } from '../timelapse/spcard'
import { SP_LEAN_DEG } from '../timelapse/spmark'

import type { Stage } from './scene'
import type { Script } from './script'
import { t } from '../../i18n/scope/shell'

export type Ground = 'plain' | 'grid' | 'marks' | 'rules' | 'plate' | 'stems'

export const GROUNDS: Array<{ id: Ground; name: string; note: string }> = [
  { id: 'plain', name: t('Plain'), note: t('the theme\'s ground alone') },
  { id: 'grid', name: t('Drawing sheet'), note: t('faint construction lines, a margin and a title block in the corner') },
  { id: 'marks', name: t('Sheet marks'), note: t('the margin, crop marks at the corners and the title block; no grid') },
  { id: 'rules', name: t('Spec rules'), note: t('a rule across the top and the bottom with the sheet\'s labels on them, as a specification page') },
  { id: 'plate', name: t('Plate'), note: t('the s∥p monogram on its plate, large and faint, in the lower right') },
  { id: 'stems', name: t('Two stems'), note: t('a hairline down the left margin and the leaning stem in rust; a soft lift of light') },
]

export const groundOf = (s: Script): Ground => s.ground ?? 'plain'

const MONO = 'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace'

const groundHex = (stage: Stage): string => {
  const ground = stage.theme.ground
  return typeof ground === 'string' ? ground : ground.to
}

/** Draws the chosen hand over a ground already painted. */
export function drawGround(g: CanvasRenderingContext2D, stage: Stage, script: Script) {
  const hand = groundOf(script)
  if (hand === 'plain') return
  const inks = sheetInk(groundHex(stage))
  const k = Math.sqrt((stage.w * stage.h) / (1200 * 675))
  g.save()
  if (hand === 'grid') drawGrid(g, stage, script, inks.hair, inks.label, k, true)
  else if (hand === 'marks') drawGrid(g, stage, script, inks.hair, inks.label, k, false)
  else if (hand === 'rules') drawRules(g, stage, script, inks.hair, inks.label, inks.lean, k)
  else if (hand === 'plate') drawPlateMark(g, stage, inks.lean, k)
  else drawStems(g, stage, inks.hair, inks.lean, k)
  g.restore()
}

function drawGrid(
  g: CanvasRenderingContext2D, stage: Stage, script: Script, hair: string, label: string, k: number, grid: boolean,
) {
  const m = stage.w * 0.025
  if (grid) {
    // Construction lines: a fine grid, and every fourth line a little firmer.
    const step = stage.w / 40
    g.strokeStyle = hair
    g.lineWidth = Math.max(1, k * 0.7)
    for (const [every, alpha] of [[1, 0.35], [4, 0.7]] as Array<[number, number]>) {
      g.globalAlpha = alpha
      g.beginPath()
      for (let i = 1, x = step; x < stage.w; i += 1, x += step) if (i % every === 0) { g.moveTo(x, m); g.lineTo(x, stage.h - m) }
      for (let i = 1, y = step; y < stage.h; i += 1, y += step) if (i % every === 0) { g.moveTo(m, y); g.lineTo(stage.w - m, y) }
      g.stroke()
    }
  } else {
    // Crop marks at the corners, outside the margin.
    const len = m * 0.6
    g.strokeStyle = hair
    g.lineWidth = Math.max(1, k)
    g.globalAlpha = 1
    g.beginPath()
    for (const [cx, cy] of [[m, m], [stage.w - m, m], [m, stage.h - m], [stage.w - m, stage.h - m]]) {
      const sx = cx < stage.w / 2 ? -1 : 1
      const sy = cy < stage.h / 2 ? -1 : 1
      g.moveTo(cx + sx * m * 0.25, cy); g.lineTo(cx + sx * (m * 0.25 + len), cy)
      g.moveTo(cx, cy + sy * m * 0.25); g.lineTo(cx, cy + sy * (m * 0.25 + len))
    }
    g.stroke()
  }
  // The margin: the sheet's own frame.
  g.strokeStyle = hair
  g.globalAlpha = 1
  g.lineWidth = Math.max(1, k)
  g.strokeRect(m, m, stage.w - m * 2, stage.h - m * 2)
  // The title block, top right: three rows the way a drawing is labelled.
  const rows: Array<[string, string]> = [
    ['SHEET', script.title || script.name],
    ['SERIES', script.stamp || t('how to')],
    ['FORMAT', `${script.aspect} · ${stage.w}×${stage.h}`],
  ]
  const size = 9 * k
  g.font = `500 ${size}px ${MONO}`
  g.letterSpacing = `${(size * 0.14).toFixed(1)}px`
  const bw = 150 * k
  const bh = size * 2 * rows.length + size
  const x = stage.w - m - bw
  const y = m
  g.strokeRect(x, y, bw, bh)
  g.fillStyle = label
  g.textBaseline = 'alphabetic'
  rows.forEach(([key, value], i) => {
    const ly = y + size * 1.6 + i * size * 2
    g.textAlign = 'left'
    g.fillText(key, x + size * 0.8, ly)
    g.textAlign = 'right'
    g.fillText(short(g, value.toUpperCase(), bw - size * 6.5), x + bw - size * 0.8, ly)
    if (i < rows.length - 1) {
      g.beginPath(); g.moveTo(x, ly + size * 0.6); g.lineTo(x + bw, ly + size * 0.6); g.stroke()
    }
  })
}

function drawRules(
  g: CanvasRenderingContext2D, stage: Stage, script: Script, hair: string, label: string, lean: string, k: number,
) {
  // A specification page: one rule across the top with the labels on it,
  // one across the bottom; the rust accent is a short dash on the top rule.
  const m = stage.w * 0.04
  const top = stage.h * 0.075
  const bottom = stage.h - stage.h * 0.075
  g.strokeStyle = hair
  g.lineWidth = Math.max(1, k)
  g.globalAlpha = 1
  g.beginPath(); g.moveTo(m, top); g.lineTo(stage.w - m, top); g.stroke()
  g.beginPath(); g.moveTo(m, bottom); g.lineTo(stage.w - m, bottom); g.stroke()
  g.strokeStyle = lean
  g.lineWidth = Math.max(2, k * 2)
  g.beginPath(); g.moveTo(m, top); g.lineTo(m + stage.w * 0.06, top); g.stroke()
  const size = 9.5 * k
  g.font = `500 ${size}px ${MONO}`
  g.letterSpacing = `${(size * 0.16).toFixed(1)}px`
  g.fillStyle = label
  g.textBaseline = 'alphabetic'
  g.textAlign = 'left'
  g.fillText('SLIGHTLY PARALLEL', m, top - size * 0.7)
  g.textAlign = 'center'
  g.fillText((script.title || script.name).toUpperCase(), stage.w / 2, top - size * 0.7)
  if (script.stamp) {
    g.textAlign = 'right'
    g.fillText(script.stamp.toUpperCase(), stage.w - m, top - size * 0.7)
  }
}

function short(g: CanvasRenderingContext2D, text: string, max: number): string {
  if (g.measureText(text).width <= max) return text
  let s = text
  while (s.length > 1 && g.measureText(s + '…').width > max) s = s.slice(0, -1)
  return s + '…'
}

function drawPlateMark(g: CanvasRenderingContext2D, stage: Stage, lean: string, k: number) {
  const h = stage.h * 0.62
  const w = plateWidth(h)
  g.globalAlpha = 0.07
  drawPlate(g, stage.w - w * 0.72, stage.h - h * 0.68, h, lean)
  // A hairline across the top, the sheet's edge.
  g.globalAlpha = 0.6
  g.strokeStyle = lean
  g.lineWidth = Math.max(1, k)
  g.beginPath()
  g.moveTo(stage.w * 0.04, stage.h * 0.055)
  g.lineTo(stage.w * 0.96, stage.h * 0.055)
  g.stroke()
}

function drawStems(g: CanvasRenderingContext2D, stage: Stage, hair: string, lean: string, k: number) {
  // A lift of light behind the middle: the page sits on it, the edges stay dark.
  const cx = stage.w * 0.5
  const cy = stage.h * 0.45
  const glow = g.createRadialGradient(cx, cy, 0, cx, cy, stage.w * 0.55)
  glow.addColorStop(0, 'rgba(255,255,255,0.06)')
  glow.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = glow
  g.fillRect(0, 0, stage.w, stage.h)
  // The two stems: a hairline down the left margin, and the second leaning in rust.
  const x = stage.w * 0.04
  g.lineWidth = Math.max(1, k)
  g.strokeStyle = hair
  g.globalAlpha = 0.9
  g.beginPath(); g.moveTo(x, 0); g.lineTo(x, stage.h); g.stroke()
  const len = stage.h * 0.22
  const dx = len * Math.tan((SP_LEAN_DEG * Math.PI) / 180)
  g.strokeStyle = lean
  g.lineWidth = Math.max(2, k * 2.2)
  g.lineCap = 'round'
  g.beginPath(); g.moveTo(x + 10 * k, stage.h * 0.07 + len); g.lineTo(x + 10 * k + dx, stage.h * 0.07); g.stroke()
}
