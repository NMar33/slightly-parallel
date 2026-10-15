import { describe, expect, it } from 'vitest'
import { replaceLast, turnRef } from './turns'

const turns = [
  { n: 1, date: '', time: '', text: 'write the release' },
  { n: 2, date: '2608-29', time: '22:55', text: 'now the press release' },
]

describe('turnRef', () => {
  it('keeps the bare id for turn 1 so old copies are unchanged', () => {
    expect(turnRef('tk_28b1b490', 1)).toBe('tk_28b1b490')
    expect(turnRef('tk_28b1b490', 2)).toBe('tk_28b1b490.2')
  })
})

describe('replaceLast', () => {
  it('re-words the newest round and keeps its stamp', () => {
    expect(replaceLast(turns, 'SECOND')).toEqual([turns[0], { ...turns[1], text: 'SECOND' }])
  })
  it('gives an empty task a description rather than a turn 2', () => {
    expect(replaceLast([], 'born')).toEqual([{ n: 1, date: '', time: '', text: 'born' }])
    expect(replaceLast([], '  ')).toEqual([])
  })
})
