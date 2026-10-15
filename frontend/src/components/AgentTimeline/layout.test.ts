/**
 * Unit tests for the timeline's pure layout maths (layout.ts): lane
 * ordering with groups, name truncation and link geometry.
 */

import { describe, it, expect } from 'vitest'

import { bezierMidpoint, bezierPath, buildGroups, buildLanes, truncate } from './layout'

describe('buildLanes / buildGroups', () => {
  it('pulls a group together at its first member and brackets it once', () => {
    const lanes = buildLanes([
      { agent_id: 'a', agent_group: 'g', created_date: '2608-01', last_active: '2608-02' },
      { agent_id: 'b', created_date: '2608-02', last_active: '2608-03' },
      { agent_id: 'c', agent_group: 'g', created_date: '2608-03', last_active: '2608-04' },
    ])
    expect(lanes.map((l) => l.agent.agent_id)).toEqual(['a', 'c', 'b'])
    expect(lanes.map((l) => l.index)).toEqual([0, 1, 2])
    expect(buildGroups(lanes)).toEqual([{ name: 'g', first: 0, last: 1, color: 'var(--lane-1)' }])
  })

  it('drops rows whose created date does not parse', () => {
    expect(buildLanes([{ agent_id: 'x', created_date: 'nope', last_active: '' }])).toEqual([])
  })
})

describe('truncate', () => {
  it('keeps short names and ellipsises long ones code-point safely', () => {
    expect(truncate('рекогниция', 20)).toBe('рекогниция')
    expect(truncate('рекогниция', 5)).toBe('реко…')
  })
})

describe('bezier geometry', () => {
  it('puts the midpoint halfway on a horizontal link', () => {
    expect(bezierMidpoint(0, 10, 100, 10)).toEqual([50, 10])
    expect(bezierPath(0, 10, 100, 10)).toBe('M 0 10 C 40 10, 60 10, 100 10')
  })
})
