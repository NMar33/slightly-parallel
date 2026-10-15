/**
 * Shift-click gathers cards into a selection — in the order clicked, so
 * grouping can build a queue that reads the way you picked it. The
 * selection is momentary: Escape drops it, and so does acting on it.
 */

import { useCallback, useEffect, useState } from 'react'
import { toast } from '../../../../components/primitives'
import { laneOf } from '../model'
import type { TaskRow } from '../model'
import { ARCHIVE } from './model'
import type { Patch } from './writes'
import { t, tn } from '../../../../i18n/scope/project'

export function useSelection({ tasks, today, columnKeyOf, patchMany, setArchived }: {
  tasks: TaskRow[]
  today: string
  columnKeyOf: (t: TaskRow) => string
  patchMany: (rows: Patch[]) => Promise<void>
  setArchived: (ids: string[], on: boolean) => Promise<void>
}) {
  const [selection, setSelection] = useState<string[]>([])
  // Stable: cards get this directly, and they are memoized on their props.
  const toggleSelect = useCallback((id: string) => setSelection((cur) =>
    cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]), [])
  const clear = () => setSelection([])
  const selectedTasks = selection
    .map((id) => tasks.find((t) => t.id === id))
    .filter((t): t is TaskRow => !!t)
  useEffect(() => {
    if (selection.length === 0) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelection([]) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selection.length])

  /** Group the selection into one queue, in the order it was picked. The
   *  first card decides where the queue lives; the rest join its column. */
  const groupSelection = async () => {
    if (selectedTasks.length < 2) return
    const first = selectedTasks[0]!
    const rest = selectedTasks.slice(1)
    const stackId = first.stack_id || first.id
    const base = Number(first.position) || 0
    const before = selectedTasks.map((t) => ({ id: t.id, patch: {
      stack_id: t.stack_id || '', status: String(t.status || ''),
      assignee: String(t.assignee || ''), lane: String(t.lane || ''),
      position: String(Number(t.position) || 0),
    } }))
    const writes: Patch[] = [
      ...(first.stack_id ? [] : [{ id: first.id, patch: { stack_id: stackId } }]),
      ...rest.map((t, i) => ({ id: t.id, patch: {
        stack_id: stackId,
        status: String(first.status || ''),
        assignee: String(first.assignee || ''),
        lane: String(first.lane || first.assignee || 'unassigned'),
        position: String(base + i + 1),
      } })),
    ]
    const n = selectedTasks.length
    const headline = String(first.title ?? '').slice(0, 32)
    setSelection([])
    await patchMany(writes)
    toast.success(t('Grouped {n} into a queue behind “{headline}”', { n, headline }), {
      action: { label: t('Undo'), onClick: () => void patchMany(before) },
    })
  }
  /**
   * The selection, dropped somewhere: everything goes to that column (and
   * lane), keeping the order it was picked. Landing on a card puts the set
   * just before it; landing on the column appends.
   */
  const moveSelection = async (targetStatus: string, targetLane?: string, beforeTaskId?: string | null) => {
    if (selectedTasks.length === 0) return
    const pos = (t: TaskRow) => Number(t.position) || 0
    if (targetStatus === ARCHIVE) {
      const ids = selectedTasks.filter((t) => !t.archived_at).map((t) => t.id)
      setSelection([])
      if (ids.length) void setArchived(ids, true)
      return
    }
    const moving = selectedTasks
    const ids = new Set(moving.map((t) => t.id))
    const inTarget = tasks
      .filter((t) => !ids.has(t.id) && columnKeyOf(t) === targetStatus)
      .filter((t) => !targetLane || laneOf(t) === targetLane)
      .sort((a, b) => pos(a) - pos(b))
    // Where the set lands: before the card dropped on, else after the last.
    const idx = beforeTaskId ? inTarget.findIndex((t) => t.id === beforeTaskId) : -1
    const lower = idx > 0 ? pos(inTarget[idx - 1]!) : idx === 0 ? pos(inTarget[0]!) - moving.length - 1 : (inTarget.length ? pos(inTarget[inTarget.length - 1]!) : 0)
    const upper = idx >= 0 ? pos(inTarget[idx]!) : lower + moving.length + 1
    const step = (upper - lower) / (moving.length + 1)
    const laneUpdate = targetLane && targetLane !== 'unassigned'
      ? { assignee: targetLane, lane: targetLane }
      : {}
    const before = moving.map((t) => ({ id: t.id, patch: {
      status: String(t.status || ''), position: String(pos(t)),
      assignee: String(t.assignee || ''), lane: String(t.lane || ''),
    } }))
    const writes = moving.map((t, i) => ({ id: t.id, patch: {
      status: targetStatus, position: String(lower + step * (i + 1)), ...laneUpdate,
    } as Record<string, string> }))
    const n = moving.length
    setSelection([])
    await patchMany(writes)
    toast.success(t('{n} moved', { n }), {
      action: { label: t('Undo'), onClick: () => void patchMany(before) },
    })
  }

  /** Plan the whole selection for today. */
  const todaySelection = async () => {
    const before = selectedTasks.map((t) => ({ id: t.id, patch: { today_on: t.today_on || '' } }))
    const rows = selectedTasks.map((t) => ({ id: t.id, patch: { today_on: today } }))
    setSelection([])
    await patchMany(rows)
    toast.success(tn(rows.length, '{n} task planned for today', '{n} tasks planned for today'), {
      action: { label: t('Undo'), onClick: () => void patchMany(before) },
    })
  }

  return { selection, toggleSelect, clear, selectedTasks, groupSelection, moveSelection, todaySelection }
}

export type Selection = ReturnType<typeof useSelection>
