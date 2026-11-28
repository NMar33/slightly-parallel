import { describe, expect, it } from 'vitest'
import { laneOf, laneUpdate } from './model'
import type { TaskRow } from './model'

describe('laneUpdate', () => {
  it('clears the assignee for the unassigned lane, so the card stays where it was dropped', () => {
    const moved = { id: 'tk_1', assignee: 'alice', lane: 'alice' } as unknown as TaskRow
    const after = { ...moved, ...laneUpdate('unassigned') }
    expect(laneOf(after)).toBe('unassigned')
  })
  it('names a person lane, and writes nothing on a board without lanes', () => {
    expect(laneUpdate('bob')).toEqual({ assignee: 'bob', lane: 'bob' })
    expect(laneUpdate(undefined)).toEqual({})
    expect(laneUpdate('')).toEqual({})
  })
})

it('writes an empty row and a named unassigned row differently', () => {
  expect(laneUpdate({ project: 'alpha', name: '' })).toEqual({ assignee: '', lane: '' })
  expect(laneUpdate({ project: 'alpha', name: 'unassigned' }))
    .toEqual({ assignee: 'unassigned', lane: 'unassigned' })
})
