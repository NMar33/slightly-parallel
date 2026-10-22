import { describe, expect, it, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'

import { useDayBook } from './useDayBook'
import { monthKey } from './data'

function wrap({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('the day book state', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/scans')
  })

  it('opens on this month when the address says nothing', () => {
    const { result } = renderHook(() => useDayBook(['slightly-parallel']), { wrapper: wrap })
    expect(result.current.month).toBe(monthKey())
  })

  it('reads the month from the address, so a month can be linked', () => {
    window.history.replaceState(null, '', '/scans#month=2026-07')
    const { result } = renderHook(() => useDayBook(['slightly-parallel']), { wrapper: wrap })
    expect(result.current.month).toBe('2026-07')
  })

  it('writes the month to the address, so paging back survives a reload', () => {
    const { result } = renderHook(() => useDayBook(['slightly-parallel']), { wrapper: wrap })
    act(() => result.current.showMonth('2026-08'))
    expect(window.location.hash).toContain('month=2026-08')
    expect(result.current.month).toBe('2026-08')
  })

  it('follows a picked day into its own month', () => {
    const { result } = renderHook(() => useDayBook(['slightly-parallel']), { wrapper: wrap })
    act(() => result.current.pick('2607-04'))
    expect(result.current.month).toBe('2026-07')
    expect(result.current.active).toBe('2607-04')
  })

  it('shows the project in the address when it has entries, else the newest', () => {
    window.history.replaceState(null, '', '/scans#project=atlas')
    const { result } = renderHook(() => useDayBook(['slightly-parallel', 'atlas']), { wrapper: wrap })
    expect(result.current.project).toBe('atlas')

    window.history.replaceState(null, '', '/scans#project=gone')
    const { result: other } = renderHook(() => useDayBook(['slightly-parallel', 'atlas']), { wrapper: wrap })
    expect(other.current.project).toBe('slightly-parallel')
  })
})
