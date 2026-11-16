import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useSessionTurns } from './sessionTurns'

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

afterEach(() => { vi.unstubAllGlobals() })

describe('useSessionTurns', () => {
  it('answers for every chat asked, past the size of its cache', async () => {
    // 401 chats: the cache keeps 400, so the first one was evicted before
    // the answer was built, and came back with no turns.
    const sessions = Array.from({ length: 401 }, (_, i) => ({ id: `ses_${i}`, turns_n: 1, end_time: '10:00', chat_end_line: 5 }))
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const ids = decodeURIComponent(/ids=([^&]+)/.exec(String(url))![1]!).split(',')
      const turns = Object.fromEntries(ids.map((id) => [id, [{ n: 1, at: '10:00', user: `hi from ${id}`, agent: 'ok' }]]))
      return new Response(JSON.stringify({ turns }), { status: 200, headers: { 'content-type': 'application/json' } })
    }))
    const { result } = renderHook(() => useSessionTurns(sessions), { wrapper })
    await waitFor(() => expect(result.current.data).toBeDefined())
    const got = result.current.data!
    expect(Object.keys(got)).toHaveLength(401)
    expect(got.ses_0![0]!.user).toBe('hi from ses_0')
    expect(got.ses_400![0]!.user).toBe('hi from ses_400')
  })
})
