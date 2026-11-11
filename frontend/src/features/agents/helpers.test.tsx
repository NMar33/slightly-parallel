import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '@testing-library/jest-dom/vitest'

import AgentsIndexPage from '../../pages/AgentsIndexPage'
import { AgentDossier } from './dossier'
import { HelperRows } from './parts'
import type { AgentProfile, HelperRow, ProfileTotals } from './profile'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const totals: ProfileTotals = {
  sessions_n: 1, minutes: 30, turns: 5, days_active: 1, scans_n: 0, files_n: 0, lines_add: 0, lines_del: 0,
  file_entries_n: 0, decisions_n: 0, architecture_n: 0, features_n: 0, problems_n: 0, bugs_resolved_n: 0,
  rules_n: 0, standups_n: 0, tasks_n: 0, tasks_handed_n: 0, tasks_done_n: 0, links_n: 0,
}

const helper = (id: string, first: string, more: Partial<HelperRow> = {}): HelperRow => ({
  agent_id: id, project: 'p', tool: 'codex', helper_kind: 'codex-exec', helper_of: 'cc-x', started: '2026-11-01T10:05:00',
  first_line: first, message_count: 1, tokens: 12_400, cost_usd: 0.42, ...more,
})

const profile = (more: Partial<AgentProfile> = {}): AgentProfile => ({
  agent: { agent_id: 'cc-x', agent_name: 'writer', project: 'p', created_date: '2608-20', last_active: '2026-08-21T10:00:00', message_count: 5, files_touched: [] },
  origin: { tool: 'claude-code', cwd: '/work/p', session_ref: 'abc', capture: 'hooks', chat_path: '' },
  totals, by_day: [], by_hour: new Array(24).fill(0), architecture_kinds: {},
  sessions: [], scans: [], files: [], decisions: [], architecture: [], problems: [], rules: [],
  tasks: [], links: [], parent: null, children: [], group: { name: '', members: [] },
  ...more,
})

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('helper chats', () => {
  it('a row says when, how it was started, its first line and what it used, and opens its chat', () => {
    wrap(<HelperRows rows={[helper('codex-00000001', 'You are a critic.'), helper('cc-bbbb2222', 'draft', { tool: 'claude-code', helper_kind: 'claude-print', tokens: 0, cost_usd: null })]} />)
    const links = screen.getAllByRole('link')
    expect(links[0]).toHaveAttribute('href', '/agent/codex-00000001#sec=chats')
    expect(links[0]).toHaveTextContent('codex exec')
    expect(links[0]).toHaveTextContent('You are a critic.')
    expect(links[0]).toHaveTextContent('1 msgs · 12k · $0.42')
    expect(links[0]).toHaveTextContent('10:05')
    // No tokens recorded: no number made up.
    expect(links[1]).toHaveTextContent('claude -p')
    expect(links[1].textContent).not.toMatch(/\$|·\s*0\b/)
  })

  it('the agent page has a helpers section only when the agent started some', () => {
    const { unmount } = wrap(<AgentDossier p={profile()} range={[0, 864e5]} peak={5} onOpenLens={() => {}} onOpenTask={() => {}} />)
    expect(screen.queryByRole('tab', { name: /helpers/ })).toBeNull()
    unmount()
    wrap(<AgentDossier p={profile({ helpers: [helper('codex-00000001', 'You are a critic.')] })} range={[0, 864e5]} peak={5} onOpenLens={() => {}} onOpenTask={() => {}} />)
    const tab = screen.getByRole('tab', { name: /helpers/ })
    expect(tab).toHaveTextContent('helpers1')
    fireEvent.click(tab)
    expect(screen.getByRole('link', { name: /You are a critic/ })).toHaveAttribute('href', '/agent/codex-00000001#sec=chats')
  })

  it('a section the agent does not have shows the overview', () => {
    wrap(<AgentDossier p={profile()} section="helpers" range={[0, 864e5]} peak={5} onOpenLens={() => {}} onOpenTask={() => {}} />)
    expect(screen.getByText('/work/p')).toBeInTheDocument()
  })

  it("a helper's own page names the chat that started it", () => {
    const own = profile({ agent: { ...profile().agent, agent_id: 'codex-00000001', helper: true, helper_kind: 'codex-exec', helper_of: 'cc-x' } })
    wrap(<AgentDossier p={own} section="links" range={[0, 864e5]} peak={5} onOpenLens={() => {}} onOpenTask={() => {}} />)
    const line = screen.getByText(/helper run \(codex exec\), started by/)
    expect(within(line).getByRole('link')).toHaveAttribute('href', '/agent/cc-x')
  })

  it('the board folds the helpers with no known parent at the end of their project', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const body = url.startsWith('/api/snapshot')
        ? { projects: [{ code: 'p', name: 'p' }], agents: [], kpi: {}, recent_activity: [], open_tasks: [], recent_decisions: [] }
        : url.startsWith('/api/agents/profiles')
          ? { profiles: [profile({ helpers: [helper('codex-00000001', 'parented')] })], orphans: [helper('codex-00000002', 'started by hand', { helper_of: '' })] }
          : {}
      return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => JSON.stringify(body) }
    }))
    wrap(<AgentsIndexPage />)
    const group = await screen.findByText('Helpers with no known parent · 1')
    const details = group.closest('details')!
    expect(details).not.toHaveAttribute('open')
    expect(within(details).getByRole('link', { name: /started by hand/ })).toHaveAttribute('href', '/agent/codex-00000002#sec=chats')
    // A helper with a parent is not on the board: it is on its parent's page.
    expect(screen.queryByText('parented')).toBeNull()
  })
})
