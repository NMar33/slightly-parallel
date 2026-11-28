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
import { laneKey, taskLaneName, taskLaneKey } from '../model'
import type { BoardLane, KanbanView, TaskRow } from '../model'
import { putBack } from '../boardData'
import { t, tn } from '../../../../i18n/scope/project'

export function useLanes({
  boardKey, view, tasks, setTasks, setRefreshTick, savedLanes, project,
}: {
  boardKey: string
  project?: string
  savedLanes?: Record<string, string[]>
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
  const [agentsOpen, setAgentsOpen] = useKeyedPref(
    `sp-lanes-agents:${boardKey}`, (key) => readStrings(key).includes('open'),
    (key, open) => persistPref(key, open ? '["open"]' : '[]'),
  )
  const toggleAgents = () => setAgentsOpen(!agentsOpen)
  const primary = project ?? ''
  const storedKey = (key: string) => key.includes('\n') ? key : laneKey(primary, key === 'unassigned' ? '' : key)
  const orderedKeys = laneOrder.map(storedKey)
  const laneRows = useMemo(() => {
    const rows = new Map<string, BoardLane>()
    const active = new Set(tasks.filter((task) => !task.archived_at).map(taskLaneKey))
    for (const task of tasks) {
      const key = taskLaneKey(task)
      if (task.archived_at && active.has(key)) continue
      const name = taskLaneName(task)
      const agent = task.lane_kind === 'agent' && !!name
      const previous = rows.get(key)
      if (!previous || (agent && !previous.agent)) rows.set(key, { key, name, project: task.project ?? '', agent })
    }
    const addBoardLane = (code: string, name: string) => {
      if (!name) return
      const key = laneKey(code, name)
      rows.set(key, { key, name, project: code, agent: false })
    }
    if (savedLanes?.[primary] === undefined) {
      for (const name of extraLanes) addBoardLane(primary, name)
    }
    for (const [code, names] of Object.entries(savedLanes ?? {})) {
      for (const name of names) addBoardLane(code, name)
    }
    return [...rows.values()]
  }, [tasks, extraLanes, primary, savedLanes])
  const compare = (a: BoardLane, b: BoardLane) => {
    const aIndex = orderedKeys.indexOf(a.key)
    const bIndex = orderedKeys.indexOf(b.key)
    if (aIndex !== -1 || bIndex !== -1) {
      return (aIndex === -1 ? orderedKeys.length : aIndex) - (bIndex === -1 ? orderedKeys.length : bIndex)
    }
    const unassigned = Number(!a.name) - Number(!b.name)
    return unassigned || a.name.localeCompare(b.name) || a.project.localeCompare(b.project)
  }
  const boardLanes = laneRows.filter((lane) => !lane.agent).sort(compare)
  const agentLanes = laneRows.filter((lane) => lane.agent).sort(compare)
  const lanes = view !== 'lanes' ? [] : agentsOpen ? [...boardLanes, ...agentLanes] : boardLanes

  const promoteLane = async (lane: BoardLane) => {
    try {
      await postJson('/api/tasks/lanes/promote', { project: lane.project, lane: lane.name, actor: OPERATOR_ACTOR })
    } catch {
      toast.error(t('Could not move lane "{name}" to the board', { name: lane.name }))
    }
    setRefreshTick((tick) => tick + 1)
  }

  const moveLaneBefore = (key: string, target: string) => {
    if (key === target) return
    const current = lanes.map((lane) => lane.key).filter((lane) => lane !== key)
    const index = current.indexOf(target)
    if (index !== -1) saveLaneOrder([...current.slice(0, index), key, ...current.slice(index)])
  }

  // Collapsed lanes are remembered by project and spelling-independent name.
  const [storedCollapsed, saveCollapsed] = useKeyedPref(
    `sp-lanes-collapsed:${boardKey}`,
    readStrings,
  )
  const collapsedLanes = new Set(storedCollapsed.map(storedKey))
  const toggleLane = (key: string) => {
    const next = new Set(collapsedLanes)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    saveCollapsed([...next])
  }
  const allCollapsed = laneRows.length > 0
    && !agentsOpen && boardLanes.every((lane) => collapsedLanes.has(lane.key))
  const collapseAll = () => {
    saveCollapsed(allCollapsed ? [] : lanes.map((lane) => lane.key))
    if (agentLanes.length > 0) setAgentsOpen(allCollapsed)
  }

  // Inline add-lane form state (replaces window.prompt).
  const [addingLane, setAddingLane] = useState(false)
  const [laneDraft, setLaneDraft] = useState('')

  const saveLane = async (op: 'add' | 'remove' | 'rename', code: string, lane: string, previous?: string) => {
    const registered = savedLanes?.[code]?.some((name) => laneKey(code, name) === laneKey(code, previous ?? lane))
    const targets = code && (op === 'add' || registered) ? [code] : []
    const results = await Promise.allSettled(targets.map((code) =>
      postJson('/api/tasks/lanes', { op, lane, previous, project: code, actor: OPERATOR_ACTOR })))
    if (results.some((result) => result.status === 'rejected')) {
      toast.error(t('Could not save lane "{name}"', { name: lane }))
    }
    setRefreshTick((tick) => tick + 1)
    return results.every((result) => result.status === 'fulfilled')
  }

  // Rename a lane — cascades to all tasks with that assignee. Optimistic;
  // rolls back and toasts if any persistence call fails.
  const renameLane = async (lane: BoardLane, newName: string) => {
    const { name: oldName, key } = lane
    const clean = newName.trim()
    if (!clean || clean === oldName) return
    const affected = tasks.filter((t) => taskLaneKey(t) === key)
    const prevTasks = tasks
    const prevLanes = extraLanes
    // Optimistic update
    setTasks((prev) => prev.map((t) =>
      taskLaneKey(t) === key
        ? { ...t, assignee: clean, lane: clean }
        : t
    ))
    // Update the user-added lanes list too
    if (lane.project === primary) {
      saveExtraLanes(prevLanes.map((name) => laneKey(primary, name) === key ? clean : name))
    }
    // Persist each affected task; collect outcomes.
    const results = await Promise.allSettled(
      affected.map((t) =>
        postJson(`/api/tasks/${encodeURIComponent(t.id)}/update`, {
          assignee: clean,
          lane: clean,
          actor: OPERATOR_ACTOR,
        }),
      ),
    )
    const failed = results.filter((r) => r.status === 'rejected').length
    if (failed > 0) {
      // Put back only the cards that did not save: the saved ones carry the
      // new name on the server, and showing them under the old one was wrong
      // until the next refresh.
      const lost = new Set(affected.filter((_, i) => results[i]!.status === 'rejected').map((t) => t.id))
      setTasks(putBack(prevTasks, lost))
      if (lost.size === affected.length) saveExtraLanes(prevLanes)
      toast.error(t('Couldn\'t rename lane "{name}"', { name: oldName }), {
        description: t('{failed} of {total} task updates failed.', { failed, total: affected.length }),
      })
      return
    }
    await saveLane('rename', lane.project, clean, oldName)
  }

  // Delete a lane (must be empty; the unassigned bucket is not deletable).
  const deleteLane = async ({ name, project: code, key }: BoardLane) => {
    if (!name) return
    const inLane = tasks.filter((t) => taskLaneKey(t) === key)
    if (inLane.length > 0) {
      toast.error(t('Cannot delete "{name}"', { name }), {
        description: t('It has {tasks}. Move them first.', { tasks: tn(inLane.length, '{n} task', '{n} tasks') }),
      })
      return
    }
    if (await saveLane('remove', code, name) && code === primary) {
      saveExtraLanes(extraLanes.filter((candidate) => laneKey(primary, candidate) !== key))
    }
  }

  const commitAddLane = async () => {
    const name = laneDraft.trim()
    setAddingLane(false)
    setLaneDraft('')
    if (!name || name.length > 80 || boardLanes.some((lane) => lane.key === laneKey(primary, name))) return
    if (project) await saveLane('add', project, name)
    else saveExtraLanes([...extraLanes.filter((l) => l !== name), name])
  }

  return {
    lanes, agentLanes, agentsOpen, toggleAgents, promoteLane, collapsedLanes, toggleLane, allCollapsed, collapseAll,
    addingLane, setAddingLane, laneDraft, setLaneDraft,
    renameLane, deleteLane, commitAddLane, moveLaneBefore,
  }
}
