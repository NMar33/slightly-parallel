/**
 * The one poll: /api/health on an interval, and the active queries are
 * asked again only when the server's data stamp moved.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { areasOf, useFreshness } from './settings'

function client() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  })
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => { vi.restoreAllMocks() })

describe('useFreshness', () => {
  it('asks the active queries again once the stamp moves, and not before', async () => {
    let stamp = 100
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/health') return json({ ok: true, fs_mtime: stamp })
      return json({ groups: [], environment: [], file: '' })
    }))
    const qc = client()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
    const { result } = renderHook(() => useFreshness(1_000), { wrapper })
    void result
    await waitFor(() => expect(qc.getQueryData(['freshness'])).toEqual({ ok: true, fs_mtime: 100 }))
    expect(invalidate).not.toHaveBeenCalled()

    // The same stamp again is nothing.
    await qc.refetchQueries({ queryKey: ['freshness'] })
    expect(invalidate).not.toHaveBeenCalled()

    // A moved stamp is everything, except the poll itself.
    stamp = 101
    await qc.refetchQueries({ queryKey: ['freshness'] })
    await waitFor(() => expect(invalidate).toHaveBeenCalledTimes(1))
    const arg = invalidate.mock.calls[0]![0] as { predicate: (q: { queryKey: readonly unknown[] }) => boolean }
    expect(arg.predicate({ queryKey: ['freshness'] })).toBe(false)
    expect(arg.predicate({ queryKey: ['lens', 'scans'] })).toBe(true)
  })

  it('with the areas, only the pages that read a moved area are asked again', async () => {
    let stamps: Record<string, number> = { chats: 1, tasks: 1, scans: 1, rest: 1 }
    let stamp = 10
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/health') return json({ ok: true, fs_mtime: stamp, stamps })
      return json({ groups: [], environment: [], file: '' })
    }))
    const qc = client()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
    renderHook(() => useFreshness(1_000), { wrapper })
    await waitFor(() => expect(qc.getQueryData(['freshness'])).toBeTruthy())
    stamps = { ...stamps, tasks: 2 }
    stamp = 11
    await qc.refetchQueries({ queryKey: ['freshness'] })
    await waitFor(() => expect(invalidate).toHaveBeenCalledTimes(1))
    const arg = invalidate.mock.calls[0]![0] as { predicate: (q: { queryKey: readonly unknown[] }) => boolean }
    expect(arg.predicate({ queryKey: ['scans-page', 'all'] })).toBe(false)
    expect(arg.predicate({ queryKey: ['session-turns', 'a,b'] })).toBe(false)
    expect(arg.predicate({ queryKey: ['lens', 'tasks', {}] })).toBe(true)
    expect(arg.predicate({ queryKey: ['project', 'slightly-parallel'] })).toBe(true)
  })

  it('a key this list does not know reloads on every change', () => {
    expect(areasOf(['project', 'slightly-parallel'])).toBeNull()
    expect(areasOf(['lens', 'tasks', {}])).toEqual(['tasks', 'chats'])
  })
})
