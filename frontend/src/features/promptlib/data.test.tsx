import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }))
vi.mock('sonner', () => ({ toast: Object.assign(vi.fn(), { error: toastError, success: vi.fn() }) }))

import { useLibraryWrites } from './data'

afterEach(() => { vi.unstubAllGlobals(); toastError.mockReset() })

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('library writes', () => {
  it('a refused archive, rename or keep is said, not swallowed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({ detail: 'prompt not found: pr_x' }) })))
    const { result } = renderHook(() => useLibraryWrites('pr_x'), { wrapper })
    await act(async () => { await result.current.update.mutateAsync({ status: 'archived' }).catch(() => {}) })
    expect(toastError).toHaveBeenCalledWith('prompt not found: pr_x')
    await act(async () => { await result.current.keep.mutateAsync('cl_1').catch(() => {}) })
    expect(toastError).toHaveBeenCalledTimes(2)
  })
})
