import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { TypingBatcher } from './typing'

describe('typing ticks', () => {
  let now = 0
  const sent: Array<[string, number]> = []
  const make = (answer: 'ok' | 'gone' = 'ok') => new TypingBatcher((sid, keys) => { sent.push([sid, keys]); return answer }, 15_000, () => now)

  beforeEach(() => { vi.useFakeTimers(); now = 1_000_000; sent.length = 0 })
  afterEach(() => { vi.useRealTimers() })

  const advance = async (ms: number) => { now += ms; await vi.advanceTimersByTimeAsync(ms) }

  it('sends the first key at once, then the keys typed meanwhile once the 15 s have passed', async () => {
    const b = make()
    b.tick('t1')
    await Promise.resolve()
    expect(sent).toEqual([['t1', 1]])
    b.tick('t1'); b.tick('t1'); b.tick('t2')
    await advance(14_000)
    expect(sent).toHaveLength(1)
    await advance(1_000)
    expect(sent).toEqual([['t1', 1], ['t1', 2], ['t2', 1]])
  })

  it('never sends more often than every 15 s, and sends nothing when nothing was typed', async () => {
    const b = make()
    for (let i = 0; i < 60; i++) { b.tick('t1'); await advance(1_000) }
    // 60 s of typing: at 0, 15, 30, 45 and 60 s.
    expect(sent.length).toBeLessThanOrEqual(5)
    expect(sent.reduce((n, [, k]) => n + k, 0) + b.pending('t1')).toBe(60)
    const before = sent.length
    await advance(60_000)
    expect(sent.length).toBe(before + (b.pending('t1') ? 1 : 0))
  })

  it('sends counts only: the sid and a number', async () => {
    const b = make()
    b.tick('t1', 3)
    await Promise.resolve()
    expect(sent[0]).toEqual(['t1', 3])
  })

  it('stops for good when the server has no typing route', async () => {
    const b = make('gone')
    b.tick('t1')
    await Promise.resolve()
    expect(b.stopped).toBe(true)
    b.tick('t1')
    await advance(30_000)
    expect(sent).toHaveLength(1)
  })

  it('sends what is counted when the page goes away', async () => {
    const b = make()
    b.tick('t1'); await Promise.resolve()
    b.tick('t1'); b.tick('t1')
    await b.flush()
    expect(sent).toEqual([['t1', 1], ['t1', 2]])
  })
})
