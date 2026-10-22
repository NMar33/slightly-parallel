/**
 * The yard intro as an opening: drawn on every stage at any second without
 * throwing, its words kept on the stage, and the last second is the drawing
 * of the name — the wordmark filled from its outlines, the l in rust.
 */

import { beforeAll, describe, expect, it } from 'vitest'

import { leadFor } from './BookendPicker'
import { ASPECTS } from './scene'
import { YARD_SECONDS, drawYard } from './yard'

type Word = { text: string; x: number; y: number; w: number; size: number; align: string }

/** A canvas that records each word and each fill. */
function fakeCanvas() {
  const words: Word[] = []
  const fills: string[] = []
  const state: Record<string, unknown> = { font: '10px sans', textAlign: 'left', letterSpacing: '0px', globalAlpha: 1 }
  const saved: Array<Record<string, unknown>> = []
  const sizeOf = () => parseFloat(/([\d.]+)px/.exec(String(state.font))?.[1] ?? '10')
  const width = (text: string) => text.length * sizeOf() * 0.5
  const g = new Proxy(state, {
    get(target, key: string) {
      if (key === 'measureText') return (text: string) => ({ width: width(text) })
      if (key === 'fillText') {
        return (text: string, x: number, y: number) => {
          words.push({ text, x, y, w: width(text), size: sizeOf(), align: String(target.textAlign) })
        }
      }
      if (key === 'fill') return () => { fills.push(String(target.fillStyle)) }
      if (key === 'createLinearGradient' || key === 'createRadialGradient') return () => ({ addColorStop() {} })
      if (key === 'save') return () => saved.push({ ...state })
      if (key === 'restore') return () => Object.assign(state, saved.pop() ?? {})
      if (key in target) return target[key]
      return () => {}
    },
    set(target, key: string, value) {
      target[key] = value
      return true
    },
  })
  return { g: g as unknown as CanvasRenderingContext2D, words, fills }
}

beforeAll(() => {
  // jsdom has no Path2D: a stand-in that keeps its path data.
  ;(globalThis as unknown as { Path2D: unknown }).Path2D = class { constructor(public d: string) {} }
})

describe('the yard intro', () => {
  it('runs 8 seconds', () => {
    expect(YARD_SECONDS).toBe(8)
  })

  for (const a of ASPECTS) {
    it(`draws at 0, 4 and 8 s on the ${a.id} stage, its words on the stage`, () => {
      for (const t of [0, 4, YARD_SECONDS]) {
        const { g, words } = fakeCanvas()
        expect(() => drawYard(g, a.w, a.h, t)).not.toThrow()
        for (const word of words) {
          const left = word.align === 'center' ? word.x - word.w / 2 : word.align === 'right' ? word.x - word.w : word.x
          expect(left, `${a.id} ${t}s "${word.text}"`).toBeGreaterThanOrEqual(-1)
          expect(left + word.w, `${a.id} ${t}s "${word.text}"`).toBeLessThanOrEqual(a.w + 1)
          expect(word.y - word.size, `${a.id} ${t}s "${word.text}"`).toBeGreaterThanOrEqual(-1)
          expect(word.y, `${a.id} ${t}s "${word.text}"`).toBeLessThanOrEqual(a.h + 1)
        }
      }
    })
  }

  it('ends on the drawing: the wordmark filled, the leaning l in rust', () => {
    for (const a of ASPECTS) {
      const { g, words, fills } = fakeCanvas()
      drawYard(g, a.w, a.h, YARD_SECONDS - 0.5)
      expect(fills.filter((f) => f === '#D0694F'), a.id).toHaveLength(1)
      expect(fills.filter((f) => f === '#F2F4F3').length, a.id).toBeGreaterThan(14)
      expect(words.map((w) => w.text), a.id).toContain('AGENTS, SIDE BY SIDE')
    }
  })

  it('shows the yard alone mid-way: no drawing, no words', () => {
    const { g, words, fills } = fakeCanvas()
    drawYard(g, 1600, 900, 4)
    expect(words).toHaveLength(0)
    expect(fills).not.toContain('#D0694F')
  })

  it('takes an 8 s lead when chosen, and gives the 3 s back when left', () => {
    expect(leadFor('yard', 3)).toBe(YARD_SECONDS)
    expect(leadFor('sheet', YARD_SECONDS)).toBe(3)
    expect(leadFor('sheet', 5)).toBe(5)
  })
})
