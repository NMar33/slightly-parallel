import { describe, it, expect } from 'vitest'
import { foldGroups, foldLinks, foldMarks } from './timelineFold'
import type { AgentMeta } from '../../components/AgentTimeline/AgentTimeline'

const A = (id: string, group: string, from: string, to: string): AgentMeta =>
  ({ agent_id: id, agent_name: id, agent_group: group, created_date: from, last_active: to, message_count: 2 })

describe('foldGroups', () => {
  const agents = [A('a', 'g', '2026-09-01', '2026-09-02'), A('b', '', '2026-09-03', '2026-09-03'), A('c', 'g', '2026-09-05', '2026-09-06')]
  it('turns a folded group into one lane with every member as a piece', () => {
    const f = foldGroups(agents, new Set(['g']))
    expect(f.agents.map((a) => a.agent_id)).toEqual(['group:g', 'b'])
    const g = f.agents[0]!
    expect([g.created_date, g.last_active, g.message_count]).toEqual(['2026-09-01', '2026-09-06', 4])
    expect(g.members).toEqual(['a', 'c'])
    expect(g.spans).toHaveLength(2)
    expect(f.laneOf('c')).toBe('group:g')
    expect(f.laneOf('b')).toBe('b')
  })
  it('leaves an unfolded group as it is', () => {
    expect(foldGroups(agents, new Set()).agents.map((a) => a.agent_id)).toEqual(['a', 'b', 'c'])
  })
  it('moves marks onto the group lane and drops links inside it', () => {
    const f = foldGroups(agents, new Set(['g']))
    const m = { task_id: 't', title: '', at: '2026-09-01T10:00:00', role: 'user' as const }
    expect(Object.keys(foldMarks({ a: [m], c: [m], b: [m] }, f.laneOf)).sort()).toEqual(['b', 'group:g'])
    const L = (from: string, to: string) => ({ id: from + to, from_id: from, to_id: to, kind: 'branch', style: 'solid', note: '' })
    expect(foldLinks([L('a', 'c'), L('a', 'b')], f.laneOf)).toEqual([{ ...L('a', 'b'), from_id: 'group:g' }])
  })
})
