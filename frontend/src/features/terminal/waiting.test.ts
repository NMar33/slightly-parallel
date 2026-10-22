import { describe, expect, it } from 'vitest'

import type { TermSession } from '../../lib/terminal'
import { newlyWaiting, titleWith } from './waiting'

const s = (id: string, state: TermSession['state']) => ({ id, state, label: id }) as TermSession

describe('who has just turned to you', () => {
  it('is only a change: the first look raises nothing', () => {
    expect(newlyWaiting(null, [s('a', 'waiting')])).toEqual([])
  })
  it('is a terminal that was working and now waits', () => {
    const before = new Map([['a', 'working'], ['b', 'waiting'], ['c', 'shell']] as const)
    const now = [s('a', 'waiting'), s('b', 'waiting'), s('c', 'shell'), s('d', 'waiting')]
    // b was already waiting; d is new to the list — neither is news.
    expect(newlyWaiting(before, now).map((x) => x.id)).toEqual(['a'])
  })
})

describe('the title count', () => {
  it('goes in front, replaces itself, and leaves at zero', () => {
    expect(titleWith('Kanban — Slightly Parallel', 2)).toBe('(2) Kanban — Slightly Parallel')
    expect(titleWith('(2) Kanban — Slightly Parallel', 1)).toBe('(1) Kanban — Slightly Parallel')
    expect(titleWith('(1) Kanban — Slightly Parallel', 0)).toBe('Kanban — Slightly Parallel')
  })
})

// ---------------------------------------------------------------- the watcher

import { act, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'

import { WaitingNotice } from './waiting'

describe('the watcher', () => {
  it('counts in the title, and announces only a terminal that has just turned', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
    // Seeded status (off, so nothing polls) lets the list query read the seeded cache.
    qc.setQueryData(['terminal', 'state'], { enabled: false })
    const list = (a: TermSession['state'], b: TermSession['state']) => ({
      sessions: [s('agent-a', a), s('agent-b', b)], counts: {},
    })
    qc.setQueryData(['terminal', 'sessions'], list('working', 'waiting'))
    document.title = 'Kanban — Slightly Parallel'
    render(createElement(QueryClientProvider, { client: qc }, createElement(WaitingNotice)))
    await act(async () => {})
    // b was waiting on arrival: counted, not announced.
    expect(document.title).toBe('(1) Kanban — Slightly Parallel')
    expect(screen.queryByText(/is waiting for you/)).toBeNull()

    // react-query hands cache changes to its observers on a zero timer.
    await act(async () => { qc.setQueryData(['terminal', 'sessions'], list('waiting', 'waiting')); await new Promise((r) => setTimeout(r, 0)) })
    expect(document.title).toBe('(2) Kanban — Slightly Parallel')
    expect(screen.getByText('agent-a is waiting for you')).toBeInTheDocument()

    // A page writes its own title on arrival: the count comes back on it.
    await act(async () => { document.title = 'Chats — Slightly Parallel' })
    await new Promise((r) => setTimeout(r, 0))
    expect(document.title).toBe('(2) Chats — Slightly Parallel')
  })
})
