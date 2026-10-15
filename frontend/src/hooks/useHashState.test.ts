import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { useHashState } from './useHashState'

describe('useHashState', () => {
  beforeEach(() => { window.history.replaceState(null, '', '/x') })

  it('keeps a tab token in front of the state it writes', () => {
    window.history.replaceState(null, '', '/project/p#calendar&view=week')
    const { result } = renderHook(() => useHashState())
    expect(result.current[0]).toEqual({ view: 'week' })
    act(() => result.current[1]({ month: '2026-09' }))
    expect(window.location.hash).toBe('#calendar&view=week&month=2026-09')
    act(() => result.current[1]({ view: '' }))
    expect(window.location.hash).toBe('#calendar&month=2026-09')
  })

  it('lets two instances share one hash', () => {
    const a = renderHook(() => useHashState())
    const b = renderHook(() => useHashState())
    act(() => a.result.current[1]({ project: 'slightly-parallel' }))
    act(() => b.result.current[1]({ view: 'week' }))
    expect(window.location.hash).toBe('#project=slightly-parallel&view=week')
    expect(a.result.current[0]).toEqual({ project: 'slightly-parallel', view: 'week' })
    expect(b.result.current[0]).toEqual({ project: 'slightly-parallel', view: 'week' })
  })

  it('writes a plain state hash when there is no token', () => {
    const { result } = renderHook(() => useHashState())
    act(() => result.current[1]({ q: 'a b' }))
    expect(window.location.hash).toBe('#q=a%20b')
  })

  it('reads a malformed escape as typed instead of throwing', () => {
    window.history.replaceState(null, '', '/x#q=100%&view=week')
    const { result } = renderHook(() => useHashState())
    expect(result.current[0]).toEqual({ q: '100%', view: 'week' })
  })

  it("keeps the router's history entry state when it writes the hash", () => {
    window.history.replaceState({ usr: null, key: 'k1', idx: 3 }, '', '/x')
    const { result } = renderHook(() => useHashState())
    act(() => result.current[1]({ view: 'week' }))
    expect(window.history.state).toEqual({ usr: null, key: 'k1', idx: 3 })
  })
})
