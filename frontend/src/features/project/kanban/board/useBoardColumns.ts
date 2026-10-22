/**
 * The board's columns: which view (3-col, 5-col, lanes), which columns are
 * shown, which strips are open, how each column sorts — each remembered per
 * board — and the tasks sorted into them: per column, per lane cell, the
 * archive, and how many Done cards show before the rest fold.
 */

import { useMemo, useState } from 'react'
import { useIntSetting, useStrSetting } from '../../../../lib/settings'
import {
  VIEW_COLUMNS, doneVisibleLimit, isToday, laneOf, normalizeStatus, readStoredView, sortTasks, storeView,
} from '../model'
import type { KanbanView, SortMode, TaskRow } from '../model'
import { readRecord } from './prefs'
import { useKeyedPref } from '../../../../lib/uiPrefs'
import type { ByLaneCol } from './types'

/** The open-state key of the archive column among the strips. */
const ARCHIVE_STRIP = '__archive__'

export function useBoardColumns({
  boardKey, tasks, todayTasks, today, statusSince, sprintFilter, onlyRemembered, onlyToday,
}: {
  boardKey: string
  tasks: TaskRow[]
  todayTasks: TaskRow[]
  today: string
  statusSince: Record<string, string>
  sprintFilter: string | null
  onlyRemembered: boolean
  onlyToday: boolean
}) {
  // Navigating between projects reuses the board, so every remembered
  // choice is read again for the new board (board/prefs).
  const [view, setView] = useKeyedPref<KanbanView>(boardKey, readStoredView, storeView)
  // Sort views per column — display order only; positions stay the truth.
  const [sorts, setSorts] = useKeyedPref(`sp-kanban-sort:${boardKey}`, readRecord<SortMode>)
  const setSort = (col: string, mode: SortMode) => setSorts({ ...sorts, [col]: mode })
  // Column settings: which columns this board shows (tick/untick in the
  // gear popup), and which strips (Parked, Archive) are unfolded. Synced
  // prefs, per board.
  const [hiddenCols, setHiddenCols] = useKeyedPref(`sp-kanban-cols:${boardKey}`, readRecord<boolean>)
  const setColHidden = (key: string, hidden: boolean) => {
    const next = { ...hiddenCols, [key]: hidden }
    if (!hidden) delete next[key]
    setHiddenCols(next)
  }
  const [openStrips, setOpenStrips] = useKeyedPref(`sp-kanban-strips:${boardKey}`, readRecord<boolean>)
  const toggleStrip = (key: string) => setOpenStrips({ ...openStrips, [key]: !openStrips[key] })

  const allColumns = VIEW_COLUMNS[view]
  const columns = useMemo(() => allColumns.filter((c) => !hiddenCols[c.key]), [allColumns, hiddenCols])

  /** Column key a task lands in: its normalized status if that is a visible
   *  column in the current view, else the 'unclassified' fallback bucket. */
  const columnKeyOf = useMemo(() => {
    const keys = new Set(columns.map((c) => c.key))
    return (t: TaskRow): string => {
      const s = normalizeStatus(t.status)
      return keys.has(s) ? s : 'unclassified'
    }
  }, [columns])

  // Archived tasks live in the archive column (folded by default), never in
  // the status columns. Its open state is a synced pref like Parked's.
  const showArchived = !!openStrips[ARCHIVE_STRIP]
  const toggleArchived = () => toggleStrip(ARCHIVE_STRIP)
  const showArchiveCol = !hiddenCols[ARCHIVE_STRIP]
  const archivedTasks = useMemo(() => tasks.filter((t) => t.archived_at), [tasks])
  const archivedN = archivedTasks.length

  const tasksByStatus = useMemo(() => {
    const map: Record<string, TaskRow[]> = {}
    for (const col of columns) map[col.key] = []
    const hiddenStatuses = new Set(allColumns.filter((c) => hiddenCols[c.key]).map((c) => c.key))
    for (const t of tasks) {
      if (t.archived_at) continue
      if (hiddenStatuses.has(normalizeStatus(t.status))) continue
      if (sprintFilter === 'none' && (t.sprint_id ?? '')) continue
      if (sprintFilter && sprintFilter !== 'none' && t.sprint_id !== sprintFilter) continue
      if (onlyRemembered && t.remember !== 'yes') continue
      if (onlyToday && !isToday(t, today)) continue
      map[columnKeyOf(t)]!.push(t)
    }
    for (const col of columns) {
      const mode = (sorts[col.key] ?? 'manual') as SortMode
      if (mode !== 'manual') map[col.key] = sortTasks(map[col.key]!, mode, statusSince)
    }
    return map
  }, [tasks, columns, allColumns, hiddenCols, columnKeyOf, sorts, statusSince, sprintFilter, onlyRemembered, onlyToday, today])

  /**
   * The lane view's cells, the per-lane totals and the Today band's
   * per-column groups, in one pass. These used to be a filter over the
   * whole task list for every lane × column, on every render — the cost
   * grew with the board squared.
   */
  const byLaneCol = useMemo((): ByLaneCol => {
    // Cell key: lane + column. A lane name is typed text, never a newline.
    const cells = new Map<string, TaskRow[]>()
    const laneN = new Map<string, number>()
    const todayCols = new Map<string, TaskRow[]>()
    const add = (map: Map<string, TaskRow[]>, k: string, t: TaskRow) => {
      const cell = map.get(k)
      if (cell) cell.push(t)
      else map.set(k, [t])
    }
    // Walk the columns' own lists so each cell keeps its sorted order.
    for (const col of columns) {
      for (const t of tasksByStatus[col.key] ?? []) add(cells, `${laneOf(t)}\n${col.key}`, t)
    }
    // The lane header counts every task with that lane, filtered or not —
    // the number says what the lane holds, not what the board shows.
    for (const t of tasks) laneN.set(laneOf(t), (laneN.get(laneOf(t)) ?? 0) + 1)
    for (const t of todayTasks) add(todayCols, columnKeyOf(t), t)
    return { cells, laneN, todayCols }
  }, [columns, tasksByStatus, tasks, todayTasks, columnKeyOf])

  /**
   * How many Done cards the board shows before collapsing the rest.
   * "match" keeps the column no taller than the busiest other column, so the
   * board stays balanced as Done grows without bound.
   */
  const [doneExpanded, setDoneExpanded] = useState(false)
  const doneMode = useStrSetting('tasks.done_visible', 'match')
  const doneFixed = useIntSetting('tasks.done_visible_count', 5)
  const doneLimit = useMemo(
    () =>
      doneVisibleLimit(
        doneMode,
        doneFixed,
        columns
          .filter((c) => c.key !== 'done')
          .map((c) => (tasksByStatus[c.key] ?? []).length),
        doneExpanded,
      ),
    [doneExpanded, doneMode, doneFixed, columns, tasksByStatus],
  )

  return {
    view, setView, sorts, setSort, hiddenCols, setColHidden, openStrips, toggleStrip,
    allColumns, columns, columnKeyOf,
    showArchived, toggleArchived, showArchiveCol, archivedTasks, archivedN,
    tasksByStatus, byLaneCol, doneLimit, doneExpanded, setDoneExpanded,
  }
}
