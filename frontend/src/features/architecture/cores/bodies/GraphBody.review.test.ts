// Review finding: the backend's agent.tasks (corelib._agents_of) takes the
// tasks of every commit the agent made, chat-found ones included. buildGraph
// draws a solid task→agent line from agent.tasks before it reads the commits,
// so (a) with the chat commits hidden the line and the agent stay, and (b)
// with them shown the line is never dashed. Live: Code audit rounds,
// cc-56a11b0e (turns 0, 4 commits, all "chat").
import { describe, expect, it } from 'vitest'

import type { CoreDetail } from '../data'
import { buildGraph, withoutChatCommits } from './GraphBody'

const core: CoreDetail = {
  id: 'cr_1', project: 'alpha', name: 'Audit rounds', type: 'workflow', reason: '', status: 'view', position: '1',
  tracking_on: '', tracking_until: '', created_at: '2026-10-18T11:20:00', updated_at: '', actor: 'operator', off_at: '',
  tracking: { on: false, until: '', days_left: null, expired: false }, grid: [],
  notes: [], links: [], events: [], nearby: [],
  tasks: [{ id: 'tk_aaaaaaaa', title: 'audit round', status: 'done', archived_at: '', created_date: '2610-20' }],
  files: [{ path: 'a.py', lines_add: 5, lines_del: 0, tasks: ['tk_aaaaaaaa'] }],
  commits_n: 1,
  commits: [{ sha: 'abc1234', at: '2026-10-20T14:39:19', subject: 'fix', how: 'chat', agent: 'cc-z', tasks: ['tk_aaaaaaaa'], files: ['a.py'] }],
  // As the backend sends it: the chat-found commit put the task on the agent; it never had a turn on it.
  agents: [{ agent_id: 'cc-z', tasks: ['tk_aaaaaaaa'], commits: 1, notes: 0, turns: 0, sessions: 0, last_at: '2026-10-20T14:39:19' }],
}

describe('the graph and the commits found by the chat only', () => {
  it('hides the task→agent line when its only commit is a chat one', () => {
    const g = buildGraph(withoutChatCommits(core), 'everyone')
    expect(g.edges.find((e) => e.a === 't:tk_aaaaaaaa' && e.b === 'a:cc-z')).toBeUndefined()   // found: a solid line
  })

  it('draws that line dashed when the chat commits are shown', () => {
    const g = buildGraph(core, 'everyone')
    expect(g.edges.find((e) => e.a === 't:tk_aaaaaaaa' && e.b === 'a:cc-z')?.chat).toBe(true)   // found: false
  })
})
