import { describe, expect, it } from 'vitest'

import type { CoreDetail } from '../../architecture/cores/data'
import type { Topic } from '../../entrypoints/desk/data'
import type { Card } from '../../publish/data'
import { agentTasks, agentView, CommitCheck, coreView, decisionView, entryView, pageOf, publishView, skillView } from './records'

describe('what each card shows of its record', () => {
  it('a decision: what was decided, why, the options not taken, its weight and day', () => {
    const d = decisionView({
      metadata: { id: 'dc_0badc0de', decision_text: 'row text', rationale: 'row why', weight: 'major', created_date: '2611-18', created_time: '10:42:00', project: 'merkhet', agent_id: 'cc-676175ea' },
      text: {
        decision: 'Hashes are checked by the server before they underline',
        why: 'A hex word is not a commit.',
        alternatives: ['Underline every hex run — rejected: false links', 'Chosen: ask the repository', 'Something in no shape'],
      },
    })
    expect(d).toMatchObject({ decision: 'Hashes are checked by the server before they underline', why: 'A hex word is not a commit.', weight: 'major', day: '2611-18', project: 'merkhet', agent: 'cc-676175ea' })
    expect(d.rejected).toEqual([
      { option: 'Underline every hex run', verdict: 'rejected', reason: 'false links' },
      { option: 'Something in no shape', verdict: 'other', reason: '' },
    ])
    // An older answer with the row only.
    expect(decisionView({ metadata: { id: 'dc_1', decision_text: 'row text', rationale: 'row why' } })).toMatchObject({ decision: 'row text', why: 'row why', rejected: [] })
  })

  it('a Publish card: the text, the context, and everything attached counted', () => {
    const c = { id: 'pu_1a2b3c4d', project: 'merkhet', at: '2026-11-18T10:00:00', message: 'msg', text: 'The card text', context: ' ctx ',
      tasks: [{}, {}], notes: [{}], cores: [{}], commits: [{}, {}, {}], images: [{}], links: [], files: [{}], placements: [{}] } as unknown as Card
    expect(publishView(c)).toEqual({ id: 'pu_1a2b3c4d', project: 'merkhet', at: '2026-11-18T10:00:00', text: 'The card text', context: 'ctx', attachments: 9, placed: 1 })
    expect(publishView({ ...c, text: '' }).text).toBe('msg')
  })

  it('a core: name, type, reason, the last three notes newest first, its live tasks', () => {
    const note = (id: string, at: string) => ({ id, at, author: 'operator', text: `note ${id}`, comment: '' })
    const v = coreView({ id: 'cr_00ff00aa', project: 'merkhet', name: 'Terminal window', type: 'interface', reason: 'Where the operator works', status: 'view',
      notes: [note('a', '2026-11-01T10:00'), note('b', '2026-11-03T10:00'), note('c', '2026-11-02T10:00'), note('d', '2026-11-04T10:00')],
      tasks: [{ id: 'tk_1', title: 'one', status: 'doing', archived_at: '' }, { id: 'tk_2', title: 'gone', status: 'done', archived_at: '2026-11-01' }] } as unknown as CoreDetail)
    expect(v).toMatchObject({ name: 'Terminal window', type: 'interface', reason: 'Where the operator works', off: false, notesN: 4 })
    expect(v.notes.map((n) => n.id)).toEqual(['d', 'b', 'c'])
    expect(v.tasks).toEqual([{ id: 'tk_1', title: 'one', status: 'doing' }])
  })

  it('a skill: its name and description, SKILL.md without the --- block, where it is installed', () => {
    const v = skillView({
      metadata: { id: 'sk_abcdef01', name: '', description: '', status: 'active' },
      skill: { current: { n: 3, skill_md: '---\nname: write-a-note\ndescription: Write a note for the operator\n---\n# Write a note\n\nSteps.' },
        installs: [{ project: 'merkhet', status: 'fresh' }, { project: 'other', status: 'missing' }] },
    })
    expect(v).toEqual({ id: 'sk_abcdef01', name: 'write-a-note', description: 'Write a note for the operator', status: 'active', version: 3, body: '# Write a note\n\nSteps.', installedIn: ['merkhet'] })
  })

  it('an entry point: its question, what it is, where it stopped and its shots', () => {
    const v = entryView({ id: 'ep_12345678', project: 'merkhet', name: '', title: 'How do I run the sandbox?', what: 'The sandbox server.', state: 'active',
      stops: [{ id: 's1', at: '2026-11-18T09:00', author: 'cc-1', text: 'Started it', task_id: '', turn: 1 }],
      shots: [{ id: 'sh1', src: '/api/entrypoints/shots/sh1/file', caption: 'Home' }], open_tasks: 2 } as unknown as Topic)
    expect(v).toMatchObject({ name: 'How do I run the sandbox?', question: 'How do I run the sandbox?', what: 'The sandbox server.', openTasks: 2 })
    expect(v.stops).toEqual([{ at: '2026-11-18T09:00', author: 'cc-1', text: 'Started it' }])
    expect(v.shots).toEqual([{ id: 'sh1', src: '/api/entrypoints/shots/sh1/file', caption: 'Home' }])
  })

  it('a chat: its name, and whether it can be resumed and branched', () => {
    const a = (tool: string, ref = 'abc-123') => agentView({ agent: { agent_id: 'cc-676175ea', agent_name: 'messages', tool, session_ref: ref, project: 'merkhet', last_active: '2026-11-18T10:00' } })
    expect(a('claude-code')).toMatchObject({ name: 'messages', project: 'merkhet', canResume: true, canBranch: true })
    expect(a('opencode')).toMatchObject({ canResume: true, canBranch: false })
    expect(a('cursor')).toMatchObject({ canResume: false, canBranch: false })
    expect(a('claude-code', '-rf')).toMatchObject({ canResume: false, canBranch: false })
    expect(a('claude-code', '')).toMatchObject({ canResume: false })
  })

  it('a chat\'s tasks: each once, the last named first', () => {
    expect(agentTasks({ 'cc-1': [
      { task_id: 'tk_a', title: 'A', at: '2026-11-18T09:00' }, { task_id: 'tk_b', title: 'B', at: '2026-11-18T10:00' }, { task_id: 'tk_a', title: 'A', at: '2026-11-18T11:00' },
    ], 'cc-2': [{ task_id: 'tk_c', title: 'C', at: '2026-11-18T12:00' }] }, 'cc-1')).toEqual([{ id: 'tk_a', title: 'A' }, { id: 'tk_b', title: 'B' }])
  })

  it('links each record to its place on its page', () => {
    expect(pageOf.decision('merkhet', '2611-18')).toBe('/decisions#project=merkhet&month=2026-11&day=2611-18')
    expect(pageOf.publish('merkhet')).toBe('/publish#project=merkhet')
    expect(pageOf.core('merkhet', 'cr_00ff00aa')).toBe('/architecture#project=merkhet&core=cr_00ff00aa')
    expect(pageOf.skill('sk_abcdef01')).toBe('/skills#skill=sk_abcdef01')
    expect(pageOf.entrypoint('ep_12345678')).toBe('/entrypoints?topic=ep_12345678')
    expect(pageOf.agent('cc-676175ea')).toBe('/agent/cc-676175ea')
  })
})

describe('which hashes are commits of the terminal\'s project', () => {
  it('asks the server once per hash; a 404 is no, a failure is asked again', async () => {
    const asked: string[] = []
    let down = true
    const check = new CommitCheck('merkhet', async (url) => {
      asked.push(url)
      if (url.includes('47feacd0')) return {}
      if (url.includes('d3adbeef') && down) throw new TypeError('network')
      throw Object.assign(new Error('Not Found'), { status: 404 })
    })
    expect(check.known('47feacd0')).toBeUndefined()
    expect(await check.check('47feacd0')).toBe(true)
    expect(await check.check('47feacd0')).toBe(true)
    expect(check.known('47feacd0')).toBe(true)
    expect(await check.check('a1b2c3d4')).toBe(false)
    expect(await check.check('a1b2c3d4')).toBe(false)
    expect(check.known('a1b2c3d4')).toBe(false)
    expect(asked).toEqual(['/api/git/commit?repo=merkhet&sha=47feacd0', '/api/git/commit?repo=merkhet&sha=a1b2c3d4'])
    expect(await check.check('d3adbeef')).toBe(false)
    expect(check.known('d3adbeef')).toBeUndefined()
    down = false
    expect(await check.check('d3adbeef')).toBe(false)
    expect(asked.filter((u) => u.includes('d3adbeef'))).toHaveLength(2)
  })

  it('a terminal with no project has no commits to ask about', async () => {
    let asked = 0
    expect(await new CommitCheck('', async () => { asked++; return {} }).check('47feacd0')).toBe(false)
    expect(asked).toBe(0)
  })
})
