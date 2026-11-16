import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CoreDetail, CoreNote } from '../data'
import { GraphBody, buildGraph } from './GraphBody'

vi.mock('../../../../lib/useAgentNames', () => ({ useAgentNames: () => (id: string) => id }))

const note = (id: string, at: string, author: string, approved: boolean, extra: Partial<CoreNote> = {}): CoreNote => ({
  id, core_id: 'cr_1', at, author, approved, kind: 'note', text: '', comment: '', task_id: '', session_id: '', turn: '',
  approved_at: approved ? at : '', approved_by: approved ? 'operator' : '', ...extra,
})

const core: CoreDetail = {
  id: 'cr_1', project: 'alpha', name: 'Chat capture', type: 'capability', reason: 'the core of the product', status: 'view', position: '1',
  tracking_on: '1', tracking_until: '2026-10-31', created_at: '2026-10-18T11:20:00', updated_at: '', actor: 'operator', off_at: '',
  tracking: { on: true, until: '2026-10-31', days_left: 7, expired: false }, grid: [],
  notes: [
    note('n0', '2026-10-18T11:20:00', 'operator', true, { kind: 'founding', text: 'capture every chat' }),
    note('n1', '2026-10-24T21:40:00', 'cc-x', true, { kind: 'auto', comment: 'turns.jsonl under the lock', task_id: 'tk_aaaaaaaa' }),
    note('n2', '2026-10-25T09:12:00', 'cc-x', false, { kind: 'auto', comment: 'OpenCode on stdin' }),
    note('n3', '2026-10-25T10:00:00', 'operator', true, { text: 'tk_bbbbbbbb must keep long sessions' }),
  ],
  links: [],
  tasks: [
    { id: 'tk_aaaaaaaa', title: 'turns under the lock', status: 'done', archived_at: '', created_date: '2610-24' },
    { id: 'tk_bbbbbbbb', title: 'OpenCode on stdin', status: 'doing', archived_at: '', created_date: '2610-25' },
  ],
  files: [
    { path: 'backend/backend/turntimes.py', lines_add: 10, lines_del: 2, tasks: ['tk_aaaaaaaa'] },
    { path: 'scripts/hooks/capture.py', lines_add: 30, lines_del: 4, tasks: ['tk_bbbbbbbb'] },
  ],
  commits_n: 2, nearby: [],
  commits: [
    { sha: 'bbb2222000', at: '2026-10-25T09:00:00', subject: 'stdin for opencode', how: 'signed', agent: 'cx-y', tasks: ['tk_bbbbbbbb'], files: ['scripts/hooks/capture.py'] },
    { sha: 'aaa1111000', at: '2026-10-24T21:30:00', subject: 'lock turns.jsonl', how: 'chat', agent: 'cc-x', tasks: ['tk_aaaaaaaa'], files: ['backend/backend/turntimes.py'] },
  ],
  agents: [
    { agent_id: 'cc-x', tasks: ['tk_aaaaaaaa'], given: ['tk_aaaaaaaa'], commits: 1, notes: 2, turns: 6, sessions: 1, last_at: '2026-10-25T09:12:00' },
    { agent_id: 'cx-y', tasks: ['tk_bbbbbbbb'], given: ['tk_bbbbbbbb'], commits: 1, notes: 0, turns: 3, sessions: 1, last_at: '2026-10-25T09:00:00' },
  ],
  events: [],
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>
}

function serve() {
  const posts: Array<{ path: string; body: unknown }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') posts.push({ path: String(url), body: JSON.parse(String(init.body)) })
    return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
  }))
  return posts
}

afterEach(() => vi.unstubAllGlobals())

describe('buildGraph', () => {
  it('links a note to the task it names (by id or in its words), an agent to its notes and tasks, a task to its files', () => {
    const g = buildGraph(core, 'everyone')
    const near = (id: string) => [...(g.near.get(id) ?? [])].sort()
    expect(near('n:n1')).toEqual(['a:cc-x', 'core', 't:tk_aaaaaaaa'])
    expect(near('n:n3')).toEqual(['core', 't:tk_bbbbbbbb'])
    expect(near('t:tk_bbbbbbbb')).toEqual(['a:cx-y', 'core', 'f:scripts/hooks/capture.py', 'n:n3'])
    // The operator's notes are taller than the agents', and the notes start at the top.
    const node = (id: string) => g.nodes.find((n) => n.id === id)!
    expect(node('n:n3').height).toBeGreaterThan(node('n:n2').height)
    expect(node('n:n3').top).toBe(0)   // newest first
  })

  it('keeps 40+ nodes readable: the files past the top 12 are one node', () => {
    const many: CoreDetail = {
      ...core,
      files: Array.from({ length: 30 }, (_, i) => ({ path: `src/f${i}.ts`, lines_add: 100 - i, lines_del: 0, tasks: ['tk_aaaaaaaa'] })),
      notes: Array.from({ length: 20 }, (_, i) => note(`m${i}`, `2026-10-${String(i + 1).padStart(2, '0')}T10:00:00`, 'operator', true, { text: `note ${i}` })),
    }
    const g = buildGraph(many, 'everyone')
    expect(g.nodes.filter((n) => n.kind === 'file')).toHaveLength(12)
    expect(g.restFiles).toHaveLength(18)
    expect(g.nodes.filter((n) => n.kind === 'note')).toHaveLength(14)
    expect(g.hiddenNotes).toHaveLength(6)
    // No two nodes of one column overlap.
    for (const col of [1, 4]) {
      const ns = g.nodes.filter((n) => n.col === col).sort((a, b) => a.top - b.top)
      for (let i = 1; i < ns.length; i++) expect(ns[i]!.top).toBeGreaterThanOrEqual(ns[i - 1]!.top + ns[i - 1]!.height)
    }
  })
})

describe('GraphBody', () => {
  it('lights the neighbours of a pointed node and fades the rest', () => {
    serve()
    render(wrap(<GraphBody projectCode="alpha" core={core} show="everyone" onOpenTask={vi.fn()} onNewTask={vi.fn()} />))
    const task = screen.getByRole('button', { name: /^Task OpenCode on stdin/ })
    fireEvent.mouseEnter(task)
    const box = (name: RegExp) => screen.getByRole('button', { name }).parentElement!
    expect(box(/^Your note, 2026-10-25 10:00: tk_bbbbbbbb/).style.opacity).toBe('1')
    expect(box(/^File scripts\/hooks\/capture\.py/).style.opacity).toBe('1')
    expect(box(/^Task turns under the lock/).style.opacity).toBe('0.3')
    expect(document.querySelector('[data-edge="t:tk_bbbbbbbb|a:cx-y"]')!.getAttribute('data-on')).toBe('1')
    expect(document.querySelector('[data-edge="t:tk_aaaaaaaa|a:cc-x"]')!.getAttribute('data-on')).toBe('0')
    fireEvent.mouseLeave(task)
    expect(box(/^Task turns under the lock/).style.opacity).toBe('1')
  })

  it('opens a task from its panel, approves an agent note, and adds a note on the picked task', async () => {
    const posts = serve()
    const open = vi.fn()
    render(wrap(<GraphBody projectCode="alpha" core={core} show="everyone" onOpenTask={open} onNewTask={vi.fn()} />))
    const panel = screen.getByRole('complementary', { name: 'Details' })

    fireEvent.click(screen.getByRole('button', { name: /^Task OpenCode on stdin/ }))
    expect(within(panel).getByText('stdin for opencode')).toBeInTheDocument()
    fireEvent.click(within(panel).getByRole('button', { name: 'Open task' }))
    expect(open).toHaveBeenCalledWith('tk_bbbbbbbb')
    fireEvent.change(within(panel).getByLabelText('Note on this task'), { target: { value: 'keep it short' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Add note' }))
    await waitFor(() => expect(posts.find((p) => p.path === '/api/cores/cr_1/notes')?.body).toMatchObject({ text: 'keep it short', task_id: 'tk_bbbbbbbb' }))

    fireEvent.click(screen.getByRole('button', { name: /^Agent note, 2026-10-25 09:12: OpenCode on stdin/ }))
    fireEvent.click(within(panel).getByRole('button', { name: /approve/ }))
    await waitFor(() => expect(posts.some((p) => p.path === '/api/cores/cr_1/notes/n2/approve')).toBe(true))
  })

  it('shows only the approved notes for "operator"', () => {
    serve()
    render(wrap(<GraphBody projectCode="alpha" core={core} show="operator" onOpenTask={vi.fn()} onNewTask={vi.fn()} />))
    expect(screen.queryByRole('button', { name: /OpenCode on stdin$/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /turns\.jsonl under the lock/ })).toBeInTheDocument()
  })

  it('leaves the commits found only by the chat out until asked, then draws them dashed', () => {
    serve()
    const { container } = render(wrap(<GraphBody projectCode="alpha" core={core} show="everyone" onOpenTask={vi.fn()} onNewTask={vi.fn()} />))
    // The chat-only commit touched turntimes.py: its file is not drawn, its line not either.
    expect(screen.queryByRole('button', { name: /File backend\/backend\/turntimes\.py/ })).not.toBeInTheDocument()
    expect(container.querySelector('[data-edge="t:tk_aaaaaaaa|f:backend/backend/turntimes.py"]')).toBeNull()
    // The operator gave cc-x the task in a chat: that line stands without any commit, solid.
    expect(container.querySelector('[data-edge="t:tk_aaaaaaaa|a:cc-x"]')?.getAttribute('stroke-dasharray')).toBeNull()
    fireEvent.click(screen.getByRole('checkbox', { name: /found by the chat only/ }))
    expect(screen.getByRole('button', { name: /File backend\/backend\/turntimes\.py/ })).toBeInTheDocument()
    expect(container.querySelector('[data-edge="t:tk_aaaaaaaa|f:backend/backend/turntimes.py"]')?.getAttribute('stroke-dasharray')).toBe('4 3')
    // A signed commit's line stays solid.
    expect(container.querySelector('[data-edge="t:tk_bbbbbbbb|a:cx-y"]')?.getAttribute('stroke-dasharray')).toBeNull()
  })
})
