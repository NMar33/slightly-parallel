import { describe, expect, it, beforeAll } from 'vitest'

import metricsRaw from '../../../../brand/kit/metrics.json?raw'

import { SP_LEAN_DEG, SP_LEAN_INDEX, SP_METRICS, SP_WORDMARK, SP_WORDMARK_WIDTH } from './spmark'
import { drawPlate, drawSheet, drawWordmark, plateWidth, sheetInk } from './spcard'

/**
 * spmark.ts is written by brand/kit/build.py from metrics.json. A wordmark
 * changed in the kit and not rebuilt shows here; so does a drawing that
 * stops drawing the glyphs, the lean or the construction.
 */
const kit = JSON.parse(metricsRaw)

type Call = { op: string; args: unknown[]; fill?: string; rotated: boolean }

/** A canvas that records what is drawn: fills with their colour, whether a rotation was in force. */
function recorder() {
  const calls: Call[] = []
  const stack: Array<{ fill: string; rot: number }> = []
  let fill = '#000', rot = 0
  const g = {
    calls,
    set fillStyle(v: string) { fill = v }, get fillStyle() { return fill },
    strokeStyle: '', lineWidth: 1, font: '', textAlign: 'left', letterSpacing: '0px',
    save() { stack.push({ fill, rot }) },
    restore() { const s = stack.pop(); if (s) { fill = s.fill; rot = s.rot } },
    translate() {}, scale() {},
    rotate(a: number) { rot += a },
    fill(...args: unknown[]) { calls.push({ op: 'fill', args, fill, rotated: rot !== 0 }) },
    stroke() { calls.push({ op: 'stroke', args: [], rotated: rot !== 0 }) },
    fillText(...args: unknown[]) { calls.push({ op: 'text', args, fill, rotated: rot !== 0 }) },
    beginPath() {}, moveTo() {}, lineTo() {}, arc() {}, arcTo() {}, closePath() {}, strokeRect() {}, setLineDash() {},
  }
  return g as unknown as CanvasRenderingContext2D & { calls: Call[] }
}

beforeAll(() => {
  // jsdom has no Path2D: a stand-in that keeps its path data.
  ;(globalThis as unknown as { Path2D: unknown }).Path2D = class { constructor(public d: string) {} }
})

describe('the brand drawing', () => {
  it('uses the outlines the kit has now', () => {
    const lower = kit.sg.lower
    expect(SP_WORDMARK.map((r) => r.d)).toEqual(lower.recs.map((r: { d: string }) => r.d))
    expect(SP_WORDMARK.map((r) => r.ch).join('')).toBe('slightly parallel')
    expect(SP_WORDMARK_WIDTH).toBeCloseTo(lower.width, 3)
    expect(SP_METRICS.xh).toBeCloseTo(kit.sg.metrics.xh, 3)
    expect(SP_WORDMARK[SP_LEAN_INDEX].ch).toBe('l')
  })

  it('draws every glyph, and only the second l of parallel leans, in the lean colour', () => {
    const g = recorder()
    const width = drawWordmark(g, 0, 100, 50, '#F2F4F3', '#D0694F')
    const fills = g.calls.filter((c) => c.op === 'fill')
    expect(fills).toHaveLength(SP_WORDMARK.length)
    expect(width).toBeCloseTo(SP_WORDMARK_WIDTH * 50, 6)
    fills.forEach((c, i) => {
      expect(c.rotated).toBe(i === SP_LEAN_INDEX)
      expect(c.fill).toBe(i === SP_LEAN_INDEX ? '#D0694F' : '#F2F4F3')
    })
  })

  it('draws the plate: ground, s, p, two stems, the second leaning in the lean colour', () => {
    const g = recorder()
    const w = drawPlate(g, 0, 0, 40, '#D0694F')
    expect(w).toBeCloseTo(plateWidth(40), 6)
    const fills = g.calls.filter((c) => c.op === 'fill')
    expect(fills).toHaveLength(5)
    expect(fills.filter((c) => c.rotated).map((c) => c.fill)).toEqual(['#D0694F'])
  })

  it('labels the construction with the lean and the metrics, and fills the title block', () => {
    const g = recorder()
    const said: string[] = []
    drawSheet(g, 1200, 675, 1, sheetInk('#0C0E0E'), (t) => said.push(t), [['PROJECT', 'ALPHA'], ['CARDS', '12']])
    expect(said).toEqual(expect.arrayContaining([`${SP_LEAN_DEG}°`, 'ASCENDER · 732', 'BASELINE · 0', 'PROJECT', 'ALPHA', 'CARDS', '12']))
  })

  it('takes paper ink on a dark ground and ink on a light one', () => {
    expect(sheetInk('#0C0E0E').ink).toBe('#F2F4F3')
    expect(sheetInk('#F6F4EF').ink).toBe('#17181A')
  })
})
