/**
 * The agent's page — the dossier on a rail, fed by the profile API.
 *
 *   1. renders the identity and the eight rail sections
 *   2. a rail click switches the section and writes it into the hash
 *   3. ← → walk the project's roster, most recently active first
 *   4. error state when the profile cannot load
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { AgentPage } from './AgentPage'

const totals = {
  sessions_n: 2, minutes: 95, turns: 12, days_active: 2, scans_n: 1, files_n: 3, lines_add: 120, lines_del: 8,
  file_entries_n: 1, decisions_n: 1, architecture_n: 0, features_n: 0, problems_n: 0, bugs_resolved_n: 0,
  rules_n: 0, standups_n: 0, tasks_n: 1, tasks_handed_n: 1, tasks_done_n: 0, links_n: 0,
}

function profile(id: string, name: string, last: string) {
  return {
    agent: { agent_id: id, agent_name: name, project: 'WT', created_date: '2608-20', last_active: last, message_count: 12, files_touched: [] },
    origin: { tool: 'claude-code', cwd: '/w', session_ref: 'abc', capture: '', chat_path: '' },
    totals,
    by_day: [{ date: '2608-20', turns: 6, minutes: 40, sessions: 1 }, { date: '2608-21', turns: 6, minutes: 55, sessions: 1 }],
    by_hour: new Array(24).fill(0),
    architecture_kinds: {},
    sessions: [{ id: 'ses_1', created_date: '2608-20', start_time: '10:00', end_time: '10:40', duration_min: 40, turns_n: 6, l1: 'первая сессия' }],
    scans: [], files: [], decisions: [{ id: 'dc_1', created_date: '2608-21', created_time: '11:00', decision_text: 'Adopt jade', source: 'explicit' }],
    architecture: [], problems: [], rules: [],
    tasks: [{ id: 'tk_1', title: 'Wire it', status: 'doing', first_at: '2026-08-20T10:00:00', last_at: '2026-08-21T10:00:00', handed_n: 1, replied_n: 0, turn_max: 1 }],
    links: [], parent: null, children: [], group: { name: '', members: [] },
  }
}

const A1 = profile('a1', 'писатель', '2026-08-21T10:00:00')
const A2 = profile('a2', 'reviewer', '2026-08-20T10:00:00')

function stub(fail = false) {
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
    const path = String(url)
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
    if (path.includes('/api/agents/profiles')) return json({ total: 2, profiles: [A1, A2] })
    if (path.includes('/api/agents/a1/profile')) return fail ? json({ detail: 'boom' }, 500) : json(A1)
    if (path.includes('/api/agents/a2/profile')) return json(A2)
    if (path.includes('/api/sessions/')) return json({ metadata: {}, l2: '', l3: [], l4: '', turns: [] })
    if (path.includes('/api/settings')) return json({ groups: [], environment: [], file: '' })
    return json({})
  }))
}

function renderPage(id = 'a1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/agent/${id}`]}>
        <Routes>
          <Route path="/agent/:id" element={<AgentPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AgentPage — the dossier', () => {
  beforeEach(() => { window.history.replaceState(null, '', '/'); stub() })
  afterEach(() => { vi.unstubAllGlobals(); window.location.hash = '' })

  it('renders the identity and the eight rail sections', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('писатель')).toBeTruthy())
    const rail = screen.getByRole('tablist', { name: /sections/i })
    const labels = within(rail).getAllByRole('tab').map((t) => t.textContent?.replace(/\d+/g, '').trim())
    expect(labels).toEqual(['overview', 'chats', 'files', 'decisions', 'tasks', 'features & fixes', 'links and subagents'])
  })

  it('a rail click switches the section and lands in the hash', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('писатель')).toBeTruthy())
    fireEvent.click(screen.getByRole('tab', { name: /decisions/ }))
    expect(screen.getByRole('tab', { name: /decisions/ }).getAttribute('aria-selected')).toBe('true')
    expect(window.location.hash).toBe('#sec=decisions')
    expect(screen.getByText('Adopt jade')).toBeTruthy()
  })

  it('walks the roster, most recently active first', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('писатель')).toBeTruthy())
    // the roster loads after the profile — a1 is the most recent → a2 is next
    await waitFor(() => expect(screen.getByText('1 of 2')).toBeTruthy())
    const next = screen.getByRole('link', { name: 'Next agent' })
    expect(next.getAttribute('href')).toBe('/agent/a2')
  })

  it('shows the error banner when the profile cannot load', async () => {
    vi.unstubAllGlobals(); stub(true)
    renderPage()
    await waitFor(() => expect(screen.getByText(/Could not load agent "a1"/)).toBeTruthy())
  })
})
