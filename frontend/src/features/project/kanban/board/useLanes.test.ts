import { afterEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import { useLanes } from './useLanes'
import type { KanbanView, TaskRow } from '../model'

afterEach(() => localStorage.clear())

const props = (boardKey: string) => ({
  boardKey, view: 'lanes' as KanbanView, tasks: [] as TaskRow[], setTasks: () => {}, setRefreshTick: () => {},
})

describe('useLanes', () => {
  it("reads the next board's lanes when the board changes, and writes them under its key", () => {
    localStorage.setItem('sp-lanes:alpha', JSON.stringify(['a-lane']))
    localStorage.setItem('sp-lanes:beta', JSON.stringify(['b-lane']))
    localStorage.setItem('sp-lanes-collapsed:beta', JSON.stringify(['b-lane']))
    const { result, rerender } = renderHook((p: ReturnType<typeof props>) => useLanes(p), { initialProps: props('alpha') })
    expect(result.current.lanes).toContain('a-lane')
    rerender(props('beta'))
    expect(result.current.lanes).toContain('b-lane')
    expect(result.current.lanes).not.toContain('a-lane')
    expect(result.current.collapsedLanes.has('b-lane')).toBe(true)
    act(() => result.current.toggleLane('b-lane'))
    expect(JSON.parse(localStorage.getItem('sp-lanes-collapsed:beta')!)).toEqual([])
    expect(localStorage.getItem('sp-lanes-collapsed:alpha')).toBeNull()
  })

  it('a stored value that is not a list reads as none', () => {
    localStorage.setItem('sp-lanes:alpha', '{"x":1}')
    const { result } = renderHook(() => useLanes(props('alpha')))
    expect(result.current.lanes).toEqual([])
  })
})
