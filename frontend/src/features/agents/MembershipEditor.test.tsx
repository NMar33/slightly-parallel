import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'

import { MembershipEditor } from './MembershipEditor'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const AGENT = 'cc-aaaa1111'
const BASE = { agent_id: AGENT, home: 'alpha', members: ['alpha', 'beta'], level: 2,
  summary: `agent ${AGENT}\nhome: alpha · member of: alpha, beta · runs from folder: alpha\ntask level: 2 (picks by context)` }

/** The server: GET membership and the snapshot; POST answers what `post` says. */
function server(post: (body: Record<string, unknown>) => { status: number; body: unknown }) {
  const posted: Array<Record<string, unknown>> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const json = (status: number, body: unknown) =>
      new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      posted.push(body)
      const got = post(body)
      return json(got.status, got.body)
    }
    if (String(url).includes('/membership')) return json(200, BASE)
    return json(200, { projects: [{ code: 'alpha' }, { code: 'beta' }, { code: 'gamma' }], agents: [] })
  })
  vi.stubGlobal('fetch', fetchMock)
  return posted
}

function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MembershipEditor agentId={AGENT} /></QueryClientProvider>)
}

describe('the agent card: its projects', () => {
  it('shows each project as a chip, the home marked and without a leave', async () => {
    server(() => ({ status: 200, body: BASE }))
    wrap()
    const chips = await screen.findByRole('list', { name: 'Member projects' })
    const items = within(chips).getAllByRole('listitem')
    expect(items.map((i) => i.textContent)).toEqual(['alpha· home', 'betaleave'])
    expect(screen.queryByRole('button', { name: 'Leave alpha' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Leave beta' })).toBeInTheDocument()
  })

  it('joins a project picked from the ones it is not in, and shows the summary it answers', async () => {
    const posted = server(() => ({ status: 200, body: { ...BASE, members: ['alpha', 'beta', 'gamma'],
      summary: BASE.summary.replace('alpha, beta', 'alpha, beta, gamma') } }))
    wrap()
    const pick = await screen.findByRole('combobox', { name: 'Join a project' })
    await waitFor(() => expect(within(pick).getAllByRole('option').map((o) => o.textContent)).toEqual(['join a project…', 'gamma']))
    fireEvent.change(pick, { target: { value: 'gamma' } })
    await waitFor(() => expect(posted).toEqual([{ op: 'join', project: 'gamma' }]))
    expect(await screen.findByRole('status')).toHaveTextContent('member of: alpha, beta, gamma')
  })

  it('shows the one-line refusal of a leave', async () => {
    const posted = server(() => ({ status: 409, body: { detail: `${AGENT} is not in beta` } }))
    wrap()
    fireEvent.click(await screen.findByRole('button', { name: 'Leave beta' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(`${AGENT} is not in beta`)
    expect(posted).toEqual([{ op: 'leave', project: 'beta' }])
  })

  it('sets the task level from its radio group', async () => {
    const posted = server(() => ({ status: 200, body: { ...BASE, level: 3 } }))
    wrap()
    const group = await screen.findByRole('radiogroup', { name: 'task level' })
    fireEvent.click(within(group).getByRole('radio', { name: /3/ }))
    await waitFor(() => expect(posted).toEqual([{ op: 'level', value: 3 }]))
  })
})
