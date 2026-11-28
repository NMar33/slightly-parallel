import { describe, expect, it } from 'vitest'

import { limitChoices, needsCloseConfirmation, projectedMemory, triageTerminals } from './limitModel'
import type { TerminalLimitSession } from '../../../lib/terminalLimit'

const today = Date.parse('2026-11-27T11:45:00') / 1000
const day = 86400
const row = (id: string, input: Partial<TerminalLimitSession>): TerminalLimitSession => ({
  id, label: id, agent_id: '', agent_kind: 'shell', project: 'alpha',
  created: '2026-11-27T10:00:00', last_activity: today, last_opened: null,
  recent_output: false, attached: false, running: false, activity: 0, memory_bytes: 5, ...input,
})

describe('terminal limit', () => {
  it('includes the exact saved limit and the unlimited setting on the slider', () => {
    expect(limitChoices(36, 256)).toEqual([1, 32, 36, 64, 128, 256, 0])
    expect(limitChoices(32, 256)).toEqual([1, 32, 64, 128, 256, 0])
  })

  it('requires confirmation if either foreground or attachment state is unknown', () => {
    expect(needsCloseConfirmation(row('shell', { foreground_known: true, attachment_known: true }))).toBe(false)
    expect(needsCloseConfirmation(row('foreground', { foreground_known: false }))).toBe(true)
    expect(needsCloseConfirmation(row('attachment', { attachment_known: false }))).toBe(true)
  })

  it('estimates from the measured per-kind means and the running mix', () => {
    const kinds = {
      claude: { count: 3, measured: 2, bytes: 400 },
      codex: { count: 1, measured: 1, bytes: 40 },
      opencode: { count: 0, measured: 0, bytes: 0 },
      shell: { count: 0, measured: 0, bytes: 0 },
    }
    expect(projectedMemory(kinds, 8)).toBe(1280)
    expect(projectedMemory(kinds, 0)).toBeNull()
    expect(projectedMemory({ ...kinds, claude: { count: 3, measured: 0, bytes: 0 } }, 8)).toBeNull()
  })
})

describe('terminal triage', () => {
  const rows = [
    row('now', { recent_output: true, memory_bytes: 8 }),
    row('current', { attached: true, agent_kind: 'codex', activity: 4 }),
    row('yesterday', { created: '2026-11-26T08:00:00', last_activity: today - 5 * day, memory_bytes: 4 }),
    row('older', { created: '2026-11-09T08:00:00', last_activity: today - 12 * day, memory_bytes: 2 }),
    row('beta', { project: 'beta', agent_kind: 'codex', attached: true, memory_bytes: 30 }),
  ]
  const defaults = { project: '', agent: '', state: '', inactiveDays: 0, sort: 'last_activity', descending: true, group: '' } as const
  const ids = (groups: ReturnType<typeof triageTerminals>) => groups.map(({ rows }) => rows.map(({ id }) => id))

  it('combines project, agent, and state filters', () => {
    expect(ids(triageTerminals(rows, { ...defaults, project: 'alpha', agent: 'codex', state: 'attached' }, today))).toEqual([['current']])
    expect(ids(triageTerminals(rows, { ...defaults, state: 'running' }, today))).toEqual([['now']])
  })

  it('combines an inactivity cutoff with sorting and date grouping', () => {
    expect(ids(triageTerminals(rows, { ...defaults, inactiveDays: 3, sort: 'memory_bytes', descending: false }, today)))
      .toEqual([['older', 'yesterday']])
    expect(ids(triageTerminals(rows, { ...defaults, group: 'date' }, today)))
      .toEqual([['now', 'current', 'beta'], ['yesterday'], ['older']])
  })

  it('sorts the rows within project groups by activity', () => {
    expect(ids(triageTerminals(rows, { ...defaults, group: 'project', sort: 'activity' }, today)))
      .toEqual([['current', 'now', 'yesterday', 'older'], ['beta']])
  })
})
