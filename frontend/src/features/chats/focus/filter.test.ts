import { describe, expect, it } from 'vitest'

import { todayKey } from '../../daybook/data'
import type { Row } from '../data'
import { activeCount, applyFilter, NO_FILTER } from './filter'

const row = (id: string, agent: string, day: string, extra: Partial<Row> = {}) => ({
  id, agent_id: agent, created_date: day, project: 'p', start_time: '10:00', end_time: '10:05',
  duration_min: 5, turns_n: 2, l1: id, produced: {}, marks: {}, git: { commits: 0 }, tasks: 0, matches: 0,
  agent: { agent_id: agent, agent_group: agent === 'b' ? 'team' : '' }, ...extra,
}) as unknown as Row

const rows = [row('1', 'a', todayKey()), row('2', 'b', '2601-01'), row('3', 'c', todayKey(), { turns_n: 12 })]

describe('the focus filter', () => {
  it('keeps any of the agents picked, a group standing for its members', () => {
    expect(applyFilter(rows, { ...NO_FILTER, agents: ['a', 'c'] }).map((r) => r.id)).toEqual(['1', '3'])
    expect(applyFilter(rows, { ...NO_FILTER, agents: ['group:team'] }).map((r) => r.id)).toEqual(['2'])
  })
  it('cuts by when and by what a chat has, all at once', () => {
    expect(applyFilter(rows, { ...NO_FILTER, period: '1' }).map((r) => r.id)).toEqual(['1', '3'])
    const f = { ...NO_FILTER, period: '1' as const, chips: ['turns10' as const] }
    expect(applyFilter(rows, f).map((r) => r.id)).toEqual(['3'])
    expect(activeCount(f)).toBe(2)
  })
})
