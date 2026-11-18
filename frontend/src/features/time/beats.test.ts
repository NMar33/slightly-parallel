import { describe, expect, it } from 'vitest'

import { BEAT_MS, Beater, READING_MS, type BeatSource } from './beats'
import type { WorkContext } from '../../lib/timer'

function world(present = true) {
  const sent: Array<[string, string, BeatSource]> = []
  const w = { now: 1_000_000, present }
  const b = new Beater('window', (work, source) => sent.push([work.project, work.taskId ?? '', source]), () => w.now, () => w.present)
  return { b, sent, w }
}
const X: WorkContext = { project: 'harbor', taskId: 'tk_1' }
const Y: WorkContext = { project: 'kelp' }

describe('beats from the terminal window', () => {
  it('the first input after a quiet spell beats at once, the rest wait for the next beat', () => {
    const { b, sent, w } = world()
    b.input(X)
    expect(sent).toEqual([['harbor', 'tk_1', 'window']])
    w.now += 5_000
    b.input(X)
    expect(sent).toHaveLength(1)
    w.now += BEAT_MS
    expect(b.beat(X)).toBe(true)
    expect(sent).toHaveLength(2)
  })

  it('reading with no input counts for two minutes, then stops', () => {
    const { b, sent, w } = world()
    b.input(X)
    w.now += READING_MS
    expect(b.beat(X)).toBe(true)
    w.now += 1
    expect(b.beat(X)).toBe(false)
    expect(sent).toHaveLength(2)
  })

  it('a window not in front sends nothing, input or not', () => {
    const { b, sent } = world(false)
    b.input(X)
    expect(b.beat(X)).toBe(false)
    expect(sent).toEqual([])
  })

  it('another tab in front: the next beat names its project', () => {
    const { b, sent, w } = world()
    b.input(X)
    w.now += 3_000
    expect(b.beat(Y)).toBe(true)
    expect(sent.map((s) => s[0])).toEqual(['harbor', 'kelp'])
  })

  it('no project, no beat', () => {
    const { b, sent } = world()
    b.input(null)
    expect(sent).toEqual([])
  })
})
