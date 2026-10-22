import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { useSetWrites, type KeptSet } from './data'

afterEach(() => vi.unstubAllGlobals())

const set: KeptSet = { id: 'st_1', name: 'One', kind: 'vision', items: ['a', 'b'], created_at: '', updated_at: '' }

describe('set writes', () => {
  it('a refused reorder puts the set back at once', async () => {
    // The write is refused; the read that follows never answers, so only the rollback can restore it.
    vi.stubGlobal('fetch', vi.fn((url: string) => url.includes('/update')
      ? Promise.resolve({ ok: false, status: 422, json: async () => ({ detail: 'no' }) })
      : new Promise(() => {})))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    qc.setQueryData(['sets', 'vision'], [set])
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSetWrites('vision'), { wrapper })
    await act(async () => { await result.current.update.mutateAsync({ id: 'st_1', items: ['b', 'a'] }).catch(() => {}) })
    expect(qc.getQueryData<KeptSet[]>(['sets', 'vision'])?.[0]?.items).toEqual(['a', 'b'])
  })
})
