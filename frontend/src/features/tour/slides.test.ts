/**
 * The beats that are not a page.
 *
 * A terminal types its commands in the order written and prints an answer
 * whole; a slide puts its lines on the ground; neither is photographed or
 * walked, and the film draws both without a shot.
 */

import { describe, it, expect } from 'vitest'

import { THEMES } from '../timelapse/theme'

import { drawTour, type Stage } from './scene'
import { drawSlide, drawTerminal, termLines, terminalReveal } from './slides'
import { LIBRARY, PRESETS, captureJob, walkable, type Beat, type Script } from './script'

const stage = (): Stage => ({
  w: 1600, h: 900, theme: THEMES[0], face: 'sans', shots: new Map(), images: new Map(),
  footer: true, bookends: true, highlight: false, panel: 'card',
})

/** A pretend canvas that draws nothing and remembers every word. */
function fakeCanvas() {
  const words: string[] = []
  const state: Record<string, unknown> = { font: '10px sans', textAlign: 'left', letterSpacing: '0px' }
  const saved: Array<Record<string, unknown>> = []
  const sizeOf = () => parseFloat(/([\d.]+)px/.exec(String(state.font))?.[1] ?? '10')
  const g = new Proxy(state, {
    get(target, key: string) {
      if (key === 'measureText') return (text: string) => ({ width: text.length * sizeOf() * 0.5 })
      if (key === 'fillText') return (text: string) => { words.push(text) }
      if (key === 'createLinearGradient') return () => ({ addColorStop() {} })
      if (key === 'save') return () => saved.push({ ...state })
      if (key === 'restore') return () => Object.assign(state, saved.pop() ?? {})
      if (key in target) return target[key]
      return () => {}
    },
    set(target, key: string, value) { target[key] = value; return true },
  }) as unknown as CanvasRenderingContext2D
  return { g, words }
}

const beat = (over: Partial<Beat>): Beat => ({ ...LIBRARY[0], on: true, ...over })

describe('a terminal beat', () => {
  const text = '$ git clone x\n$ cd x\n# a note\nready on :8123'

  it('reads commands, comments and answers apart', () => {
    expect(termLines(text).map((l) => l.kind)).toEqual(['command', 'command', 'comment', 'output'])
  })

  it('types the commands in order, then prints the answers whole', () => {
    const all = termLines(text)
    const start = terminalReveal(all, 0)
    expect(start.chars).toEqual([0, 0, 0, 0])
    const mid = terminalReveal(all, 0.2)
    // The first command is being typed before the second has started.
    expect(mid.chars[0]).toBeGreaterThan(0)
    expect(mid.chars[1]).toBe(0)
    // Mid-way through the answers there is no caret: the next thing is an answer, not a prompt.
    const printing = terminalReveal(termLines('$ a\nout1\nout2'), 0.66)
    expect(printing.chars).toEqual([1, 4, 0])
    expect(printing.caret).toBe(-1)
    const end = terminalReveal(all, 0.95)
    expect(end.chars).toEqual(['git clone x'.length, 'cd x'.length, 'a note'.length, 'ready on :8123'.length])
    expect(end.caret).toBe(all.length)
  })

  it('draws the window title and the typed words, with no picture at all', () => {
    const { g, words } = fakeCanvas()
    drawTerminal(g, stage(), beat({ kind: 'terminal', title: 'bash', text }), 0.9, 1, 60)
    expect(words).toContain('bash')
    expect(words).toContain('git clone x')
    expect(words).toContain('ready on :8123')
  })
})

describe('a slide beat', () => {
  it('draws the chapter, the title and the lines, bullets and chips included', () => {
    const { g, words } = fakeCanvas()
    const b = beat({ kind: 'slide', chapter: 'Install', title: 'Python and git', text: 'first line\n- a bullet\n`a command`' })
    drawSlide(g, stage(), b, 0.9, 1, 60)
    expect(words).toContain('INSTALL')
    expect(words).toContain('Python and git')
    expect(words).toContain('first line')
    expect(words).toContain('a bullet')
    expect(words).toContain('a command')
  })

  it('plays in the film without a shot, where a page would say it has none', () => {
    const { g, words } = fakeCanvas()
    const b = beat({ id: 'x', kind: 'slide', title: 'A slide', text: 'one line', hold: 5 })
    const script: Script = { ...PRESETS[0], beats: [b], lead: 0, tail: 0 }
    drawTour(g, script, 2.5, stage())
    expect(words).toContain('A slide')
    expect(words.join(' ')).not.toContain('No picture')
  })
})

describe('what is photographed and walked', () => {
  it('leaves slides and terminals out of the capture and the live tour', () => {
    const page = beat({ id: 'p', kind: 'page', page: '/setup' })
    const slide = beat({ id: 's', kind: 'slide', page: '' })
    const term = beat({ id: 't', kind: 'terminal', page: '' })
    expect(captureJob([slide, page, term], 'shopfront').map((j) => j.id)).toEqual(['p'])
    const script: Script = { ...PRESETS[0], beats: [slide, page, term] }
    expect(walkable(script).map((b) => b.id)).toEqual(['p'])
  })

  it('the install cut names beats the library has, slides and pages alike', () => {
    const install = PRESETS.find((p) => p.id === 'install')
    expect(install).toBeDefined()
    const on = install!.beats.filter((b) => b.on)
    expect(on.some((b) => b.kind === 'slide')).toBe(true)
    expect(on.some((b) => b.kind === 'terminal')).toBe(true)
    expect(on.some((b) => !b.kind)).toBe(true)
  })
})
