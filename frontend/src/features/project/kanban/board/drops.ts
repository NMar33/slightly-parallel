/**
 * Where a drop lands: one card (between its new neighbours, by position),
 * a whole batch dragged by its handle, the selection, or the archive. The
 * board builds these each render over its current state.
 */

import { type Dispatch, type SetStateAction } from 'react'
import { toast } from '../../../../components/primitives'
import { postJson } from '../../../../lib/getJson'
import { OPERATOR_ACTOR } from '../../types'
import { SELECTION, isToday, laneOf, laneUpdate as laneWrite, normalizeStatus, parseBulk } from '../model'
import type { SortMode, TaskRow } from '../model'
import { ARCHIVE } from './model'
import { putBack } from '../boardData'
import { t, tn } from '../../../../i18n/scope/project'

export type PendingDrop = {
  draggedId: string; targetStatus: string; targetLane?: string; beforeTaskId?: string | null
}

export function boardDrops({
  tasks, setTasks, columnKeyOf, today, sorts, setPendingDrop, setArchived, moveSelection, setRefreshTick,
}: {
  tasks: TaskRow[]
  setTasks: (u: TaskRow[] | ((cur: TaskRow[]) => TaskRow[])) => void
  columnKeyOf: (t: TaskRow) => string
  today: string
  sorts: Record<string, SortMode>
  setPendingDrop: (d: PendingDrop | null) => void
  setArchived: (ids: string[], on: boolean) => Promise<void>
  moveSelection: (targetStatus: string, targetLane?: string, beforeTaskId?: string | null) => Promise<void>
  setRefreshTick: Dispatch<SetStateAction<number>>
}) {
  const persistUpdate = async (id: string, updates: Partial<TaskRow>) => {
    try {
      await postJson(`/api/tasks/${encodeURIComponent(id)}/update`, { ...updates, actor: OPERATOR_ACTOR })
      // A small delay lets the backend watchdog + view rebuild settle before
      // the refetch, avoiding a race where the refetch reads a stale cache.
      setTimeout(() => setRefreshTick((t) => t + 1), 250)
    } catch (e) {
      toast.error(t('Could not save the task'), { description: String((e as Error)?.message ?? e) })
      setRefreshTick((t) => t + 1)
    }
  }

  /**
   * Handle drop — supports both column-change and reorder-within-column.
   * `beforeTaskId` set → the dropped card slots ABOVE that card;
   * `beforeTaskId` null → append at the end of the column.
   */
  /**
   * Move every task of one column (optionally one lane of it) to another
   * column in a single gesture — the "agent finished the batch" move.
   * Optimistic, with rollback and one toast summarising the outcome.
   */
  const handleBulkMove = async (
    sourceStatus: string,
    targetStatus: string,
    sourceLane?: string,
    targetLane?: string,
    /** Only the cards planned for today — the Today lane's own batch. */
    onlyToday?: boolean,
  ) => {
    if (sourceStatus === targetStatus && (sourceLane ?? '') === (targetLane ?? '')) return
    const moving = tasks.filter(
      (t) =>
        columnKeyOf(t) === sourceStatus &&
        (!sourceLane || laneOf(t) === sourceLane) &&
        (!onlyToday || isToday(t, today)),
    )
    if (moving.length === 0) return

    const ids = new Set(moving.map((t) => t.id))
    const laneUpdate = laneWrite(targetLane)
    const prevTasks = tasks
    setTasks((prev) =>
      prev.map((t) =>
        ids.has(t.id) ? { ...t, status: targetStatus, ...laneUpdate } : t,
      ),
    )

    const results = await Promise.allSettled(
      moving.map((t) =>
        postJson(`/api/tasks/${encodeURIComponent(t.id)}/update`, {
          status: targetStatus,
          ...laneUpdate,
          actor: OPERATOR_ACTOR,
        }),
      ),
    )
    const failed = results.filter((r) => r.status === 'rejected').length
    if (failed > 0) {
      setTasks(putBack(prevTasks, ids))
      toast.error(t('Could not move the whole column'), {
        description: `${failed} of ${moving.length} task${moving.length === 1 ? '' : 's'} failed.`,
      })
    } else {
      toast.success(
        t('Moved {tasks} → {status}', { tasks: tn(moving.length, '{n} task', '{n} tasks'), status: targetStatus }),
      )
    }
    setRefreshTick((n) => n + 1)
  }

  const handleDrop = (
    draggedId: string,
    targetStatus: string,
    targetLane?: string,
    beforeTaskId?: string | null,
    force = false,
  ) => {
    if (!draggedId) return
    // Any selected card was dragged: the whole selection travels.
    if (draggedId === SELECTION) {
      void moveSelection(targetStatus, targetLane, beforeTaskId)
      return
    }
    // A whole column was dragged by its bulk handle.
    const bulk = parseBulk(draggedId)
    if (bulk) {
      if (targetStatus === ARCHIVE) {
        const ids = tasks
          .filter((t) => !t.archived_at && columnKeyOf(t) === bulk.status && (!bulk.lane || laneOf(t) === bulk.lane))
          .filter((t) => !bulk.onlyToday || isToday(t, today))
          .map((t) => t.id)
        if (ids.length) void setArchived(ids, true)
        return
      }
      void handleBulkMove(
        bulk.status,
        targetStatus,
        bulk.lane || undefined,
        targetLane,
        bulk.onlyToday,
      )
      return
    }
    const task = tasks.find((t) => t.id === draggedId)
    if (!task) return
    // Dropped on the archive strip: archive (a no-op if it already is).
    if (targetStatus === ARCHIVE) {
      if (!task.archived_at) void setArchived([task.id], true)
      return
    }
    // A drop into a sorted view would not stick where it lands — pause and
    // ask: back to manual, adopt this order as manual, or cancel.
    if (!force && targetStatus !== ARCHIVE && (sorts[targetStatus] ?? 'manual') !== 'manual') {
      setPendingDrop({ draggedId, targetStatus, targetLane, beforeTaskId })
      return
    }
    // An archived card dragged back onto the board: restore, then move.
    if (task.archived_at) void setArchived([task.id], false)

    // Column-mates (in target status + optional lane) sorted by position.
    const posOf = (t: TaskRow): number => {
      const n = Number(t.position)
      return Number.isFinite(n) ? n : 0
    }
    const inTarget = tasks
      .filter((t) => t.id !== draggedId) // exclude the dragged card itself
      .filter((t) => columnKeyOf(t) === targetStatus)
      .filter((t) => !targetLane || laneOf(t) === targetLane)
      .sort((a, b) => posOf(a) - posOf(b))

    // New position: midpoint of the gap around the drop slot.
    let newPos: number
    if (beforeTaskId) {
      const idx = inTarget.findIndex((t) => t.id === beforeTaskId)
      if (idx === -1) {
        newPos = inTarget.length > 0 ? posOf(inTarget[inTarget.length - 1]!) + 10 : 10
      } else {
        const above = idx === 0 ? 0 : posOf(inTarget[idx - 1]!)
        const at = posOf(inTarget[idx]!)
        newPos = (above + at) / 2
        // Handle collision (rare) — nudge past the occupied slot.
        if (newPos === above || newPos === at) newPos = at + 0.5
      }
    } else {
      // Append at the end.
      newPos = inTarget.length > 0 ? posOf(inTarget[inTarget.length - 1]!) + 10 : 10
    }

    const updates: Partial<TaskRow> = { position: String(newPos) }
    if (normalizeStatus(task.status) !== targetStatus) updates.status = targetStatus
    if (targetLane && laneOf(task) !== targetLane) Object.assign(updates, laneWrite(targetLane))

    // Optimistic local update
    setTasks((prev) => prev.map((t) => (t.id === draggedId ? { ...t, ...updates } : t)))
    persistUpdate(draggedId, updates)
  }

  return { handleBulkMove, handleDrop }
}
