import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'

import { putBack, useBoardData } from './boardData'
import type { TaskRow } from './model'

const row = (id: string, status: string) => ({ id, status, title: id }) as unknown as TaskRow

describe('putBack', () => {
  it('restores the named tasks and leaves what a refetch brought to the others', () => {
    const before = [row('a', 'todo'), row('b', 'todo')]
    // Since then: a moved optimistically, b was changed by an agent.
    const now = [row('a', 'doing'), row('b', 'done'), row('c', 'todo')]
    expect(putBack(before, new Set(['a']))(now).map((t) => `${t.id}:${t.status}`)).toEqual(['a:todo', 'b:done', 'c:todo'])
  })
})

describe('an optimistic edit against a refetch already on its way', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the edit: the late answer left before it and is dropped', async () => {
    // Each read of the task list is held until the test answers it.
    const held: Array<(tasks: TaskRow[]) => void> = []
    vi.stubGlobal('fetch', vi.fn((url: string, init?: { signal?: AbortSignal }) => {
      const answer = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })
      if (!String(url).startsWith('/api/tasks?')) return Promise.resolve(answer({}))
      return new Promise((resolve, reject) => {
        held.push((tasks) => resolve(answer({ tasks })))
        init?.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
      })
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: qc }, children)
    const { result } = renderHook(() => useBoardData('p', ['p'], false), { wrapper })

    await waitFor(() => expect(held.length).toBe(1))
    await act(async () => { held[0]!([row('a', 'todo')]) })
    await waitFor(() => expect(result.current.tasks.map((t) => t.status)).toEqual(['todo']))

    // An agent's write moves the stamp: the board is asked for again…
    act(() => { void qc.invalidateQueries({ queryKey: ['tasks', 'board'] }) })
    await waitFor(() => expect(held.length).toBe(2))
    // …and before that answer lands the operator drags the card.
    act(() => result.current.setTasks((cur) => cur.map((t) => ({ ...t, status: 'doing' }))))
    await act(async () => { held[1]!([row('a', 'todo')]); await new Promise((r) => setTimeout(r, 0)) })
    expect(result.current.tasks.map((t) => t.status)).toEqual(['doing'])
  })
})
