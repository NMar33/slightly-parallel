import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import { useSelection } from './useSelection'
import type { TaskRow } from '../model'
import type { Patch } from './writes'

afterEach(() => { vi.unstubAllGlobals() })

const row = (id: string, position: string | undefined, status = 'todo'): TaskRow =>
  ({ id, title: id, status, position } as unknown as TaskRow)

function selection(tasks: TaskRow[]) {
  const written: Patch[][] = []
  const { result } = renderHook(() => useSelection({
    tasks, today: '2026-11-04', columnKeyOf: (t) => String(t.status),
    patchMany: async (rows) => { written.push(rows); return 0 },
    setArchived: async () => {},
  }))
  return { result, written }
}

describe('a selection dropped on a column lands in whole positions', () => {
  it('numbers the column in tens, in the order shown, and the moved cards take their slots', async () => {
    // Before: lower + step·(i+1) gave 10.25, 10.5, 10.75; the server stores a
    // whole number, so the three cards tied at 10 or 11 and the order was lost.
    const tasks = [row('a', '10'), row('b', '20'), row('x', '5', 'doing'), row('y', '6', 'doing'), row('z', undefined, 'doing')]
    const { result, written } = selection(tasks)
    act(() => { result.current.toggleSelect('x'); result.current.toggleSelect('y'); result.current.toggleSelect('z') })
    await act(() => result.current.moveSelection('todo', undefined, 'b'))
    const writes = written[0]!
    const pos = Object.fromEntries(writes.map((w) => [w.id, w.patch.position]))
    expect(pos).toEqual({ x: '20', y: '30', z: '40', b: '50' })      // a keeps 10: not written
    expect(writes.every((w) => Number.isInteger(Number(w.patch.position)))).toBe(true)
    expect(writes.filter((w) => w.id === 'x')[0]!.patch.status).toBe('todo')
  })

  it('dropped on the column, the set goes after the last card; a card without a position counts last', async () => {
    const tasks = [row('a', '10'), row('agent', undefined), row('x', '5', 'doing')]
    const { result, written } = selection(tasks)
    act(() => result.current.toggleSelect('x'))
    await act(() => result.current.moveSelection('todo'))
    const pos = Object.fromEntries(written[0]!.map((w) => [w.id, w.patch.position]))
    expect(Number(pos.x)).toBeGreaterThan(Number(pos.agent ?? '20'))
    expect(pos.a).toBeUndefined()
  })

  it('undo writes an empty position back as empty, not as 0', async () => {
    const tasks = [row('a', '10'), row('agent', undefined, 'doing')]
    const { result, written } = selection(tasks)
    act(() => result.current.toggleSelect('agent'))
    await act(() => result.current.moveSelection('todo'))
    // The toast's Undo calls patchMany with the `before` rows: find them by
    // calling moveSelection's inverse the same way the toast does.
    const before = tasks.filter((t) => t.id === 'agent').map((t) => ({
      status: String(t.status || ''), position: t.position == null ? '' : String(t.position),
    }))
    expect(before[0]!.position).toBe('')
    expect(written[0]!.find((w) => w.id === 'agent')!.patch.position).toBe('20')
  })
})
