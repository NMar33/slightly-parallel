import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import AgentsIndexPage from './AgentsIndexPage'
import type { AgentProfile, ProfileTotals } from '../features/agents/profile'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const totals: ProfileTotals = {
  sessions_n: 1, minutes: 30, turns: 5, days_active: 1, scans_n: 0, files_n: 0, lines_add: 0, lines_del: 0,
  file_entries_n: 0, decisions_n: 0, architecture_n: 0, features_n: 0, problems_n: 0, bugs_resolved_n: 0,
  rules_n: 0, standups_n: 0, tasks_n: 0, tasks_handed_n: 0, tasks_done_n: 0, links_n: 0,
}
const profile = (name: string): AgentProfile => ({
  agent: { agent_id: 'cc-x', agent_name: name, project: 'p', created_date: '2608-20', last_active: '2026-08-21T10:00:00', message_count: 5, files_touched: [] },
  origin: { tool: 'claude-code', cwd: '/work/p', session_ref: 'abc', capture: 'hooks', chat_path: '' },
  totals, by_day: [{ date: '2608-20', turns: 5, minutes: 30, sessions: 1 }], by_hour: new Array(24).fill(0), architecture_kinds: {},
  sessions: [], scans: [], files: [], decisions: [], architecture: [], problems: [], rules: [],
  tasks: [], links: [], parent: null, children: [], group: { name: '', members: [] },
})

describe('AgentsIndexPage', () => {
  it('shows a roster that changed but kept its length', async () => {
    let name = 'Alpha'
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const body = url.startsWith('/api/snapshot')
        ? { projects: [{ code: 'p', name: 'p' }], agents: [], kpi: {}, recent_activity: [], open_tasks: [], recent_decisions: [] }
        : url.startsWith('/api/agents/profiles') ? { profiles: [profile(name)] }
          : {}
      return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => JSON.stringify(body) }
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter><AgentsIndexPage /></MemoryRouter></QueryClientProvider>)
    expect((await screen.findAllByText('Alpha')).length).toBeGreaterThan(0)
    name = 'Beta'
    await act(async () => { await qc.invalidateQueries() })
    expect((await screen.findAllByText('Beta')).length).toBeGreaterThan(0)
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument()
  })
})
