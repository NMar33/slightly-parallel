import { describe, expect, it } from 'vitest'

import {
  fmtLines,
  fmtMinutes,
  groupProfiles,
  profileHeadline,
  sumTotals,
  taskTone,
  toolOfProfile,
  type AgentProfile,
  type ProfileTotals,
} from './profile'

const totals = (over: Partial<ProfileTotals> = {}): ProfileTotals => ({
  sessions_n: 0, minutes: 0, turns: 0, days_active: 0, scans_n: 0, files_n: 0,
  lines_add: 0, lines_del: 0, file_entries_n: 0, decisions_n: 0,
  architecture_n: 0, features_n: 0, problems_n: 0, bugs_resolved_n: 0, rules_n: 0,
  standups_n: 0, tasks_n: 0, tasks_handed_n: 0, tasks_done_n: 0, links_n: 0,
  ...over,
})

function profile(id: string, over: Partial<AgentProfile['agent']> = {}, t: Partial<ProfileTotals> = {}): AgentProfile {
  return {
    agent: {
      agent_id: id, agent_name: id, project: 'p', created_date: '2608-20', last_active: '2026-08-21T10:00:00',
      message_count: 0, files_touched: [], ...over,
    },
    origin: { tool: '', cwd: '', session_ref: '', capture: '', chat_path: '' },
    totals: totals(t),
    by_day: [], by_hour: new Array(24).fill(0), architecture_kinds: {},
    sessions: [], scans: [], files: [], decisions: [], architecture: [], problems: [],
    rules: [], tasks: [], links: [], parent: null, children: [],
    group: { name: over.agent_group ?? '', members: [] },
  }
}

describe('formatting', () => {
  it('prints minutes as wall clock, never fractional hours', () => {
    expect(fmtMinutes(0)).toBe('—')
    expect(fmtMinutes(45)).toBe('45m')
    expect(fmtMinutes(60)).toBe('1h 00m')
    expect(fmtMinutes(2503)).toBe('41h 43m')
  })
  it('prints lines with signs and a dash when nothing was reported', () => {
    expect(fmtLines(0, 0)).toBe('—')
    expect(fmtLines(1700, 85)).toBe('+1,700 / −85')
  })
  it('maps task statuses to three tones', () => {
    expect(taskTone('done')).toBe('done')
    expect(taskTone('done-archived')).toBe('done')
    expect(taskTone('doing')).toBe('doing')
    expect(taskTone('review')).toBe('doing')
    expect(taskTone('todo')).toBe('open')
  })
})

describe('groupProfiles', () => {
  it('keeps grouped agents together at the position of the first member, ungrouped in place', () => {
    const ps = [
      profile('a'),
      profile('b', { agent_group: 'g' }),
      profile('c'),
      profile('d', { agent_group: 'g' }),
      profile('e', { agent_group: 'h' }),
    ]
    const sections = groupProfiles(ps)
    expect(sections.map((s) => [s.name, s.members.map((m) => m.agent.agent_id)])).toEqual([
      ['', ['a', 'c']],
      ['g', ['b', 'd']],
      ['h', ['e']],
    ])
  })
})

describe('sumTotals', () => {
  it('adds every counter across the fleet', () => {
    const s = sumTotals([
      profile('a', {}, { minutes: 10, lines_add: 5, tasks_done_n: 1 }),
      profile('b', {}, { minutes: 20, lines_add: 7, tasks_done_n: 2, features_n: 3 }),
    ])
    expect(s.minutes).toBe(30)
    expect(s.lines_add).toBe(12)
    expect(s.tasks_done_n).toBe(3)
    expect(s.features_n).toBe(3)
  })
  it('is all zeros for an empty fleet', () => {
    expect(sumTotals([]).minutes).toBe(0)
  })
})

describe('headline and tool', () => {
  it('prefers the meta headline, then the last session', () => {
    const p = profile('x')
    expect(profileHeadline(p)).toBe('')
    p.sessions = [{ id: 's', created_date: '2608-20', start_time: '09:00', end_time: '09:10', duration_min: 10, turns_n: 1, l1: 'session line' }]
    expect(profileHeadline(p)).toBe('session line')
    p.agent.l1_headline = 'meta line'
    expect(profileHeadline(p)).toBe('meta line')
  })
  it('reads the tool from meta, else from the id prefix', () => {
    expect(toolOfProfile(profile('cc-abc'))).toBe('claude-code')
    expect(toolOfProfile(profile('codex-abc'))).toBe('codex')
    expect(toolOfProfile(profile('oc-abc'))).toBe('opencode')
    const p = profile('weird'); p.origin.tool = 'codex'
    expect(toolOfProfile(p)).toBe('codex')
    expect(toolOfProfile(profile('weird'))).toBe('')
  })
})
