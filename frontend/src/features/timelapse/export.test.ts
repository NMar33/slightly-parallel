/**
 * The GIF encoder's own parts: frames grouped into segments with a palette
 * each, and a frame reduced to the pixels that changed since the last one.
 */

import { describe, expect, it } from 'vitest'

import { __test } from './export'

const { segmentsOf, diffFrame, remember } = __test

describe('segments', () => {
  it('is one run when nothing groups the frames', () => {
    expect(segmentsOf(5)).toEqual([{ from: 0, to: 5 }])
  })

  it('cuts where the key changes, and keeps the order', () => {
    const key = (i: number) => (i < 2 ? 'title' : i < 6 ? 'board' : 'end')
    expect(segmentsOf(8, key)).toEqual([{ from: 0, to: 2 }, { from: 2, to: 6 }, { from: 6, to: 8 }])
  })
})

describe('the frame as stored', () => {
  const palette = [[0, 0, 0], [255, 255, 255], [200, 30, 30], [0, 0, 0]]
  const transparent = 3

  it('is whole when nothing was painted yet', () => {
    const { out, changed } = diffFrame(new Uint8Array([0, 1, 2]), palette, transparent, null)
    expect(Array.from(out)).toEqual([0, 1, 2])
    expect(changed).toBe(3)
  })

  it('leaves the pixels the viewer already sees transparent', () => {
    const seen = new Uint8Array(9)
    remember(new Uint8Array([0, 1, 2]), palette, seen)
    expect(Array.from(seen)).toEqual([0, 0, 0, 255, 255, 255, 200, 30, 30])
    const { out, changed } = diffFrame(new Uint8Array([0, 2, 2]), palette, transparent, seen)
    expect(Array.from(out)).toEqual([transparent, 2, transparent])
    expect(changed).toBe(1)
  })

  it('compares colours, not indices, so a new palette costs only the pixels that look different', () => {
    const seen = new Uint8Array(6)
    remember(new Uint8Array([1, 2]), palette, seen)
    const other = [[255, 255, 255], [200, 30, 30], [0, 0, 0]]
    const { out, changed } = diffFrame(new Uint8Array([0, 1]), other, 2, seen)
    expect(Array.from(out)).toEqual([2, 2])
    expect(changed).toBe(0)
  })
})
