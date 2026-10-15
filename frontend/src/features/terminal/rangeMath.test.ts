import { describe, expect, it } from 'vitest'

import { absOf, relOf, rowOf } from './rangeMath'

describe('the gutter arithmetic', () => {
  const at = { history: 1000, scroll: 0, rows: 40 }
  const up = { history: 1000, scroll: 25, rows: 40 }

  it('anchors a clicked row to an absolute line, and finds it again after a scroll', () => {
    const abs = absOf(10, at)
    expect(abs).toBe(1010)
    // Scrolled 25 up, the same line sits 25 rows lower on screen.
    expect(rowOf(abs, up)).toBe(35)
    // And the anchor round-trips from there.
    expect(absOf(35, up)).toBe(abs)
  })

  it('numbers rows back from the newest: 0 at the bottom, more negative above and when scrolled', () => {
    expect(relOf(at.rows - 1, at)).toBe(0)
    expect(relOf(0, at)).toBe(-39)
    expect(relOf(at.rows - 1, up)).toBe(-25)
  })

  it('keeps an anchor pointed at the same text while new output streams in', () => {
    const abs = absOf(10, at)
    // Twelve new lines arrived: history grew, the line moved up the screen.
    const later = { history: 1012, scroll: 0, rows: 40 }
    expect(rowOf(abs, later)).toBe(-2) // just off the top — the edge pill's case
  })
})
