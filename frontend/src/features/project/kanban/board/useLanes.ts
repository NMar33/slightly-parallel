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
  const { boardLanes, agentLanes } = useMemo(() => {
    const board = new Set([...extraLanes, ...Object.values(savedLanes ?? {}).flat()].filter(Boolean))
    const agent = new Map<string, string[]>()
    const active = new Set(tasks.filter((task) => !task.archived_at).map((task) => laneOf(task).toLowerCase()))
    for (const task of tasks) {
      const lane = laneOf(task)
      if (task.archived_at && active.has(lane.toLowerCase())) continue
      if (task.lane_kind !== 'agent' || !task.project || lane === 'unassigned') {
        board.add(lane)
        continue
      }
      const projects = agent.get(lane) ?? []
      if (!projects.includes(task.project)) agent.set(lane, [...projects, task.project])
    }
    const boardNames = new Set([...board].map((lane) => lane.toLowerCase()))
    for (const lane of agent.keys()) if (boardNames.has(lane.toLowerCase())) agent.delete(lane)
    return { boardLanes: orderLanes([...board], laneOrder), agentLanes: agent }
  }, [tasks, extraLanes, laneOrder, savedLanes])
  const agentOrder = orderLanes([...agentLanes.keys()], laneOrder)
  const lanes = view !== 'lanes' ? [] : agentsOpen ? [...boardLanes, ...agentOrder] : boardLanes

  const promoteLane = async (lane: string) => {
    const projects = agentLanes.get(lane) ?? []
    const outcomes = await Promise.allSettled(projects.map((project) =>
      postJson('/api/tasks/lanes/promote', { project, lane, actor: OPERATOR_ACTOR })))
    if (outcomes.some((outcome) => outcome.status === 'rejected')) {
      toast.error(t('Could not move lane "{name}" to the board', { name: lane }))
    }
    setRefreshTick((tick) => tick + 1)
  }

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
  const allCollapsed = (boardLanes.length > 0 || agentLanes.size > 0)
    && !agentsOpen && boardLanes.every((lane) => collapsedLanes.has(lane))
  const collapseAll = () => {
    saveCollapsed(allCollapsed ? new Set() : new Set(lanes))
    if (agentLanes.size > 0) setAgentsOpen(allCollapsed)
  }

  // Inline add-lane form state (replaces window.prompt).
  const [addingLane, setAddingLane] = useState(false)
  const [laneDraft, setLaneDraft] = useState('')

  const saveLane = async (op: 'add' | 'remove' | 'rename', lane: string, previous?: string) => {
    const targets = op === 'add' ? (project ? [project] : [])
      : Object.keys(savedLanes ?? {}).filter((code) => savedLanes?.[code]?.includes(previous ?? lane))
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
    await saveLane('rename', clean, oldName)
  }

  // Delete a lane (must be empty; the unassigned bucket is not deletable).
  const deleteLane = async (name: string) => {
    if (name === 'unassigned') return
    const inLane = tasks.filter((t) => laneOf(t) === name)
    if (inLane.length > 0) {
      toast.error(t('Cannot delete "{name}"', { name }), {
        description: t('It has {tasks}. Move them first.', { tasks: tn(inLane.length, '{n} task', '{n} tasks') }),
      })
      return
    }
    if (await saveLane('remove', name)) saveExtraLanes(extraLanes.filter((l) => l !== name))
  }

  const commitAddLane = async () => {
    const name = laneDraft.trim()
    setAddingLane(false)
    setLaneDraft('')
    if (!name || name.length > 80 || boardLanes.some((lane) => lane.toLowerCase() === name.toLowerCase())) return
    if (project) await saveLane('add', name)
    else saveExtraLanes([...extraLanes.filter((l) => l !== name), name])
  }

  return {
    lanes, agentLanes, agentsOpen, toggleAgents, promoteLane, collapsedLanes, toggleLane, allCollapsed, collapseAll,
    addingLane, setAddingLane, laneDraft, setLaneDraft,
    renameLane, deleteLane, commitAddLane, moveLaneBefore,
  }
}
