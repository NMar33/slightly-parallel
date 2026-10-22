/**
 * useLanes — the swim lanes' own state: which lanes exist beyond the
 * assignees, their order, which are folded, and the add-lane form, each
 * remembered per board; plus rename and delete, which reach the tasks.
 */

import { useMemo, useState, type Dispatch, type SetStateAction } from 'react'
import { readStrings } from './prefs'
import { persistPref, useKeyedPref } from '../../../../lib/uiPrefs'
import { toast } from '../../../../components/primitives'
import { postJson } from '../../../../lib/getJson'
import { OPERATOR_ACTOR } from '../../types'
import { laneOf, orderLanes } from '../model'
import type { KanbanView, TaskRow } from '../model'
import { putBack } from '../boardData'
import { t, tn } from '../../../../i18n/scope/project'

export function useLanes({
  boardKey, view, tasks, setTasks, setRefreshTick,
}: {
  boardKey: string
  view: KanbanView
  tasks: TaskRow[]
  setTasks: (u: TaskRow[] | ((cur: TaskRow[]) => TaskRow[])) => void
  setRefreshTick: Dispatch<SetStateAction<number>>
}) {
  // Swimlanes: derived from unique assignees + any user-added empty lanes,
  // remembered per board.
  const [extraLanes, saveExtraLanes] = useKeyedPref(`sp-lanes:${boardKey}`, readStrings)
  // Lane order — manual, remembered per project; lanes not yet placed follow
  // alphabetically, "unassigned" last unless the user moved it.
  const [laneOrder, saveLaneOrder] = useKeyedPref(`sp-lanes-order:${boardKey}`, readStrings)
  const lanes = useMemo(() => {
    if (view !== 'lanes') return []
    const s = new Set<string>()
    for (const t of tasks) s.add(laneOf(t))
    for (const extra of extraLanes) if (extra) s.add(extra)
    return orderLanes(Array.from(s), laneOrder)
  }, [tasks, view, extraLanes, laneOrder])
  const moveLane = (lane: string, to: number) => {
    const current = lanes.filter((l) => l !== lane)
    const idx = Math.max(0, Math.min(current.length, to))
    saveLaneOrder([...current.slice(0, idx), lane, ...current.slice(idx)])
  }
  const moveLaneBefore = (lane: string, target: string) => {
    if (lane === target) return
    const current = lanes.filter((l) => l !== lane)
    moveLane(lane, current.indexOf(target))
  }

  // Collapsed lanes — one line each, still a drop target; remembered per project.
  const [collapsedLanes, saveCollapsed] = useKeyedPref(
    `sp-lanes-collapsed:${boardKey}`,
    (k) => new Set(readStrings(k)),
    (k, v) => persistPref(k, JSON.stringify([...v])),
  )
  const toggleLane = (lane: string) => {
    const next = new Set(collapsedLanes)
    if (next.has(lane)) next.delete(lane)
    else next.add(lane)
    saveCollapsed(next)
  }
  const allCollapsed = lanes.length > 0 && lanes.every((l) => collapsedLanes.has(l))
  const collapseAll = () => saveCollapsed(allCollapsed ? new Set() : new Set(lanes))

  // Inline add-lane form state (replaces window.prompt).
  const [addingLane, setAddingLane] = useState(false)
  const [laneDraft, setLaneDraft] = useState('')

  // Rename a lane — cascades to all tasks with that assignee. Optimistic;
  // rolls back and toasts if any persistence call fails.
  const renameLane = async (oldName: string, newName: string) => {
    const clean = newName.trim()
    if (!clean || clean === oldName) return
    const affected = tasks.filter((t) => laneOf(t) === oldName)
    const prevTasks = tasks
    const prevLanes = extraLanes
    // Optimistic update
    setTasks((prev) => prev.map((t) =>
      laneOf(t) === oldName
        ? { ...t, assignee: clean === 'unassigned' ? '' : clean, lane: clean }
        : t
    ))
    // Update the user-added lanes list too
    saveExtraLanes(
      prevLanes
        .map((l) => (l === oldName ? clean : l))
        .concat([clean])
        .filter((l, i, a) => a.indexOf(l) === i && l !== 'unassigned'),
    )
    // Persist each affected task; collect outcomes.
    const results = await Promise.allSettled(
      affected.map((t) =>
        postJson(`/api/tasks/${encodeURIComponent(t.id)}/update`, {
          assignee: clean === 'unassigned' ? '' : clean,
          lane: clean,
          actor: OPERATOR_ACTOR,
        }),
      ),
    )
    const failed = results.filter((r) => r.status === 'rejected').length
    if (failed > 0) {
      // Roll back the optimistic update
      setTasks(putBack(prevTasks, new Set(affected.map((t) => t.id))))
      saveExtraLanes(prevLanes)
      toast.error(t('Couldn\'t rename lane "{name}"', { name: oldName }), {
        description: t('{failed} of {total} task updates failed.', { failed, total: affected.length }),
      })
      return
    }
    setRefreshTick((n) => n + 1)
  }

  // Delete a lane (must be empty; the unassigned bucket is not deletable).
  const deleteLane = (name: string) => {
    if (name === 'unassigned') return
    const inLane = tasks.filter((t) => laneOf(t) === name)
    if (inLane.length > 0) {
      toast.error(t('Cannot delete "{name}"', { name }), {
        description: t('It has {tasks}. Move them first.', { tasks: tn(inLane.length, '{n} task', '{n} tasks') }),
      })
      return
    }
    saveExtraLanes(extraLanes.filter((l) => l !== name))
  }

  const commitAddLane = () => {
    const name = laneDraft.trim()
    setAddingLane(false)
    setLaneDraft('')
    if (!name || lanes.includes(name)) return
    saveExtraLanes([...extraLanes.filter((l) => l !== name), name])
  }

  return {
    lanes, collapsedLanes, toggleLane, allCollapsed, collapseAll,
    addingLane, setAddingLane, laneDraft, setLaneDraft,
    renameLane, deleteLane, commitAddLane, moveLaneBefore,
  }
}
