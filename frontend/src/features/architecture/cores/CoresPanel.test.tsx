import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CoresPanel } from './CoresPanel'
import type { CoreDetail, CoreSummary, GridDay } from './data'

vi.mock('../../../lib/useAgentNames', () => ({ useAgentNames: () => (id: string) => id }))

const grid: GridDay[] = Array.from({ length: 30 }, (_, i) => ({ day: `2026-10-${String(i + 1).padStart(2, '0')}`, story: i === 29 ? 2 : 0, nearby: i === 28 ? 1 : 0 }))

const base = {
  project: 'alpha', reason: '', status: 'view', position: '1', tracking_on: '', tracking_until: '',
  created_at: '2026-10-24T10:00:00', updated_at: '2026-10-25T10:00:00', actor: 'operator', off_at: '',
  tracking: { on: false, until: '', days_left: null, expired: false }, grid,
}
const CORES: CoreSummary[] = [
  { ...base, id: 'cr_1', name: 'Chat capture', type: 'capability', reason: 'the core of the product', notes_n: 2, pending_n: 1,
    last_note: { at: '2026-10-25T09:00:00', text: '', comment: 'stdin now', author: 'cc-x', kind: 'auto', approved: false },
    tasks_n: 2, open_n: 1, anchors: ['scripts/hooks/capture.py'],
    tracking: { on: true, until: '2026-10-31', days_left: 6, expired: false } },
  { ...base, id: 'cr_2', name: '### suppressor', type: 'feature', notes_n: 1, pending_n: 0, last_note: null, tasks_n: 0, open_n: 0, anchors: [] },
  { ...base, id: 'cr_3', name: 'Layers refactor', type: 'internals', status: 'off', off_at: '2026-10-24T18:00:00', notes_n: 0, pending_n: 0, last_note: null, tasks_n: 0, open_n: 0, anchors: [] },
]
const DETAIL: CoreDetail = {
  ...base, id: 'cr_1', name: 'Chat capture', type: 'capability', reason: 'the core of the product',
  tracking: { on: true, until: '2026-10-31', days_left: 6, expired: false },
  notes: [
    { id: 'cn_0', core_id: 'cr_1', at: '2026-10-24T10:00:00', author: 'operator', kind: 'founding', text: '#core-new chat capture', comment: 'named from this chat',
      task_id: '', session_id: '', turn: '', approved_at: '2026-10-24T10:00:00', approved_by: 'operator', approved: true },
    { id: 'cn_1', core_id: 'cr_1', at: '2026-10-25T09:00:00', author: 'cc-x', kind: 'auto', text: '', comment: 'stdin now',
      task_id: 'tk_1', session_id: '', turn: '', approved_at: '', approved_by: '', approved: false },
  ],
  links: [{ id: 'cl_1', core_id: 'cr_1', kind: 'anchor', target: 'scripts/hooks/capture.py', note: '', at: '', actor: 'operator' }],
  tasks: [{ id: 'tk_1', title: 'OpenCode on stdin', status: 'done', archived_at: '', created_date: '2610-25' }],
  files: [{ path: 'scripts/hooks/capture.py', lines_add: 12, lines_del: 3 }],
  commits_n: 3,
  nearby: [{ sha: 'abc1234', at: '2026-10-25T08:00:00', subject: 'tidy', files: ['scripts/hooks/capture.py'] }],
  commits: [], agents: [],
  events: [],
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

afterEach(() => { vi.unstubAllGlobals(); window.location.hash = '' })

function serve(posts: Array<{ path: string; body: unknown }>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url)
    if (init?.method === 'POST') {
      posts.push({ path, body: JSON.parse(String(init.body)) })
      return new Response(JSON.stringify({ note: {}, core: {} }), { status: 200, headers: { 'content-type': 'application/json' } })
    }
    const body = path.startsWith('/api/cores/cr_1') ? DETAIL : { cores: CORES, types: [] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
  }))
}

describe('CoresPanel', () => {
  it('shows the cores in view as tiles, the ones out of view below, and opens a core', async () => {
    const posts: Array<{ path: string; body: unknown }> = []
    serve(posts)
    render(wrap(<CoresPanel projectCode="alpha" />))
    await waitFor(() => expect(screen.getByText('Chat capture')).toBeInTheDocument())
    expect(screen.getByText('### suppressor')).toBeInTheDocument()
    expect(screen.getByText('2 cores in view')).toBeInTheDocument()
    expect(screen.getByText(/1 note awaiting approval/)).toBeInTheDocument()
    // Out of view, under the tiles, not among them.
    expect(screen.getByText('Layers refactor')).toBeInTheDocument()
    expect(screen.getByText(/removed 2026-10-24/)).toBeInTheDocument()
    // The "operator" view hides an agent's unapproved note on the tile.
    expect(screen.getByText('stdin now')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'operator' }))
    expect(screen.queryByText('stdin now')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Chat capture'))
    // The core opens as its graph: the notes and the tasks are nodes.
    await waitFor(() => expect(screen.getByText('tracking on')).toBeInTheDocument())
    expect(window.location.hash).toContain('core=cr_1')
    expect(screen.getByText(/6 days left/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /chat capture/ }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /OpenCode on stdin/ }).length).toBeGreaterThan(0)

    // Approving an agent's note from its node posts to its approve route, as the operator.
    fireEvent.click(screen.getByRole('button', { name: /^Agent note, .*stdin now/ }))
    fireEvent.click(within(screen.getByRole('complementary', { name: 'Details' })).getByRole('button', { name: /approve/ }))
    await waitFor(() => expect(posts.some((p) => p.path === '/api/cores/cr_1/notes/cn_1/approve')).toBe(true))
    expect((posts.find((p) => p.path.endsWith('/approve'))!.body as { actor: string }).actor).toBe('operator')

    // Switching tracking off posts {on: false}; on asks for a span first.
    fireEvent.click(screen.getByRole('switch', { name: 'Tracking' }))
    await waitFor(() => expect(posts.some((p) => p.path === '/api/cores/cr_1/tracking')).toBe(true))
    expect(posts.find((p) => p.path.endsWith('/tracking'))!.body).toEqual({ actor: 'operator', on: false })
  })

  it('makes a new core from the dialog and opens it', async () => {
    const posts: Array<{ path: string; body: unknown }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url)
      if (init?.method === 'POST') {
        posts.push({ path, body: JSON.parse(String(init.body)) })
        return new Response(JSON.stringify({ core: { ...base, id: 'cr_9', name: 'Kanban', type: 'interface' }, existing: false }), { status: 201, headers: { 'content-type': 'application/json' } })
      }
      const body = path.startsWith('/api/cores/cr_9') ? { ...DETAIL, id: 'cr_9', name: 'Kanban', type: 'interface', notes: [], links: [], tasks: [], files: [], nearby: [] } : { cores: [], types: [] }
      return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
    }))
    render(wrap(<CoresPanel projectCode="alpha" />))
    await waitFor(() => expect(screen.getByText('No cores yet.')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'New core' }))
    fireEvent.change(screen.getByPlaceholderText('Core name'), { target: { value: 'Kanban' } })
    fireEvent.click(screen.getByRole('button', { name: /interface/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Keep in view' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.path).toBe('/api/cores')
    expect(posts[0]!.body).toMatchObject({ project: 'alpha', name: 'Kanban', type: 'interface', actor: 'operator' })
    await waitFor(() => expect(window.location.hash).toContain('core=cr_9'))
  })
})
