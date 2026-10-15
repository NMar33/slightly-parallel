import { describe, expect, it } from 'vitest'
import {
  busiest,
  countOf,
  dayBars,
  daysWith,
  distribution,
  medianBucket,
  nearWords,
  num,
  pct,
  ranked,
} from './rollups'
import type { Pair } from './api'

const days: Pair[] = [
  ['2608-13', 15],
  ['2608-14', 100],
  ['2608-15', 5],
  ['2608-16', 80],
]

describe('the ranking', () => {
  it('puts the largest first and carries its share and its bar', () => {
    const rows = ranked([
      ['task', 179],
      ['turn', 1624],
      ['agent', 45],
    ])
    expect(rows.map((r) => r.label)).toEqual(['turn', 'task', 'agent'])
    expect(rows[0]).toMatchObject({ rank: 1, n: 1624, scale: 1 })
    expect(rows[0].share).toBeCloseTo(1624 / 1848, 6)
    expect(rows[2].scale).toBeCloseTo(45 / 1624, 6)
  })

  it('breaks a tie by name, so two reads of the table agree', () => {
    expect(ranked([['b', 3], ['a', 3]]).map((r) => r.label)).toEqual(['a', 'b'])
  })

  it('keeps only as many rows as it is asked for', () => {
    expect(ranked(days, 2)).toHaveLength(2)
  })

  it('answers nothing for nothing', () => {
    expect(ranked([])).toEqual([])
  })
})

describe('the median turn length', () => {
  it('marks the bucket the middle turn falls in', () => {
    const buckets = [
      { bucket: '0–10', n: 2 },
      { bucket: '10–25', n: 2 },
      { bucket: '25–50', n: 6 },
      { bucket: '50–100', n: 0 },
    ]
    const rows = distribution(buckets)
    expect(rows.filter((b) => b.median).map((b) => b.bucket)).toEqual(['25–50'])
    expect(medianBucket(buckets)).toBe('25–50')
  })

  it('marks exactly one bucket when the half falls on a boundary', () => {
    const buckets = [
      { bucket: '0–10', n: 5 },
      { bucket: '10–25', n: 5 },
    ]
    expect(distribution(buckets).filter((b) => b.median)).toHaveLength(1)
    expect(medianBucket(buckets)).toBe('0–10')
  })

  it('never marks an empty bucket, and marks nothing when there are no turns', () => {
    expect(medianBucket([{ bucket: '0–10', n: 0 }, { bucket: '10–25', n: 4 }])).toBe('10–25')
    expect(medianBucket([{ bucket: '0–10', n: 0 }])).toBe('')
    expect(medianBucket([])).toBe('')
  })

  it('scales each bar against the tallest bucket and shares against the whole', () => {
    const rows = distribution([
      { bucket: '0–10', n: 1 },
      { bucket: '10–25', n: 3 },
    ])
    expect(rows[0].scale).toBeCloseTo(1 / 3, 6)
    expect(rows[1].scale).toBe(1)
    expect(rows[0].share).toBeCloseTo(0.25, 6)
  })
})

describe('the day band', () => {
  it('holds one bar per day of the index, in date order', () => {
    const bars = dayBars([...days].reverse())
    expect(bars.map((b) => b.day)).toEqual(['2608-13', '2608-14', '2608-15', '2608-16'])
    expect(bars[1].scale).toBe(1)
    expect(bars[0].scale).toBeCloseTo(15 / 100, 6)
  })

  it('reads a day against every row when there is no word', () => {
    const bars = dayBars(days)
    expect(bars[1].shareOfAll).toBeCloseTo(100 / 200, 6)
    expect(bars[1].shareOfDay).toBe(1)
  })

  it('reads a word against the day it was said in, and keeps the empty days', () => {
    const bars = dayBars(days, [['2608-14', 25], ['2608-16', 5]])
    expect(bars.map((b) => b.n)).toEqual([0, 25, 0, 5])
    expect(bars.map((b) => b.base)).toEqual([15, 100, 5, 80])
    expect(bars[1].shareOfDay).toBeCloseTo(0.25, 6)
    expect(bars[3].shareOfDay).toBeCloseTo(5 / 80, 6)
    expect(bars[1].shareOfAll).toBeCloseTo(25 / 30, 6)
    // The word's bar is drawn against the busiest day of the whole index,
    // so it sits inside the pale bar behind it.
    expect(bars[1].scale).toBeCloseTo(25 / 100, 6)
    expect(bars[1].baseScale).toBe(1)
  })

  it('names the day that carries the most, and counts the days that carry anything', () => {
    const bars = dayBars(days, [['2608-14', 2], ['2608-16', 9]])
    expect(busiest(bars)?.day).toBe('2608-16')
    expect(daysWith(bars)).toBe(2)
    expect(busiest(dayBars(days))?.day).toBe('2608-14')
    expect(busiest([])).toBeNull()
  })
})

describe('the words nearby', () => {
  it('ranks by lift, then by how many rows hold the word', () => {
    const rows = nearWords([
      { word: 'a', n: 3, lift: 2 },
      { word: 'b', n: 9, lift: 14.3 },
      { word: 'c', n: 2, lift: 14.3 },
    ])
    expect(rows.map((r) => r.word)).toEqual(['b', 'c', 'a'])
    // The lift ties at the top of this list, so the bar carries the count.
    expect(rows[0].scale).toBe(1)
    expect(rows[1].scale).toBeCloseTo(2 / 9, 6)
    expect(rows[2].scale).toBeCloseTo(3 / 9, 6)
  })
})

describe('the small readings', () => {
  it('writes a count and a share the way a table writes them', () => {
    expect(num(252619)).toBe('252,619')
    expect(pct(157, 2244)).toBe('7.0%')
    expect(pct(1, 0)).toBe('0%')
    expect(pct(1, 100000)).toBe('<0.1%')
    expect(pct(0, 10)).toBe('0.0%')
    // A part short of the whole is not all of it.
    expect(pct(19999, 20000)).toBe('>99.9%')
    expect(pct(10, 10)).toBe('100.0%')
  })

  it('finds one count', () => {
    expect(countOf(days, '2608-14')).toBe(100)
    expect(countOf(days, 'nothing')).toBe(0)
  })
})
