import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { AgentTree } from './AgentTree'
import type { SnapshotAgent } from '../../lib/api'

/**
 * One chat with folders in two projects (a session resumed elsewhere) is two
 * snapshot rows of one agent id. Each row carries its own folder's project
 * and the projects the agent joined (tk_d1d25a4d): every project's tree
 * shows the chat once, and React never sees two items with one key.
 */
const row = (project: string, projects: string): SnapshotAgent => ({
  agent_id: 'cc-twofold1', agent_name: 'two folders', project, projects, parent_agent_id: null,
  created_date: '2611-20', last_active: '2026-11-20T10:00:00', message_count: 2, l1_headline: '',
  files_touched: [], tags: [],
})

function draw(agents: SnapshotAgent[], project: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchInterval: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><AgentTree agents={agents} activity={[]} project={project} /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('a chat with two folders in the agent tree', () => {
  let errors: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })))
    errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => {
    errors.mockRestore()
    vi.unstubAllGlobals()
  })

  const chatLinks = () => document.querySelectorAll('a[href="/agent/cc-twofold1"]')
  const keyWarnings = () => errors.mock.calls.filter((c) => String(c[0]).includes('same key'))

  it('shows it once in each folder’s project, with no joins', () => {
    const agents = [row('alpha', 'alpha'), row('beta', 'beta')]
    for (const p of ['alpha', 'beta']) {
      const { unmount } = draw(agents, p)
      expect(chatLinks()).toHaveLength(1)
      unmount()
    }
    expect(keyWarnings()).toEqual([])
  })

  it('shows it once in a project it joined, with no duplicate key', () => {
    // The folders' metas can differ: one put in a group, the other not.
    draw([{ ...row('alpha', 'alpha,gamma'), agent_group: 'g1' }, row('beta', 'beta,gamma')], 'gamma')
    expect(chatLinks()).toHaveLength(1)
    expect(keyWarnings()).toEqual([])
  })
})
