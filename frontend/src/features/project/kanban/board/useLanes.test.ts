import { afterEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import { useLanes } from './useLanes'
import { laneKey, type KanbanView, type TaskRow } from '../model'

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
    expect(result.current.lanes.map((lane) => lane.name)).toContain('a-lane')
    rerender(props('beta'))
    expect(result.current.lanes.map((lane) => lane.name)).toContain('b-lane')
    expect(result.current.lanes.map((lane) => lane.name)).not.toContain('a-lane')
    expect(result.current.collapsedLanes.has(laneKey('', 'b-lane'))).toBe(true)
    act(() => result.current.toggleLane(laneKey('', 'b-lane')))
    expect(JSON.parse(localStorage.getItem('sp-lanes-collapsed:beta')!)).toEqual([])
    expect(localStorage.getItem('sp-lanes-collapsed:alpha')).toBeNull()
  })

  it('a stored value that is not a list reads as none', () => {
    localStorage.setItem('sp-lanes:alpha', '{"x":1}')
    const { result } = renderHook(() => useLanes(props('alpha')))
    expect(result.current.lanes).toEqual([])
  })
})

it('groups agent lanes behind one collapsed row and opens them together', () => {
  const tasks = [
    { id: 'a', assignee: 'Backend', project: 'alpha' },
    { id: 'b', assignee: 'bugs', project: 'alpha', lane_kind: 'agent' },
    { id: 'c', assignee: 'ideas', project: 'alpha', lane_kind: 'agent' },
  ]
  const { result } = renderHook(() => useLanes({ ...props('alpha'), tasks }))
  expect(result.current.lanes.map((lane) => lane.name)).toEqual(['Backend'])
  expect(result.current.agentLanes.map(({ name, project }) => [name, project])).toEqual([['bugs', 'alpha'], ['ideas', 'alpha']])
  expect(result.current.agentsOpen).toBe(false)
  act(() => result.current.toggleAgents())
  expect(result.current.lanes.map((lane) => lane.name)).toEqual(['Backend', 'bugs', 'ideas'])
})

it('keeps case-equivalent lanes from different projects in their own groups', () => {
  const tasks: TaskRow[] = [
    { id: 'a', project: 'alpha', assignee: 'Audio' },
    { id: 'b', project: 'beta', assignee: 'audio', lane_kind: 'agent' },
  ]
  const { result } = renderHook(() => useLanes({ ...props('combined'), tasks }))
  expect(result.current.agentLanes.length).toBe(1)
  act(() => result.current.toggleAgents())
  expect(result.current.lanes.map(({ key, name, agent }) => [key, name, agent])).toEqual([
    [laneKey('alpha', 'audio'), 'Audio', false],
    [laneKey('beta', 'audio'), 'audio', true],
  ])
})

it('uses one key for canonically equivalent and fully case-folded lane names', () => {
  expect(laneKey('alpha', 'Straße')).toBe(laneKey('alpha', 'STRASSE'))
  expect(laneKey('alpha', 'Café')).toBe(laneKey('alpha', 'Cafe\u0301'))
  expect(laneKey('alpha', 'τελος')).toBe(laneKey('alpha', 'ΤΕΛΟΣ'))
})
