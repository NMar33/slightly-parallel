import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { useBoardColumns } from './useBoardColumns'
import { laneKey, type TaskRow } from '../model'

afterEach(() => { localStorage.clear(); vi.unstubAllGlobals() })

const props = (boardKey: string) => ({
  boardKey, tasks: [] as TaskRow[], todayTasks: [] as TaskRow[], today: '2026-10-06', statusSince: {},
  sprintFilter: null, onlyRemembered: false, onlyToday: false,
})

describe('useBoardColumns', () => {
  it("reads the next board's view, sorts and columns when the board changes", () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })))
    localStorage.setItem('sp-kanban-view:beta', 'workflow')
    localStorage.setItem('sp-kanban-sort:beta', JSON.stringify({ todo: 'priority' }))
    localStorage.setItem('sp-kanban-cols:beta', JSON.stringify({ review: true }))
    const qc = new QueryClient()
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    const { result, rerender } = renderHook((p: ReturnType<typeof props>) => useBoardColumns(p), { initialProps: props('alpha'), wrapper })
    expect(result.current.view).toBe('classic')
    expect(result.current.sorts).toEqual({})
    rerender(props('beta'))
    expect(result.current.view).toBe('workflow')
    expect(result.current.sorts).toEqual({ todo: 'priority' })
    expect(result.current.hiddenCols).toEqual({ review: true })
    act(() => result.current.setSort('done', 'oldest'))
    expect(JSON.parse(localStorage.getItem('sp-kanban-sort:beta')!)).toEqual({ todo: 'priority', done: 'oldest' })
    expect(localStorage.getItem('sp-kanban-sort:alpha')).toBeNull()
  })
})

describe('a hidden fallback column', () => {
  it('leaves out the cards it would have held instead of crashing the board', () => {
    // Before: `map['unclassified']!.push` threw when Unclassified was unticked
    // and a card had a status no visible column shows (review in the classic view).
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })))
    localStorage.setItem('sp-kanban-cols:b', JSON.stringify({ unclassified: true }))
    const qc = new QueryClient()
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    const tasks = [{ id: 'tk_1', title: 'x', status: 'review', project: 'b' } as unknown as TaskRow]
    const { result } = renderHook(() => useBoardColumns({ ...props('b'), tasks }), { wrapper })
    expect(Object.values(result.current.tasksByStatus).flat()).toHaveLength(0)
  })
})


it('indexes the combined board cells and counts by project and folded lane name', () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })))
  const qc = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  const tasks: TaskRow[] = [
    { id: 'a', status: 'todo', project: 'alpha', assignee: 'Audio' },
    { id: 'b', status: 'todo', project: 'beta', assignee: 'audio', lane_kind: 'agent' },
    { id: 'c', status: 'todo', project: 'beta', assignee: 'AUDIO', lane_kind: 'agent' },
  ]
  const { result } = renderHook(() => useBoardColumns({ ...props('combined'), tasks }), { wrapper })
  const { cells, laneN } = result.current.byLaneCol
  expect(cells.get(`${laneKey('alpha', 'audio')}\ntodo`)?.map((task) => task.id)).toEqual(['a'])
  expect(cells.get(`${laneKey('beta', 'audio')}\ntodo`)?.map((task) => task.id)).toEqual(['b', 'c'])
  expect(laneN.get(laneKey('beta', 'audio'))).toBe(2)
})
