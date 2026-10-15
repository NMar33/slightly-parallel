import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import { useDismissed } from './overview'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); localStorage.clear() })

describe('useDismissed', () => {
  it('sends a dismissal to the server copy of the preferences', async () => {
    vi.useFakeTimers()
    const sent = vi.fn(async () => ({ ok: true }))
    vi.stubGlobal('fetch', sent)
    const { result } = renderHook(() => useDismissed())
    act(() => result.current.dismiss('cl_1'))
    expect(result.current.dismissed).toEqual(['cl_1'])
    await act(async () => { vi.advanceTimersByTime(500) })
    const body = JSON.parse(String((sent.mock.calls[0] as unknown as [string, RequestInit])[1].body))
    expect(body.values['sp-promptlib-dismissed']).toBe('["cl_1"]')
  })

  it('reads a stored list, and nothing from a value that is not one', () => {
    localStorage.setItem('sp-promptlib-dismissed', '{"a":1}')
    expect(renderHook(() => useDismissed()).result.current.dismissed).toEqual([])
    localStorage.setItem('sp-promptlib-dismissed', '["x"]')
    expect(renderHook(() => useDismissed()).result.current.dismissed).toEqual(['x'])
  })
})
