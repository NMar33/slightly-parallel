/**
 * The camera.
 *
 * The two things a tour cannot get wrong: it must not stretch a screenshot,
 * and it must not move when the beat did not ask it to — a still beat that
 * drifts turns held GIF frames into a megabyte of shimmer.
 */

import { describe, it, expect } from 'vitest'

import { THEMES } from '../timelapse/theme'

import { __test, drawTour, viewFor, stageSize, ASPECTS, type Stage } from './scene'
import { LIBRARY, PANELS, type Beat, type Script } from './script'

const shot = (rect: { x: number; y: number; w: number; h: number } | null) => ({
  frames: [], w: 3200, h: 2000, rect, nav: [], pointer: [], grab: null,
})

const beat = (over: Partial<Beat> = {}): Beat => ({ ...LIBRARY[0], ...over })

describe('the window on the shot', () => {
  const subject = { x: 0.8, y: 0.05, w: 0.02, h: 0.02 }

  it('is the whole page when the beat asks for the whole page', () => {
    expect(viewFor(beat({ zoom: 'full' }), shot(subject), 16 / 9, 0.5))
      .toEqual({ x: 0, y: 0, w: 1, h: 1 })
  })

  it('is the whole page when nothing was found to point at', () => {
    expect(viewFor(beat({ zoom: 'focus' }), shot(null), 16 / 9, 0.5))
      .toEqual({ x: 0, y: 0, w: 1, h: 1 })
  })

  it('does not move across a still beat', () => {
    const b = beat({ zoom: 'focus' })
    const a0 = viewFor(b, shot(subject), 16 / 9, 0)
    const a1 = viewFor(b, shot(subject), 16 / 9, 0.99)
    expect(a1).toEqual(a0)
  })

  it('keeps a subject at the edge inside the picture', () => {
    const v = viewFor(beat({ zoom: 'focus' }), shot(subject), 16 / 9, 1)
    expect(v.x).toBeGreaterThanOrEqual(0)
    expect(v.x + v.w).toBeLessThanOrEqual(1 + 1e-9)
    expect(v.y).toBeGreaterThanOrEqual(0)
    expect(v.y + v.h).toBeLessThanOrEqual(1 + 1e-9)
  })

  it('never zooms so far that pixels show', () => {
    const v = __test.focusView(shot({ x: 0.5, y: 0.5, w: 0.004, h: 0.004 }), 16 / 9)
    expect(v.w).toBeGreaterThanOrEqual(0.34)
  })

  it('pushes from wide to the subject and settles before the beat ends', () => {
    const b = beat({ zoom: 'push' })
    const start = viewFor(b, shot(subject), 16 / 9, 0)
    const mid = viewFor(b, shot(subject), 16 / 9, 0.3)
    const late = viewFor(b, shot(subject), 16 / 9, 0.6)
    const end = viewFor(b, shot(subject), 16 / 9, 1)
    expect(start.w).toBe(1)
    expect(mid.w).toBeLessThan(1)
    expect(late.w).toBeCloseTo(end.w, 6)
  })

  it('pulls the other way', () => {
    const b = beat({ zoom: 'pull' })
    expect(viewFor(b, shot(subject), 16 / 9, 0).w).toBeLessThan(1)
    expect(viewFor(b, shot(subject), 16 / 9, 1).w).toBe(1)
  })
})

describe('the screen', () => {
  it('keeps the shot at its own shape inside the area it is given', () => {
    const box = __test.screenBox(
      { w: 1600, h: 900 } as never,
      shot(null),
      { x: 0, y: 0, w: 1500, h: 800 },
    )
    expect(box.w / box.h).toBeCloseTo(3200 / 2000, 6)
    expect(box.w).toBeLessThanOrEqual(1500)
    expect(box.h).toBeLessThanOrEqual(800)
  })
})

describe('the stage', () => {
  it('has a size per shape, and falls back to wide', () => {
    expect(stageSize('9:16')).toMatchObject({ w: 900, h: 1600 })
    expect(stageSize('nonsense').id).toBe('16:9')
  })
})

describe('the card', () => {
  const stage = (w: number) => ({ w, h: Math.round((w * 9) / 16) }) as never
  const at = (w: number) => {
    const s = stage(w)
    const screen = { x: w * 0.035, y: w * 0.035, w: w * 0.93, h: (w * 9) / 16 * 0.8 }
    const hole = { x: w * 0.55, y: w * 0.2, w: w * 0.02, h: w * 0.02 }
    return __test.calloutBox(s, screen, hole, 'auto', 'card')
  }

  it('lands in the same place whatever size the scene is drawn at', () => {
    // The export renders at 2x and shrinks; if the layout is not a pure
    // fraction of the stage, the GIF differs from what was previewed.
    const small = at(1600)
    const big = at(3200)
    expect(big.x / small.x).toBeCloseTo(2, 6)
    expect(big.y / small.y).toBeCloseTo(2, 6)
    expect(big.w / small.w).toBeCloseTo(2, 6)
  })

  it('picks the same side for a centred subject at any render size', () => {
    // Left and right are exactly equal here; only a tie-break keeps the
    // preview and the export agreeing.
    const side = (w: number) => {
      const s = stage(w)
      const screen = { x: w * 0.11, y: w * 0.035, w: w * 0.777, h: w * 0.485 }
      const hole = { x: screen.x + screen.w / 2 - w * 0.011, y: screen.y + screen.h / 2, w: w * 0.022, h: w * 0.022 }
      const card = __test.calloutBox(s, screen, hole, 'auto', 'card')
      return card.x > hole.x ? 'right' : 'left'
    }
    expect(side(2000)).toBe(side(1600))
  })

  it('goes to a corner rather than crowding the thing it explains', () => {
    const s = stage(1600)
    // A narrow shot with the subject near its middle: neither side has room
    // for a 464-wide card without crowding.
    const screen = { x: 300, y: 56, w: 1000, h: 720 }
    const tight = __test.calloutBox(s, screen, { x: 790, y: 200, w: 20, h: 20 }, 'auto', 'card')
    expect(tight.x).toBeCloseTo(screen.x + 56, 4)
    // Subject in the upper half, so the card takes the lower corner.
    expect(tight.y).toBeGreaterThan(screen.y + screen.h / 2)
  })
})

describe('where the card goes', () => {
  const stage = (w: number) => ({ w, h: Math.round((w * 9) / 16) }) as never
  const screen = { x: 56, y: 56, w: 1488, h: 700 }

  it('honours an explicit placement instead of guessing', () => {
    const s = stage(1600)
    const hole = { x: 200, y: 200, w: 20, h: 20 }
    const left = __test.calloutBox(s, screen, hole, 'left', 'card')
    const right = __test.calloutBox(s, screen, hole, 'right', 'card')
    const top = __test.calloutBox(s, screen, hole, 'top', 'card')
    const bottom = __test.calloutBox(s, screen, hole, 'bottom', 'card')
    expect(left.x).toBeLessThan(right.x)
    expect(top.y).toBeLessThan(bottom.y)
    // …and stays inside the screen whichever way it was sent.
    for (const box of [left, right, top, bottom]) {
      expect(box.x).toBeGreaterThanOrEqual(screen.x)
      expect(box.x + box.w).toBeLessThanOrEqual(screen.x + screen.w + 1)
      expect(box.y).toBeGreaterThanOrEqual(screen.y)
      expect(box.y + box.h).toBeLessThanOrEqual(screen.y + screen.h + 1)
    }
  })

  it('gives a bar the width a bar needs, wherever it is placed', () => {
    const s = stage(1600)
    const card = __test.calloutBox(s, screen, null, 'bottom', 'card')
    const bar = __test.calloutBox(s, screen, null, 'bottom', 'bar')
    expect(bar.w).toBeGreaterThan(card.w * 1.5)
    expect(bar.h).toBeLessThan(card.h * 1.2)
  })
})

describe('the skins', () => {
  const stage = (w: number, h = Math.round((w * 9) / 16)) => ({ w, h }) as never
  const screen = (w: number) => ({ x: w * 0.035, y: w * 0.035, w: w * 0.8, h: w * 0.48 })
  const inside = (r: { x: number; y: number; w: number; h: number }, by: typeof r) => {
    expect(r.x).toBeGreaterThanOrEqual(by.x - 1e-6)
    expect(r.y).toBeGreaterThanOrEqual(by.y - 1e-6)
    expect(r.x + r.w).toBeLessThanOrEqual(by.x + by.w + 1e-6)
    expect(r.y + r.h).toBeLessThanOrEqual(by.y + by.h + 1e-6)
  }
  const apart = (a: { x: number; y: number; w: number; h: number }, b: typeof a) =>
    a.x >= b.x + b.w || b.x >= a.x + a.w || a.y >= b.y + b.h || b.y >= a.y + a.h

  it('puts a tooltip under its subject, inside the film, with the tail on the ring', () => {
    const scr = screen(1600)
    const hole = { x: 600, y: 200, w: 120, h: 30 }
    const { box, tail } = __test.tipLayout(stage(1600), scr, hole, 460, 150)
    inside(box, scr)
    expect(apart(box, hole)).toBe(true)
    expect(box.y).toBeGreaterThan(hole.y + hole.h)
    expect(tail).not.toBeNull()
    // The tail ends on the spotlight's ring, which stands just off the subject…
    const ring = 1600 * 0.006
    expect(tail!.end.y).toBeCloseTo(hole.y + hole.h + ring, 6)
    expect(tail!.end.x).toBeGreaterThanOrEqual(hole.x - ring)
    expect(tail!.end.x).toBeLessThanOrEqual(hole.x + hole.w + ring)
    // …and its point leaves the box towards it.
    expect(tail!.apex.y).toBeLessThan(box.y)
    expect(tail!.apex.y).toBeGreaterThanOrEqual(tail!.end.y - 1e-6)
  })

  it('goes above a subject at the bottom, and still aims at it', () => {
    const scr = screen(1600)
    const hole = { x: 900, y: scr.y + scr.h - 60, w: 80, h: 30 }
    const { box, tail } = __test.tipLayout(stage(1600), scr, hole, 460, 150)
    inside(box, scr)
    expect(box.y + box.h).toBeLessThan(hole.y)
    expect(tail!.end.y).toBeLessThan(hole.y)
    expect(tail!.a.y).toBeCloseTo(box.y + box.h, 6)
  })

  it('takes the side when the subject is taller than the room above and below', () => {
    const scr = screen(1600)
    const hole = { x: 300, y: scr.y + 20, w: 200, h: scr.h - 40 }
    const { box, tail } = __test.tipLayout(stage(1600), scr, hole, 460, 150)
    inside(box, scr)
    expect(box.x).toBeGreaterThan(hole.x + hole.w)
    expect(tail!.a.x).toBeCloseTo(box.x, 6)
    expect(tail!.end.x).toBeLessThan(box.x)
    expect(tail!.end.y).toBeGreaterThanOrEqual(hole.y - 10)
    expect(tail!.end.y).toBeLessThanOrEqual(hole.y + hole.h + 10)
  })

  it('has no tail when there is nothing to point at, and stays in the film', () => {
    const scr = screen(1600)
    const { box, tail } = __test.tipLayout(stage(1600), scr, null, 460, 150)
    expect(tail).toBeNull()
    inside(box, scr)
  })

  it('lays a tooltip out the same at twice the size', () => {
    const at = (w: number) => {
      const k = w / 1600
      return __test.tipLayout(stage(w), screen(w), { x: 600 * k, y: 200 * k, w: 120 * k, h: 30 * k }, 460 * k, 150 * k)
    }
    const small = at(1600)
    const big = at(3200)
    expect(big.box.x / small.box.x).toBeCloseTo(2, 6)
    expect(big.box.y / small.box.y).toBeCloseTo(2, 6)
    expect(big.tail!.end.x / small.tail!.end.x).toBeCloseTo(2, 6)
  })

  it('moves the subtitle to the top when the subject is at the bottom', () => {
    const scr = screen(1600)
    const low = __test.subtitleSpot(scr, { x: 700, y: scr.y + scr.h - 50, w: 60, h: 30 }, 700, 100, 20)
    const high = __test.subtitleSpot(scr, { x: 700, y: scr.y + 50, w: 60, h: 30 }, 700, 100, 20)
    expect(low.y).toBeLessThan(scr.y + scr.h / 2)
    expect(high.y).toBeGreaterThan(scr.y + scr.h / 2)
    inside(low, scr)
    inside(high, scr)
  })

  it('splits the stage into a film and a column that do not touch', () => {
    for (const a of ASPECTS) {
      const s = stage(a.w, a.h)
      for (const panel of ['headline', 'ring'] as const) {
        for (const rect of [null, { x: 0.1, y: 0.2, w: 0.1, h: 0.05 }, { x: 0.8, y: 0.2, w: 0.1, h: 0.05 }]) {
          const sp = __test.splitStage(s, panel, rect, a.h * 0.075, a.w * 0.035)
          const all = { x: 0, y: 0, w: a.w, h: a.h }
          inside(sp.area, all)
          inside(sp.side, all)
          expect(apart(sp.area, sp.side)).toBe(true)
        }
      }
    }
  })

  it('stacks the film and a band as tall as its words, the pair centred, on a square or tall stage', () => {
    for (const a of ASPECTS.filter((x) => x.w / x.h <= 1.2)) {
      const s = stage(a.w, a.h)
      const footer = a.h * 0.075
      const pad = a.w * 0.035
      for (const need of [60, 140, 260]) {
        for (const onTop of [false, true]) {
          const { film, band } = __test.bandStage(s, 1.6, footer, pad, need, onTop)
          const all = { x: 0, y: pad, w: a.w, h: a.h - footer - pad }
          inside(film, all)
          inside(band, all)
          expect(apart(film, band)).toBe(true)
          expect(band.h).toBeCloseTo(need, 6)
          expect(film.w / film.h).toBeCloseTo(1.6, 6)
          // Above the pair and below it, the same room.
          const first = Math.min(film.y, band.y)
          const last = Math.max(film.y + film.h, band.y + band.h)
          expect(first - pad).toBeCloseTo(a.h - footer - last, 6)
        }
      }
      // The ring's and the headline's band follow the words too.
      const ring = __test.splitStage(s, 'ring', null, footer, pad, 120)
      expect(ring.side.h).toBeCloseTo(120, 6)
      expect(ring.side.y).toBeGreaterThan(ring.area.y + ring.area.h)
    }
  })

  it('puts the ring column on the side the subject leans to', () => {
    const s = stage(1600)
    const left = __test.splitStage(s, 'ring', { x: 0.1, y: 0.2, w: 0.1, h: 0.05 }, 67, 56)
    const right = __test.splitStage(s, 'ring', { x: 0.8, y: 0.2, w: 0.1, h: 0.05 }, 67, 56)
    expect(left.at).toBe('left')
    expect(right.at).toBe('right')
    expect(__test.splitStage(stage(900, 1600), 'ring', null, 120, 32).at).toBe('below')
    expect(__test.splitStage(stage(900, 1600), 'headline', null, 120, 32).at).toBe('top')
  })

  it('sets accent words in a colour that reads on every theme', () => {
    for (const t of THEMES) {
      expect(__test.contrast(__test.accentInk(t, t.panel), t.panel)).toBeGreaterThanOrEqual(4.5)
    }
  })
})

/**
 * A pretend canvas: it draws nothing and remembers every word and where.
 * Text is measured at half its size per character, close enough to a
 * sans-serif for the wrapping to behave like the real thing.
 */
function fakeCanvas() {
  const words: Array<{ text: string; x: number; y: number; w: number; size: number; align: string }> = []
  const state: Record<string, unknown> = { font: '10px sans', textAlign: 'left', letterSpacing: '0px' }
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
      if (key === 'createLinearGradient') return () => ({ addColorStop() {} })
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
  return { g: g as unknown as CanvasRenderingContext2D, words }
}

describe('every panel, on every stage', () => {
  const long = {
    title: 'Open the evidence for a finished task and read what the agent proved',
    text: 'Each task keeps its proof: the files it touched, the commands it ran, the screenshots it took and the short report the agent wrote when it finished. Open it from the card and read it in one place.',
  }
  const script = (panel: Script['panel'], aspect: string): Script => ({
    id: 'x', name: 'x', note: '', title: 'x', subtitle: '', endline: '', theme: 'paper', aspect,
    panel, project: '', demo: '', base: '', lead: 0, tail: 0,
    beats: Array.from({ length: 12 }, (_, i) => ({
      ...LIBRARY[0], id: 'b', chapter: 'The board', zoom: 'focus' as const, hold: 4, on: true,
      ...(i % 2 ? long : { title: 'Drag a card', text: 'It moves.' }),
    })),
  })
  const shots = (rect: { x: number; y: number; w: number; h: number } | null) => new Map([['b', {
    frames: [{} as CanvasImageSource], w: 3200, h: 2000, rect, nav: [], pointer: [], grab: null,
  }]])

  it('sizes the band under a square or tall film to its words, for every panel', () => {
    for (const panel of PANELS.map((p) => p.id)) {
      for (const a of ASPECTS.filter((x) => x.w / x.h <= 1.2)) {
        const st = { w: a.w, h: a.h, theme: THEMES[2], face: 'sans', panel } as unknown as Stage
        const c = (title: string, text: string) => ({
          title, text, step: '3 / 12', progress: 0.5, chapter: 'The board', index: 2, of: 12,
        })
        const short = __test.bandNeed(fakeCanvas().g, st, c('Drag a card', 'It moves.'), a.w * 0.93)
        const tall = __test.bandNeed(fakeCanvas().g, st, c(long.title, long.text), a.w * 0.93)
        // A one-line caption takes a slim band: the old band was a third of the stage.
        expect(short, `${panel} ${a.id}`).toBeLessThan(a.h * 0.2)
        expect(short, `${panel} ${a.id}`).toBeGreaterThan(a.h * 0.03)
        expect(tall, `${panel} ${a.id}`).toBeGreaterThan(short)
      }
    }
  })

  for (const panel of PANELS.map((p) => p.id)) {
    it(`${panel} keeps every word on the stage`, () => {
      for (const a of ASPECTS) {
        for (const rect of [null, { x: 0.4, y: 0.3, w: 0.05, h: 0.03 }, { x: 0.2, y: 0.1, w: 0.2, h: 0.8 }]) {
          for (const at of [2, 6]) {
            const { g, words } = fakeCanvas()
            const st: Stage = {
              w: a.w, h: a.h, theme: THEMES[2], face: 'sans', shots: shots(rect),
              footer: true, bookends: false, highlight: false, panel,
            }
            drawTour(g, script(panel, a.id), at, st)
            expect(words.length).toBeGreaterThan(2)
            for (const word of words) {
              const left = word.align === 'center' ? word.x - word.w / 2
                : word.align === 'right' ? word.x - word.w : word.x
              expect(left).toBeGreaterThanOrEqual(-1)
              expect(left + word.w).toBeLessThanOrEqual(a.w + 1)
              expect(word.y - word.size).toBeGreaterThanOrEqual(-1)
              expect(word.y).toBeLessThanOrEqual(a.h + 1)
            }
          }
        }
      }
    })
  }
})
