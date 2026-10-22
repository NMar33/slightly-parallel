/**
 * The opening and closing cards: every hand, on every stage, keeps its
 * words inside the frame — a closing line that ran off the right edge is
 * the bug these exist for — and each hand is drawn, not skipped.
 */

import { beforeAll, describe, expect, it } from 'vitest'

import { THEMES } from '../timelapse/theme'
import { drawEnding, drawOpening, endingOf, openingOf } from './bookends'
import { ASPECTS, drawTour, type Stage } from './scene'
import { ENDINGS, OPENINGS, PRESETS, duration, type Script } from './script'

type Word = { text: string; x: number; y: number; w: number; size: number; align: string }

/** A canvas that records each word and where it was set. */
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

/** The longest words the library writes, on the preset with the most beats. */
function script(aspect: string, theme: string): Script {
  const most = PRESETS.reduce((a, b) => (b.beats.filter((x) => x.on).length > a.beats.filter((x) => x.on).length ? b : a))
  return {
    ...most,
    aspect,
    theme,
    title: 'Slightly Parallel',
    subtitle: 'a dashboard for the coding agents in your repositories: what they did, why, and what is left',
    endline: 'Runs on your computer · the data stays in plain CSV and Markdown files · nothing leaves the machine',
    section: 'Decisions and architecture',
  }
}

const stageOf = (s: Script, w: number, h: number): Stage => ({
  w, h, theme: THEMES.find((t) => t.id === s.theme) ?? THEMES[0], face: 'sans',
  shots: new Map(), footer: true, bookends: true, highlight: false, panel: 'card',
})

function onStage(words: Word[], w: number, h: number, label: string, drawn = true) {
  if (drawn) expect(words.length, label).toBeGreaterThan(0)
  for (const word of words) {
    const left = word.align === 'center' ? word.x - word.w / 2 : word.align === 'right' ? word.x - word.w : word.x
    expect(left, `${label}: "${word.text}" left`).toBeGreaterThanOrEqual(-1)
    expect(left + word.w, `${label}: "${word.text}" right`).toBeLessThanOrEqual(w + 1)
    expect(word.y - word.size, `${label}: "${word.text}" top`).toBeGreaterThanOrEqual(-1)
    expect(word.y, `${label}: "${word.text}" bottom`).toBeLessThanOrEqual(h + 1)
  }
}

describe('the opening and closing cards', () => {
  for (const o of OPENINGS) {
    it(`opening "${o.id}" keeps every word on every stage`, () => {
      for (const a of ASPECTS) {
        for (const theme of ['midnight', 'paper', 'slightly']) {
          for (const u of [0.3, 0.6, 0.85]) {
            const s = { ...script(a.id, theme), opening: o.id }
            const { g, words } = fakeCanvas()
            drawOpening(g, stageOf(s, a.w, a.h), s, u)
            // The two stems hold the name back until the second stem has settled;
            // the yard sets its words only once the drawing returns, from 6 s of 8.
            const drawn = o.id === 'yard' ? u > 0.75 : u > 0.5 || o.id !== 'stems'
            onStage(words, a.w, a.h, `${o.id} ${a.id} ${theme} u=${u}`, drawn)
          }
        }
      }
    })
  }

  for (const e of ENDINGS) {
    it(`ending "${e.id}" keeps every word on every stage`, () => {
      for (const a of ASPECTS) {
        for (const theme of ['midnight', 'paper', 'slightly']) {
          for (const u of [0.3, 0.6]) {
            const s = { ...script(a.id, theme), ending: e.id }
            const { g, words } = fakeCanvas()
            drawEnding(g, stageOf(s, a.w, a.h), s, u)
            onStage(words, a.w, a.h, `${e.id} ${a.id} ${theme} u=${u}`)
          }
        }
      }
    })
  }

  it('wraps a closing line that is wider than the stage', () => {
    const s = { ...script('16:9', 'midnight'), ending: 'plain' as const }
    const { g, words } = fakeCanvas()
    drawEnding(g, stageOf(s, 1200, 675), s, 0.5)
    const line = words.filter((w) => w.text !== s.title)
    expect(line.length).toBeGreaterThan(1)
    expect(line.map((w) => w.text).join(' ')).toContain('Markdown')
  })

  it('draws the wordmark from its outlines, with the leaning l in rust', () => {
    const s = { ...script('16:9', 'slightly'), opening: 'wordmark' as const }
    const { g, fills } = fakeCanvas()
    drawOpening(g, stageOf(s, 1200, 675), s, 0.9)
    expect(fills.filter((f) => f === '#D0694F')).toHaveLength(1)
    expect(fills.length).toBeGreaterThan(15)
  })

  it('lists the steps of the tour in the recap, and no more than fit', () => {
    const s = { ...script('16:9', 'paper'), ending: 'recap' as const }
    const { g, words } = fakeCanvas()
    drawEnding(g, stageOf(s, 1200, 675), s, 0.5)
    const numbers = words.filter((w) => /^\d\d$/.test(w.text))
    expect(numbers.length).toBeGreaterThanOrEqual(5)
    expect(numbers.length).toBeLessThanOrEqual(7)
    expect(words.some((w) => w.text.startsWith('and ') && w.text.endsWith(' more'))).toBe(true)
  })

  it('falls back to the wordmark for a script saved before the hands existed', () => {
    const s = { ...script('16:9', 'midnight'), opening: undefined, ending: undefined }
    expect(openingOf(s)).toBe('wordmark')
    expect(endingOf(s)).toBe('wordmark')
    expect(openingOf({ ...s, opening: 'nonsense' as 'plain' })).toBe('wordmark')
  })

  it('is what the film draws at its first and last seconds', () => {
    const s = { ...script('16:9', 'midnight'), opening: 'chapter' as const, ending: 'quote' as const }
    const a = fakeCanvas()
    drawTour(a.g, s, s.lead * 0.5, stageOf(s, 1200, 675))
    expect(a.words.some((w) => w.text.includes('DECISIONS AND ARCHITECTURE'))).toBe(true)
    const b = fakeCanvas()
    drawTour(b.g, s, duration(s) - s.tail * 0.5, stageOf(s, 1200, 675))
    expect(b.words.map((w) => w.text).join(' ')).toContain('Runs on your computer')
  })

  it('every preset opens on the stems and closes on the plate; the yard is the batch\'s', () => {
    expect(new Set(PRESETS.map(openingOf))).toEqual(new Set(['stems']))
    expect(new Set(PRESETS.map(endingOf))).toEqual(new Set(['plate']))
    expect(OPENINGS.some((o) => o.id === 'yard')).toBe(true)
  })
})
