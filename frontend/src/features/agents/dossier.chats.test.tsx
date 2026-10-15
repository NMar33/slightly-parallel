import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { AgentDossier } from './dossier'
import type { AgentProfile, ProfileTotals } from './profile'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const totals = {
  sessions_n: 2, minutes: 30, turns: 5, days_active: 1, scans_n: 0, files_n: 0, lines_add: 0, lines_del: 0,
  file_entries_n: 0, decisions_n: 0, architecture_n: 0, features_n: 0, problems_n: 0, bugs_resolved_n: 0,
  rules_n: 0, standups_n: 0, tasks_n: 0, tasks_handed_n: 0, tasks_done_n: 0, links_n: 0,
} as ProfileTotals
const profile = (newestTurns: number): AgentProfile => ({
  agent: { agent_id: 'cc-x', agent_name: 'x', project: 'p', created_date: '2608-20', last_active: '2026-08-21T10:00:00', message_count: 5, files_touched: [] },
  origin: { tool: 'claude-code', cwd: '/work/p', session_ref: 'abc', capture: 'hooks', chat_path: '' },
  totals, by_day: [], by_hour: new Array(24).fill(0), architecture_kinds: {},
  sessions: [
    { id: 'ses_1', created_date: '2608-20', start_time: '09:00', end_time: '09:10', duration_min: 10, turns_n: 2, l1: 'first session' },
    { id: 'ses_2', created_date: '2608-20', start_time: '11:00', end_time: '11:20', duration_min: 20, turns_n: newestTurns, l1: 'second session' },
  ],
  scans: [], files: [], decisions: [], architecture: [], problems: [], rules: [], tasks: [],
  links: [], parent: null, children: [], group: { name: '', members: [] },
})

describe('the dossier chats section', () => {
  it('keeps the chat being read when the live chat grows a turn', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ turns: {} }) })))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const ui = (p: AgentProfile) => (
      <QueryClientProvider client={qc}><MemoryRouter>
        <AgentDossier p={p} range={[0, 864e5]} peak={5} initial="chats" onOpenLens={() => {}} onOpenTask={() => {}} />
      </MemoryRouter></QueryClientProvider>
    )
    const { rerender } = render(ui(profile(3)))
    fireEvent.click(screen.getByText('first session'))
    expect(screen.getByText('first session').closest('button')).toHaveAttribute('aria-pressed', 'true')
    // The freshness stamp moved: the same chats, the newest one a turn longer.
    rerender(ui(profile(4)))
    expect(screen.getByText('first session').closest('button')).toHaveAttribute('aria-pressed', 'true')
  })
})
