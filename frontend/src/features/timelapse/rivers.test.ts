/**
 * The rivers, checked where they can be checked without a canvas: the
 * registry's promises, the git fallback, and the constellation layout —
 * which has to be identical every time it is asked for, or playback and
 * export would disagree about where a file sits.
 */

import { describe, expect, it } from 'vitest'

import { buildFilm } from './film'
import { RIVERS } from './rivers'
import { BRAND } from './brand'
import type { Card, Source } from './source'

const day = 24 * 3600_000
const T0 = Date.parse('2026-08-01T09:00:00')
const at = (d: number, h = 0) => new Date(T0 + d * day + h * 3600_000).toISOString().slice(0, 19)

const card = (over: Partial<Card> = {}): Card => ({
  id: 'tk_1', title: 'A card', lane: 'Board', assignee: '', tags: '', sprint: '',
  born: at(0), status0: 'unclassified', moves: [], archived_at: '', evidence: false,
  ...over,
})

const base: Source = {
  project: 'ALPHA',
  span: { start: at(0), end: at(6) },
  cards: [card({ moves: [{ at: at(1), status: 'done' }] })],
  sessions: [{ id: 's1', agent_id: 'cc-a', start: at(1), end: at(1, 2), turns_n: 4, l1: '' }],
  marks: [],
  stats: { turns: 4 },
}

const withGit: Source = {
  ...base,
  git: {
    commits: [
      { at: at(1), add: 40, del: 5, files: 2, areas: { frontend: 2 }, touched: ['src/a.ts', 'src/b.ts'] },
      { at: at(3), add: 90, del: 20, files: 2, areas: { frontend: 1, backend: 1 }, touched: ['src/b.ts', 'api/c.py'] },
    ],
    areas: ['frontend', 'backend'],
    graph: {
      nodes: [
        { name: 'a.ts', path: 'src/a.ts', dir: 0, area: 'frontend', churn: 45, born: at(1) },
        { name: 'b.ts', path: 'src/b.ts', dir: 0, area: 'frontend', churn: 100, born: at(1) },
        { name: 'c.py', path: 'api/c.py', dir: 1, area: 'backend', churn: 110, born: at(3) },
      ],
      edges: [[0, 1, 3, at(1)], [1, 2, 2, at(3)]],
      dirs: [
        { path: 'src', name: 'src', parent: -1, depth: 0 },
        { path: 'api', name: 'api', parent: -1, depth: 0 },
      ],
    },
  },
}

describe('the river registry', () => {
  it('every variant the studio offers is a real one', () => {
    expect(new Set(RIVERS.map((r) => r.id)).size).toBe(RIVERS.length)
    expect(RIVERS.map((r) => r.id)).toContain(BRAND.band)
  })

  it('the default needs no repository, so a film always has one to draw', () => {
    expect(RIVERS.find((r) => r.id === BRAND.band)?.needsGit).toBeFalsy()
  })

  it('every variant carries a caption a reader could publish under it', () => {
    for (const rv of RIVERS) {
      expect(rv.caption.length, rv.id).toBeGreaterThan(80)
      expect(rv.caption.trim(), rv.id).toBe(rv.caption)
      // A caption explains the picture; it must not name the code that draws it.
      expect(rv.caption, rv.id).not.toMatch(/\b(px|canvas|keyframe|simulate|rect)\b/i)
    }
  })
})

describe('git', () => {
  it('is carried onto the film only when there is something in it', () => {
    expect(buildFilm(base).git).toBeNull()
    expect(buildFilm(withGit).git?.commits).toHaveLength(2)
  })

  it('survives a scope that trims the clock', () => {
    const film = buildFilm(withGit, { days: 2 })
    expect(film.git?.graph.nodes).toHaveLength(3)
  })
})

describe('the simulation', () => {
  const sim = async () => {
    const { __layoutForTest } = await import('./rivers')
    return __layoutForTest(buildFilm(withGit))
  }

  it('is the same every time — playback and export cannot disagree', async () => {
    const a = await sim()
    const b = await sim()
    const round = (s: Awaited<ReturnType<typeof sim>>) =>
      s.keys.map((k) => [...k.pos].map((v) => v.toFixed(6)))
    expect(round(a)).toEqual(round(b))
  })

  it('stores one moment per commit, in order', async () => {
    const s = await sim()
    expect(s.keys).toHaveLength(2)
    expect(s.keys.map((k) => k.at)).toEqual([...s.keys.map((k) => k.at)].sort((x, y) => x - y))
  })

  it('nothing lurches: a body only ever creeps between two moments', async () => {
    const s = await sim()
    let worst = 0
    for (let k = 1; k < s.keys.length; k++) {
      for (let i = 0; i < s.nodes.length; i++) {
        worst = Math.max(worst, Math.hypot(
          s.keys[k].pos[i * 2] - s.keys[k - 1].pos[i * 2],
          s.keys[k].pos[i * 2 + 1] - s.keys[k - 1].pos[i * 2 + 1],
        ))
      }
    }
    // The frame is about 3.6 wide; a step of a tenth of that would read as a
    // jump. The clamp plus the eased centre keeps it far under.
    expect(worst).toBeLessThan(0.12)
  })

  it('the structure changes over time — it is not one layout faded in', async () => {
    const s = await sim()
    const first = s.keys[0].pos
    const last = s.keys[s.keys.length - 1].pos
    const moved = [...first].some((v, i) => Math.abs(v - last[i]) > 1e-3)
    expect(moved).toBe(true)
  })

  it('the walk ends on the settled repository, not on a guess at it', async () => {
    const s = await sim()
    // The last moment is the full solve, so every file is placed there.
    const last = s.keys[s.keys.length - 1]
    const spread = s.nodes.map((_, i) => Math.hypot(last.pos[i * 2], last.pos[i * 2 + 1]))
    expect(Math.max(...spread)).toBeGreaterThan(0)
    expect(spread.every((d) => Number.isFinite(d))).toBe(true)
  })

  it('the camera only ever widens, so nothing already shown is cropped', async () => {
    const s = await sim()
    const halves = s.keys.map((k) => k.cam.halfY)
    for (let i = 1; i < halves.length; i++) expect(halves[i]).toBeGreaterThanOrEqual(halves[i - 1])
  })

  it('a file ends up nearer its own folder than another', async () => {
    const s = await sim()
    const key = s.keys[s.keys.length - 1]
    const n = s.nodes.length
    const at = (i: number) => ({ x: key.pos[i * 2], y: key.pos[i * 2 + 1] })
    s.nodes.forEach((nd, i) => {
      if (nd.dir < 0) return
      const p = at(i)
      const own = at(n + nd.dir)
      const other = at(n + (1 - nd.dir))
      expect(Math.hypot(p.x - own.x, p.y - own.y))
        .toBeLessThan(Math.hypot(p.x - other.x, p.y - other.y))
    })
  })
})

describe('the instrument panels', () => {
  it('every panel variant is registered and needs the repository', () => {
    for (const id of ['cockpit', 'console', 'telemetry']) {
      const rv = RIVERS.find((r) => r.id === id)
      expect(rv, id).toBeDefined()
      expect(rv?.needsGit, id).toBe(true)
    }
  })

  it('the readings move with the playhead and are all real numbers', async () => {
    const { readings } = await import('./cockpit')
    const { frameAt } = await import('./film')
    const film = buildFilm(withGit)
    const early = readings(film, frameAt(film, Date.parse(at(0, 12))))
    const late = readings(film, frameAt(film, Date.parse(at(5))))
    expect(early.commits).toBe(0)
    expect(late.commits).toBe(2)
    expect(late.add).toBe(130)
    expect(late.done).toBeGreaterThan(early.done)
    for (const v of [late.perDay, late.leadDays, late.elapsedDays, late.backlog]) {
      expect(Number.isFinite(v)).toBe(true)
    }
    expect(late.awake).toHaveLength(film.agents.length)
  })
})

describe('the GIF colour mapping', () => {
  it('gives one colour one palette entry, whatever else is in the frame', async () => {
    const { __mapForTest } = await import('./export')
    const palette = [[0, 0, 0], [140, 140, 148], [132, 135, 141], [255, 255, 255]]
    const cache = new Map<number, number>()
    const px = (rgb: number[][]) =>
      new Uint8Array(rgb.flatMap(([r, g, b]) => [r, g, b, 255]))

    // The same colour, once surrounded by neighbours it nearly matches and
    // once alone. gifenc's rgb565 cache answers differently for the two,
    // because a near neighbour claims the shared key first; ours must not.
    const a = __mapForTest(px([[135, 138, 144], [136, 139, 145], [134, 137, 143]]), palette, cache)
    const b = __mapForTest(px([[0, 0, 0], [255, 255, 255], [135, 138, 144]]), palette, cache)
    expect(b[2]).toBe(a[0])
  })

  it('is stable across frames because the cache outlives them', async () => {
    const { __mapForTest } = await import('./export')
    const palette = [[10, 10, 10], [200, 200, 200]]
    const cache = new Map<number, number>()
    const one = __mapForTest(new Uint8Array([120, 120, 120, 255]), palette, cache)
    const two = __mapForTest(new Uint8Array([120, 120, 120, 255]), palette, cache)
    expect(one[0]).toBe(two[0])
    expect(cache.size).toBe(1)
  })
})
