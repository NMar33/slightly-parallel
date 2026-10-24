import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useDayPlan } from './useDayPlan'
import { todayISO } from '../model'
import type { TaskRow } from '../model'

describe('useDayPlan', () => {
  it('gives the day\'s buttons back after a write that did not land', async () => {
    // Before: the busy flag was set, the early return on a failed write
    // skipped the reset, and "All done" stayed "…" until the board remounted.
    const tasks = [{ id: 'tk_1', title: 'a', status: 'doing', today_on: todayISO() } as unknown as TaskRow]
    const { result } = renderHook(() => useDayPlan({
      tasks, setTasks: () => {}, patchMany: async () => 1, bump: () => {},
    }))
    await act(async () => { await result.current.todayAllDone() })
    expect(result.current.dayBusy).toBe(false)
    await act(async () => { await result.current.todayDismiss() })
    expect(result.current.dayBusy).toBe(false)
  })
})
