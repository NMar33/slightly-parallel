import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '@testing-library/jest-dom/vitest'

import { AgentDossier } from './dossier'
import type { AgentProfile, ProfileTotals } from './profile'

afterEach(cleanup)

const totals: ProfileTotals = {
  sessions_n: 2, minutes: 30, turns: 5, days_active: 1, scans_n: 1, files_n: 3, lines_add: 10, lines_del: 2,
  file_entries_n: 0, decisions_n: 1, architecture_n: 0, features_n: 0, problems_n: 0, bugs_resolved_n: 0,
  rules_n: 0, standups_n: 0, tasks_n: 1, tasks_handed_n: 1, tasks_done_n: 0, links_n: 0,
}
const profile: AgentProfile = {
  agent: { agent_id: 'cc-x', agent_name: 'писатель', project: 'p', created_date: '2608-20', last_active: '2026-08-21T10:00:00', message_count: 5, files_touched: [] },
  origin: { tool: 'claude-code', cwd: '/work/p', session_ref: 'abc', capture: 'hooks', chat_path: '' },
  totals, by_day: [{ date: '2608-20', turns: 5, minutes: 30, sessions: 2 }], by_hour: new Array(24).fill(0), architecture_kinds: {},
  sessions: [
    { id: 'ses_1', created_date: '2608-20', start_time: '09:00', end_time: '09:10', duration_min: 10, turns_n: 2, l1: 'first session' },
    { id: 'ses_2', created_date: '2608-20', start_time: '11:00', end_time: '11:20', duration_min: 20, turns_n: 3, l1: 'second session' },
  ],
  scans: [{ id: 'sn_1', created_date: '2608-20', created_time: '09:05', l1: 'a scan', files_n: 3, lines_add: 10, lines_del: 2, decisions_n: 0, scope: '' }],
  files: [], decisions: [{ id: 'dc_1', created_date: '2608-20', decision_text: 'Chose the ledger', rationale: 'append-only' }],
  architecture: [], problems: [], rules: [],
  tasks: [{ id: 'tk_1', title: 'Write it', status: 'doing', first_at: '', last_at: '', handed_n: 1, replied_n: 0, turn_max: 0 }],
  links: [], parent: null, children: [], group: { name: '', members: [] },
}

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('AgentDossier', () => {
  it('seven sections in the rail, with counts, one shown at a time', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ metadata: {}, l2: '', l3: [], l4: '', turns: [{ n: 1, at: '11:00', user: 'привет', agent: 'ответ' }] }) })))
    wrap(<AgentDossier p={profile} range={[0, 864e5]} peak={5} onOpenLens={() => {}} onOpenTask={() => {}} />)
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual([
      'overview', 'chats2', 'files1', 'decisions1', 'tasks1', 'features & fixes0', 'links and subagents0',
    ])
    expect(screen.getByText('/work/p')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /decisions/ }))
    expect(screen.getByText('Chose the ledger')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /chats/ }))
    // Newest session first, and selected.
    const sessions = screen.getAllByRole('button', { pressed: true })
    expect(sessions[0]).toHaveTextContent('second session')
    vi.unstubAllGlobals()
  })

  it('with hotkeys, a digit opens that section', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ metadata: {}, l2: '', l3: [], l4: '', turns: [] }) })))
    wrap(<AgentDossier p={profile} range={[0, 864e5]} peak={5} hotkeys onOpenLens={() => {}} onOpenTask={() => {}} />)
    expect(screen.queryByText('Chose the ledger')).toBeNull()
    fireEvent.keyDown(window, { key: '4' })
    expect(screen.getByRole('tab', { name: /decisions/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Chose the ledger')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})
