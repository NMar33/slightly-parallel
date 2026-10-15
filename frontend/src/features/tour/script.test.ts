/**
 * The tour's clock and its choice of subject.
 *
 * Both are shared: the film and the live tour read the same slots, and both
 * point at whatever `mostCentral` picks. A drift in either would show up as
 * a GIF that explains one control while highlighting another.
 */

import { describe, it, expect } from 'vitest'

import {
  LIBRARY, PRESETS, applyVoice, captureJob, chosenVoice, cueAt, duration, live, mostCentral, navFor, pageFor, slots, walkable,
  type Script,
} from './script'
import { THEMES } from '../timelapse/theme'

function script(over: Partial<Script> = {}): Script {
  return {
    ...PRESETS[0],
    lead: 2,
    tail: 3,
    beats: [
      { ...LIBRARY[0], id: 'a', hold: 4, on: true },
      { ...LIBRARY[1], id: 'b', hold: 6, on: true },
      { ...LIBRARY[2], id: 'c', hold: 5, on: false },
    ],
    ...over,
  }
}

describe('the clock', () => {
  it('runs lead, the beats that are on, then tail', () => {
    const s = script()
    expect(live(s).map((b) => b.id)).toEqual(['a', 'b'])
    expect(duration(s)).toBe(2 + 4 + 6 + 3)
    expect(slots(s).map((x) => [x.start, x.end])).toEqual([[2, 6], [6, 12]])
  })

  it('switching a beat off shortens the film without losing it', () => {
    const s = script()
    const shorter = { ...s, beats: s.beats.map((b) => (b.id === 'b' ? { ...b, on: false } : b)) }
    expect(duration(shorter)).toBe(2 + 4 + 3)
    expect(shorter.beats).toHaveLength(3)
  })

  it('names what is on screen at any second', () => {
    const s = script()
    expect(cueAt(s, 0.5).phase).toBe('title')
    const mid = cueAt(s, 8)
    expect(mid.phase).toBe('beat')
    if (mid.phase === 'beat') {
      expect(mid.slot.beat.id).toBe('b')
      expect(mid.of).toBe(2)
      expect(mid.u).toBeCloseTo(2 / 6)
    }
    expect(cueAt(s, 12.5).phase).toBe('end')
  })

  it('a cut with nothing ticked is only its cards', () => {
    const s = script({ beats: [{ ...LIBRARY[0], on: false }] })
    expect(duration(s)).toBe(5)
    expect(cueAt(s, 1).phase).toBe('title')
  })
})

describe('the subject', () => {
  const view = { width: 1000, height: 800 }

  it('is the match nearest the middle that is wholly on screen', () => {
    const edge = { x: 980, y: 10, w: 40, h: 20 }
    const centre = { x: 470, y: 390, w: 40, h: 20 }
    const corner = { x: 20, y: 20, w: 40, h: 20 }
    expect(mostCentral([edge, corner, centre], view)).toBe(centre)
  })

  it('falls back to the first match when nothing fits on screen', () => {
    const off = { x: 980, y: 10, w: 40, h: 20 }
    expect(mostCentral([off], view)).toBe(off)
  })

  it('ignores things too small to be a subject, and empty lists', () => {
    expect(mostCentral([{ x: 10, y: 10, w: 1, h: 1 }], view)).toBeNull()
    expect(mostCentral([], view)).toBeNull()
  })
})

describe('what capture is told', () => {
  it('is the page and the subject, never the words or the timing', () => {
    const job = captureJob([{ ...LIBRARY[1] }], 'shopfront')
    expect(job[0]).toMatchObject({ id: LIBRARY[1].id })
    expect(job[0].page).toBe(LIBRARY[1].page.replace('{project}', 'shopfront'))
    expect(job[0].page).not.toContain('{project}')
    expect(job[0]).not.toHaveProperty('text')
    expect(job[0]).not.toHaveProperty('hold')
  })
})

describe('the presets', () => {
  it('carry every beat in the library, so nothing can be lost by picking one', () => {
    for (const p of PRESETS) {
      expect(p.beats).toHaveLength(LIBRARY.length)
      expect(p.beats.filter((b) => b.on).length).toBeGreaterThan(0)
    }
  })

  it('give every beat a sentence, not a label', () => {
    for (const b of LIBRARY) {
      expect(b.text.length).toBeGreaterThan(20)
      expect(b.text.trim().endsWith('.')).toBe(true)
      expect(b.title.length).toBeGreaterThan(0)
    }
  })

  it('never ask the reader a question or tell them what does not happen', () => {
    const banned = [/\?/, /\bnot\b/i, /\bnever\b/i, /\bno\b/i, /\bnothing\b/i]
    for (const b of LIBRARY) {
      for (const re of banned) expect(`${b.title} ${b.text}`).not.toMatch(re)
    }
  })
})

describe('the two exits', () => {
  it('resolve a beat\u2019s page against whichever project is being shown', () => {
    const beat = LIBRARY.find((b) => b.page.includes('{project}'))!
    expect(pageFor(beat, 'shopfront')).toContain('/project/shopfront')
    expect(pageFor(beat, 'calc')).toContain('/project/calc')
    expect(pageFor(beat, 'calc')).not.toContain('{project}')
  })

  it('open the calendar on a full week of the example month, the week before this one', () => {
    const week = LIBRARY.find((b) => b.id === 'calendar-week')!
    // Monday 12 October 2026 (or any day of its week): the week of Monday 5 October.
    expect(pageFor(week, 'shopfront', '2026-10-12')).toBe('/project/shopfront#calendar&week=2026-10-05&sel=2026-10-06')
    expect(pageFor(week, 'shopfront', '2026-10-18')).toBe('/project/shopfront#calendar&week=2026-10-05&sel=2026-10-06')
    expect(pageFor(week, 'shopfront')).not.toContain('{')
  })

  it('point at the card the film acts on, when walked', () => {
    // The live tour never runs an action: a beat the film drags or opens
    // names the card itself, so the walk points at it instead.
    const script = { ...PRESETS[1] }
    for (const id of ['drag-card', 'evidence']) expect(walkable(script).find((b) => b.id === id)?.selector, id).toBeTruthy()
    expect(live(script).some((b) => b.action?.kind === 'drag')).toBe(true)
  })

  it('the quick tour shows the loop: board, proof, a message becoming an entry, the standup', () => {
    const ids = walkable(PRESETS[0]).map((b) => b.id)
    for (const id of ['board', 'evidence', 'scan-source', 'standup']) expect(ids).toContain(id)
  })

  it('every action names something to act on, and a drag names where it lands', () => {
    for (const b of LIBRARY) {
      if (!b.action) continue
      expect(b.action.selector.length).toBeGreaterThan(0)
      if (b.action.kind === 'drag') expect(b.action.to).toBeTruthy()
    }
  })
})

describe('you are here', () => {
  it('finds the nav item from the beat\u2019s own route', () => {
    const overview = LIBRARY.find((b) => b.page === '/')!
    expect(navFor(overview, 'shopfront')[0]).toContain('a[href="/"]')

    // A page inside a project rings two things: the project, and the tab —
    // ringing only the project answers "which repository" while the beat is
    // about the board.
    const board = LIBRARY.find((b) => b.page.endsWith('{project}#tasks'))!
    const rings = navFor(board, 'shopfront')
    expect(rings).toHaveLength(2)
    expect(rings[0]).toContain('a[href="/project/shopfront"]')
    expect(rings[1]).toContain('Tasks')

    // The query names a view, not a place in the nav.
    const search = LIBRARY.find((b) => b.page.startsWith('/search'))!
    expect(navFor(search, 'shopfront')[0]).toContain('a[href="/search"]')
    expect(navFor(search, 'shopfront')[0]).not.toContain('?')

    // A hash that carries more than the tab still names the tab first.
    const week = LIBRARY.find((b) => b.page.includes('#calendar&'))!
    expect(navFor(week, 'shopfront')[1]).toContain('Calendar')
  })

  it('lets a beat name something else, including nothing', () => {
    const beat = { ...LIBRARY[0], nav: '' }
    expect(navFor(beat, 'shopfront')).toEqual([])
    expect(navFor({ ...LIBRARY[0], nav: '.x' }, 'shopfront')).toEqual(['.x'])
  })

  it('is asked for at capture time, beside the subject', () => {
    const job = captureJob([LIBRARY[0]], 'shopfront')
    expect(job[0].nav[0]).toContain('a[href=')
  })
})

describe('the tours walk the example project', () => {
  it('every preset and every beat on a project page goes to the example project', async () => {
    const { PRESETS: presets, TOUR_PROJECT, onProject: on } = await import('./script')
    expect(TOUR_PROJECT).toBe('shopfront')
    for (const s of presets) expect(s.project).toBe(TOUR_PROJECT)
    const projectBeats = LIBRARY.filter(on)
    expect(projectBeats.length).toBeGreaterThan(0)
    for (const b of projectBeats) expect(pageFor(b, TOUR_PROJECT)).toContain('shopfront')
  })

  it('points the film at cards the example project has', () => {
    const text = JSON.stringify(LIBRARY)
    for (const gone of ['Restore drill', 'Alert when rollups', 'rollup', 'billing, ingest']) expect(text).not.toContain(gone)
  })
})

describe('captions', () => {
  const written = [
    { voice: 'xp' as const, title: 'Tasks', text: 'Each card is one task.' },
    { voice: 'sell' as const, title: 'Your work, in one place', text: 'Every task is on one board.' },
  ]

  it('names the caption a beat shows, or "own" when its words match none', () => {
    const b = { ...LIBRARY[0], captions: written, title: 'Tasks', text: 'Each card is one task.' }
    expect(chosenVoice(b)).toBe('xp')
    expect(chosenVoice({ ...b, text: 'Each card is one task' })).toBe('own')
    expect(chosenVoice({ ...b, captions: undefined })).toBe('own')
  })

  it('applies one voice to every beat that has it and leaves the rest as they are', () => {
    const s = script()
    s.beats[0] = { ...s.beats[0], captions: written }
    // A beat written in the plain voice alone keeps what it shows.
    s.beats[1] = { ...s.beats[1], captions: [{ voice: 'xp', title: s.beats[1].title, text: s.beats[1].text }] }
    s.beats[2] = { ...s.beats[2], captions: [{ voice: 'sell', title: 'Off', text: 'An off beat.' }] }
    const out = applyVoice(s, 'sell')
    expect(out.voice).toBe('sell')
    expect(out.beats[0]).toMatchObject({ title: 'Your work, in one place', text: 'Every task is on one board.' })
    expect(chosenVoice(out.beats[0])).toBe('sell')
    expect(out.beats[1]).toBe(s.beats[1])
    expect(out.beats[2]).toMatchObject({ title: 'Off', text: 'An off beat.' })
    // The script it was given is untouched.
    expect(s.voice).toBeUndefined()
    expect(s.beats[0].title).toBe(LIBRARY[0].title)
  })
})

describe('the library of stories', () => {
  it('gives every beat its own id', () => {
    const ids = LIBRARY.map((b) => b.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const p of PRESETS) expect(new Set(p.beats.map((b) => b.id)).size, p.id).toBe(p.beats.length)
  })

  it('gives every preset its own id and a section of the article', () => {
    const ids = PRESETS.map((p) => p.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const p of PRESETS) expect(p.section?.trim(), p.id).toBeTruthy()
  })

  it('is many stories, short ones and long ones, never a page list in between', () => {
    expect(PRESETS.length).toBeGreaterThanOrEqual(45)
    for (const p of PRESETS) {
      const n = live(p).length
      expect(n, p.id).toBeGreaterThanOrEqual(3)
      // The long film walks every page: it is the one cut past twenty beats.
      if (p.id === 'full') { expect(n).toBeGreaterThan(60); continue }
      // The short film is one minute: seven beats.
      if (p.id === 'quick') { expect(n).toBe(7); continue }
      // Short: three to five beats. Long: ten to twenty, inside what one capture takes.
      expect((n <= 5) || (n >= 10 && n <= 20), `${p.id}: ${n} beats`).toBe(true)
    }
    expect(PRESETS.filter((p) => live(p).length <= 5).length).toBeGreaterThan(20)
    expect(PRESETS.filter((p) => live(p).length >= 10).length).toBeGreaterThan(8)
  })

  it('has a title and a sentence on every beat a preset plays, and the plain caption it started with', () => {
    for (const p of PRESETS) {
      for (const b of live(p)) {
        expect(b.title.trim(), `${p.id}/${b.id}`).toBeTruthy()
        expect(b.text.trim(), `${p.id}/${b.id}`).toBeTruthy()
      }
    }
    for (const b of LIBRARY) {
      expect(b.captions?.find((c) => c.voice === 'xp'), b.id).toMatchObject({ title: b.title, text: b.text })
    }
  })

  it('writes every beat in all four voices, short and plain', () => {
    // XP wording: a title of six words at most, a sentence or two of 28,
    // no question, and none of the words that make a caption hedge or sell.
    const banned = /\b(not|no|never|nothing|simply|just|finally|real|powerful|seamless|effortless)\b/i
    const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length
    const bad: string[] = []
    for (const b of LIBRARY) {
      const voices = (b.captions ?? []).map((c) => c.voice)
      if (voices.join() !== 'xp,sell,story,tech') bad.push(`${b.id}: voices ${voices.join()}`)
      for (const c of b.captions ?? []) {
        const at = `${b.id}/${c.voice}`
        if (!c.title.trim() || !c.text.trim()) bad.push(`${at}: empty`)
        if (words(c.title) > 6) bad.push(`${at}: title of ${words(c.title)} words`)
        if (words(c.text) > 28) bad.push(`${at}: text of ${words(c.text)} words`)
        if (`${c.title} ${c.text}`.includes('?')) bad.push(`${at}: a question`)
        const word = banned.exec(`${c.title} ${c.text}`)
        if (word) bad.push(`${at}: "${word[0]}"`)
      }
    }
    expect(bad).toEqual([])
  })

  it('dresses every cut in the one look of the channel, and every cut is wide', () => {
    for (const p of PRESETS) {
      expect(p, p.id).toMatchObject({ panel: 'headline', theme: 'slightly', opening: 'stems', ending: 'plate', aspect: '16:9' })
      expect(THEMES.map((th) => th.id), p.id).toContain(p.theme)
    }
  })

  it('films every beat of the library in at least one story', () => {
    const used = new Set(PRESETS.flatMap((p) => live(p).map((b) => b.id)))
    expect(LIBRARY.filter((b) => !used.has(b.id)).map((b) => b.id)).toEqual([])
  })

  it('puts back every view a beat flips, so the next beat is photographed as the example opens', () => {
    for (const b of LIBRARY) {
      const sel = b.action?.selector ?? ''
      if (/Board view|Architecture mode|File view|Sprints view|\[aria-label="View"\]/.test(sel)) {
        expect(b.action?.after, b.id).toBeTruthy()
      }
    }
  })
})
