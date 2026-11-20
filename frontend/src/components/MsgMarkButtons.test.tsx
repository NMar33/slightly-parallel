import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { MsgMarkButtons } from './MsgMarkButtons'
import PinsPage from '../pages/PinsPage'
import type { MsgMark } from '../lib/pins'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

const mark = (over: Partial<MsgMark>): MsgMark => ({
  id: 'mk_1', kind: 'pin', target: 'cc-a#3', project: 'alpha', agent_id: 'cc-a', session_id: 'ses_1', turn: 3,
  side: '', excerpt: 'the login timeout', marked_at: '2026-11-16T10:00:00', source: 'tag', at: '2026-11-16T10:00:00',
  text: 'the login timeout', chars: 17, ...over,
})

/** A server holding these lists; every POST is recorded. */
function serve(lists: { pin?: MsgMark[]; carry?: MsgMark[]; fork?: MsgMark[] }) {
  const posts: Array<{ path: string; body: Record<string, unknown> }> = []
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') posts.push({ path, body: JSON.parse(String(init.body)) })
    const which = path.startsWith('/api/carries') ? 'carry' : path.startsWith('/api/forks') ? 'fork' : 'pin'
    return { ok: true, status: 200, json: async () => ({ items: lists[which] ?? [], deliveries: [] }) }
  }))
  return posts
}

const mount = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter>{ui}</MemoryRouter>
  </QueryClientProvider>,
)

describe('the marks on a message', () => {
  it('pins the reply by its own name, as the operator', async () => {
    const posts = serve({})
    mount(<MsgMarkButtons msg={{ agent_id: 'cc-a', turn: 3, side: 'reply', project: 'alpha' }} />)
    await act(async () => { screen.getByRole('button', { name: /^Pin this reply/ }).click() })
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toEqual({ path: '/api/pins', body: expect.objectContaining({ chat_agent: 'cc-a', turn: 3, side: 'reply', actor: 'operator' }) })
    expect(posts[0]!.body).not.toHaveProperty('agent_id')
  })

  it('the light goes whole, then brief, then off', async () => {
    const posts = serve({ carry: [mark({ kind: 'carry' })] })
    mount(<MsgMarkButtons msg={{ agent_id: 'cc-a', turn: 3, side: '' }} />)
    const light = await screen.findByRole('button', { name: /Carried whole/ })
    expect(light.dataset.carry).toBe('carry')
    await act(async () => { light.click() })
    await waitFor(() => expect(posts.at(-1)).toEqual({ path: '/api/carries', body: expect.objectContaining({ level: 'brief' }) }))
  })

  it('the light that is a brief takes the mark off', async () => {
    const posts = serve({ carry: [mark({ kind: 'carry-brief' })] })
    mount(<MsgMarkButtons msg={{ agent_id: 'cc-a', turn: 3, side: '' }} />)
    const light = await screen.findByRole('button', { name: /Carried as a brief/ })
    await act(async () => { light.click() })
    await waitFor(() => expect(posts.at(-1)).toEqual({ path: '/api/carries/remove', body: expect.objectContaining({ target: 'cc-a#3' }) }))
  })
})

describe('the Pins page', () => {
  it('lists the pins, finds in them, and takes one off', async () => {
    const posts = serve({ pin: [mark({}), mark({ id: 'mk_2', target: 'cc-a#5', turn: 5, excerpt: 'the colours', text: 'the colours' })] })
    mount(<PinsPage />)
    expect(await screen.findByText('the login timeout')).toBeTruthy()
    expect(screen.getByText('the colours')).toBeTruthy()
    await act(async () => { screen.getAllByRole('button', { name: 'Take the mark off' })[0]!.click() })
    await waitFor(() => expect(posts.at(-1)).toEqual({ path: '/api/pins/remove', body: expect.objectContaining({ target: 'cc-a#3' }) }))
  })

  it('a fork shows the command to copy and its state', async () => {
    window.location.hash = '#list=fork'
    serve({ fork: [mark({ kind: 'fork', command: "cd /w && claude -r abc --fork-session $'go'", state: 'started' })] })
    mount(<PinsPage />)
    expect(await screen.findByText("cd /w && claude -r abc --fork-session $'go'")).toBeTruthy()
    expect(screen.getByRole('radio', { name: 'started' }).getAttribute('aria-checked')).toBe('true')
    window.location.hash = ''
  })
})
