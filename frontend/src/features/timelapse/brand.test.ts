/**
 * Brand and redaction — the film's wardrobe, and what it may not say.
 */

import { describe, expect, it } from 'vitest'

import { ASPECTS, BRAND, aspectById, readBrand, redactedTitle, writeBrand } from './brand'
import { THEMES, groundBase, mix, themeById } from './theme'

describe('redaction', () => {
  it('keeps a title’s rhythm and none of its words', () => {
    const out = redactedTitle('Architecture Page')
    expect(out).not.toMatch(/[A-Za-z]/)
    expect(out.split(' ')).toHaveLength(2)
    expect(redactedTitle('a')).toBe('▬')
  })

  it('never grows past five words, however long the title', () => {
    expect(redactedTitle('one two three four five six seven').split(' ')).toHaveLength(5)
  })
})

describe('brand options travel in the url', () => {
  it('writes only what differs, and reads it back', () => {
    const b = { ...BRAND, title: 'Project Nightingale', theme: 'paper', redactTitles: true, render: 2 }
    const p = writeBrand(b, new URLSearchParams('project=ALPHA'))
    expect(p.get('title')).toBe('Project Nightingale')
    expect(p.get('redactTitles')).toBe('1')
    expect(p.get('render')).toBe('2')
    expect(p.has('layout')).toBe(false)
    expect(readBrand(p)).toEqual(b)
  })
})

describe('themes', () => {
  it('every theme is complete and has seven lanes', () => {
    for (const t of THEMES) {
      expect(t.lanes).toHaveLength(7)
      for (const key of ['panel', 'rule', 'ink', 'muted', 'dim', 'up', 'down'] as const) {
        expect(t[key]).toMatch(/^#[0-9A-Fa-f]{6}$/)
      }
      expect(groundBase(t.ground)).toMatch(/^#[0-9A-Fa-f]{6}$/)
    }
  })

  it('gradients run top to bottom — a GIF row of one colour compresses', () => {
    for (const t of THEMES) {
      if (typeof t.ground !== 'string') expect(t.ground.angle).toBe(90)
    }
  })

  it('falls back rather than throwing on an unknown id', () => {
    expect(themeById('nope').id).toBe(THEMES[0].id)
    expect(aspectById('nope').id).toBe('wide')
  })

  it('mixes two hexes', () => {
    expect(mix('#000000', '#ffffff', 0.5)).toBe('#808080')
  })
})

describe('shape, not size', () => {
  it('a square is not a wide frame with more height', async () => {
    const { shapeOf } = await import('./scene')
    expect(shapeOf(1200, 675)).toBe('wide')
    expect(shapeOf(1080, 1080)).toBe('square')
    expect(shapeOf(720, 1280)).toBe('tall')
    // Scale must not change the composition — only the pixels.
    expect(shapeOf(2400, 1350)).toBe('wide')
    expect(shapeOf(1440, 2560)).toBe('tall')
  })

  it('every shipped aspect resolves to a composition', () => {
    for (const a of ASPECTS) expect(['wide', 'square', 'tall']).toContain(
      a.w / a.h > 1.3 ? 'wide' : a.w / a.h > 0.8 ? 'square' : 'tall',
    )
  })
})
