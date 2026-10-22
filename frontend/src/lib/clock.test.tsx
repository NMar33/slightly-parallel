import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { dayStartOf, useDayStart } from './clock'

afterEach(() => { vi.useRealTimers() })

describe('useDayStart', () => {
  it('is local midnight of the day', () => {
    expect(dayStartOf(new Date(2026, 9, 12, 15, 30).getTime())).toBe(new Date(2026, 9, 12).getTime())
  })

  it('rolls to the new day for a page left open over midnight, and holds still within a day', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 12, 23, 58))
    const { result } = renderHook(() => useDayStart())
    const first = result.current
    expect(first).toBe(new Date(2026, 9, 12).getTime())
    act(() => { vi.advanceTimersByTime(60_000) })
    expect(result.current).toBe(first)
    act(() => { vi.advanceTimersByTime(2 * 60_000) })
    expect(result.current).toBe(new Date(2026, 9, 13).getTime())
  })

  it('does not redraw its caller within the day', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 12, 12, 0))
    let renders = 0
    renderHook(() => { renders += 1; return useDayStart() })
    const settled = renders
    act(() => { vi.advanceTimersByTime(10 * 60_000) })
    expect(renders).toBe(settled)
  })
})
