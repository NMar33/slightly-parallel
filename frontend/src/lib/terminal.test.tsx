import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const toastError = vi.fn()
vi.mock('sonner', () => ({ toast: { error: (m: string) => toastError(m), success: vi.fn() } }))

import { useTerminalActions } from './terminal'

afterEach(() => { vi.unstubAllGlobals(); toastError.mockReset() })

function actions() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  return renderHook(() => useTerminalActions(), { wrapper }).result
}

describe('useTerminalActions', () => {
  it('says a refused close in the server\'s words instead of rejecting', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/close')
      ? { ok: false, status: 409, json: async () => ({ detail: 'the terminal is busy' }) }
      : { ok: true, status: 200, json: async () => ({}), text: async () => '{}' }))
    const act = actions()
    await expect(act.current.close('t1')).resolves.toBeUndefined()
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('The terminal could not close: the terminal is busy'))
  })

  it('says a refused setting, and still reads the state again', async () => {
    const fetch = vi.fn(async (url: string, init?: RequestInit) => init?.method === 'POST'
      ? { ok: false, status: 422, json: async () => ({ detail: 'out of range' }) }
      : { ok: true, status: 200, json: async () => ({}), text: async () => '{}' })
    vi.stubGlobal('fetch', fetch)
    const act = actions()
    await expect(act.current.setting({ 'terminal.font_size': 99 })).resolves.toBeUndefined()
    expect(toastError).toHaveBeenCalledWith('The setting was not saved: out of range')
  })
})
