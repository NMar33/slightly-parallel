import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useTaskCoreField } from './cores'
import type { TaskRow } from '../model'

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })

function serve(taskCores: () => Promise<unknown>, posts: Array<{ url: string; body: { cores: string[] } }>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      posts.push({ url, body: JSON.parse(String(init.body)) })
      return json({ cores: [] })
    }
    if (url.startsWith('/api/cores?')) return json({ cores: [{ id: 'cr_a', name: 'A', type: 'feature', status: 'view' }, { id: 'cr_b', name: 'B', type: 'store', status: 'view' }] })
    if (url.endsWith('/cores')) return json(await taskCores())
    return json({})
  }))
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const task = { id: 'tk_1', project: 'alpha', title: 'x' } as TaskRow

afterEach(() => vi.unstubAllGlobals())

describe('useTaskCoreField', () => {
  it('keeps a pick made before the task\'s cores arrived', async () => {
    const posts: Array<{ url: string; body: { cores: string[] } }> = []
    let release: (v: unknown) => void = () => {}
    serve(() => new Promise((r) => { release = r }), posts)
    const { result } = renderHook(() => useTaskCoreField('alpha', task), { wrapper })
    act(() => result.current.setCores(['cr_b']))
    await act(async () => { release({ task_id: 'tk_1', cores: [{ id: 'cr_a' }] }) })
    await waitFor(() => expect(result.current.coreOptions).toHaveLength(2))
    expect(result.current.cores).toEqual(['cr_b'])
    await act(async () => { await result.current.syncCores(['tk_1']) })
    expect(posts).toEqual([{ url: '/api/tasks/tk_1/cores', body: { cores: ['cr_b'], actor: 'operator' } }])
  })

  it('gives steps made behind an unchanged task its cores, and leaves the task alone', async () => {
    const posts: Array<{ url: string; body: { cores: string[] } }> = []
    serve(async () => ({ task_id: 'tk_1', cores: [{ id: 'cr_a' }] }), posts)
    const { result } = renderHook(() => useTaskCoreField('alpha', task), { wrapper })
    await waitFor(() => expect(result.current.cores).toEqual(['cr_a']))
    await act(async () => { await result.current.syncCores(['tk_1', 'tk_2', 'tk_3']) })
    expect(posts.map((p) => p.url)).toEqual(['/api/tasks/tk_2/cores', '/api/tasks/tk_3/cores'])
    expect(posts.every((p) => p.body.cores.join() === 'cr_a')).toBe(true)
  })

  it('writes a new task\'s cores only when one is picked', async () => {
    const posts: Array<{ url: string; body: { cores: string[] } }> = []
    serve(async () => ({ cores: [] }), posts)
    const { result } = renderHook(() => useTaskCoreField('alpha', null, ['cr_a']), { wrapper })
    await act(async () => { await result.current.syncCores(['tk_9']) })
    expect(posts).toEqual([{ url: '/api/tasks/tk_9/cores', body: { cores: ['cr_a'], actor: 'operator' } }])
    const empty = renderHook(() => useTaskCoreField('alpha', null), { wrapper })
    await act(async () => { await empty.result.current.syncCores(['tk_10']) })
    expect(posts).toHaveLength(1)
  })
})
