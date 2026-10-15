import { hm } from '../../utils/format'
import { LoadingSkeleton } from '../../components/states'
import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { postJson } from '../../lib/getJson'
import { toast } from 'sonner'

import { persistPref, readPref } from '../../lib/uiPrefs'
import { nowStamp, OPERATOR_ACTOR } from './types'
import { Segmented } from '../../components/Segmented'
import { TaskAddModal } from './kanban/TaskWindow'
import { projectTasksKey, sprintBoardKey, useProjectTasks, useSprintBoard } from '../tasks/data'
import type { TaskRow } from './kanban/model'
import { NewSprint } from './SprintParts'
import { CalcExplainer, RadarPanel } from './SprintRadar'
import { RunwayView } from './SprintRunway'
import { BlocksView } from './SprintBlocks'
import { groupOf, type SprintRow } from './sprintsModel'
import { t } from '../../i18n/scope/project'

/**
 * SprintsPanel — the project page's Sprints section, on real data.
 *
 * Two views, complementary and switchable: RUNWAY answers "when" — every block a bar on one time axis
 * with a today-line, task ticks and a red hatched overhang past the bet;
 * BLOCKS answers "what" — a board whose columns are the blocks themselves
 * (plus backlog), tasks moving between them with one click.
 *
 * A sprint is a block of work with two limits (a bet in days, a human-hours
 * budget) and only derived numbers: tasks done/total, days left, timer
 * hours × share, agent hours from captured sessions that mentioned the
 * block's tasks. Three in parallel at most; ending one requires the retro.
 */

type View = 'runway' | 'blocks'

const VIEW_KEY = (p: string) => `sp-sprints-view:${p}`
const readView = (p: string): View => (readPref(VIEW_KEY(p)) === 'blocks' ? 'blocks' : 'runway')

/** The view picked for this project; another project reads its own. */
function useSprintsView(projectCode: string): [View, (v: View) => void] {
  const [held, setHeld] = useState(() => ({ project: projectCode, view: readView(projectCode) }))
  const view = held.project === projectCode ? held.view : readView(projectCode)
  if (held.project !== projectCode) setHeld({ project: projectCode, view })
  const pick = (v: View) => { setHeld({ project: projectCode, view: v }); persistPref(VIEW_KEY(projectCode), v) }
  return [view, pick]
}

/**
 * The project's running blocks and tasks, and the writes on them. Through
 * the query cache: the freshness stamp (area "tasks") brings in what agents
 * write, and the tasks are the same read every other panel of the project
 * uses. A write updates the cached tasks at once, then reads both again —
 * a refused write comes back as the server has it.
 */
function useSprintWork(projectCode: string) {
  const qc = useQueryClient()
  const board = useSprintBoard(projectCode)
  const taskList = useProjectTasks(projectCode)
  // Null while the first read is out; a read that failed shows as none.
  const sprints: SprintRow[] | null = board.data ?? (board.isError ? [] : null)
  const tasks = useMemo(() => (taskList.data ?? []).filter((t) => !t.archived_at), [taskList.data])
  const setTasks = useCallback((u: (cur: TaskRow[]) => TaskRow[]) => {
    // A refetch on its way left before this edit: dropped, so it cannot undo it.
    void qc.cancelQueries({ queryKey: projectTasksKey(projectCode) })
    qc.setQueryData<TaskRow[]>(projectTasksKey(projectCode), (cur) => u(cur ?? []))
  }, [qc, projectCode])
  const refresh = useCallback(() => {
    void qc.invalidateQueries({ queryKey: sprintBoardKey(projectCode) })
    void qc.invalidateQueries({ queryKey: projectTasksKey(projectCode) })
  }, [qc, projectCode])

  const tasksOf = (sprintId: string | null) =>
    tasks.filter((t) => (sprintId === null ? !(t.sprint_id ?? '') : t.sprint_id === sprintId))

  const backlog = tasksOf(null)
    .filter((t) => groupOf(t.status) !== 'done')
    .map((t) => ({ id: t.id, title: String(t.title ?? '') }))

  // -- real mutations ------------------------------------------------------
  const post = async (url: string, body?: unknown): Promise<boolean> => {
    try {
      await postJson(url, body)
      return true
    } catch (e) {
      // The server's own sentence, not a bare 'did not save'.
      toast.error(t('The change did not save: {reason}', { reason: (e as Error).message }))
      return false
    }
  }
  const assignMany = async (taskIds: string[], sprintId: string) => {
    setTasks((cur) => cur.map((x) => (taskIds.includes(x.id) ? { ...x, sprint_id: sprintId } : x)))
    const results = await Promise.all(taskIds.map((id) =>
      postJson(`/api/tasks/${encodeURIComponent(id)}/update`, { sprint_id: sprintId, actor: OPERATOR_ACTOR })
        .then(() => true, () => false),
    ))
    if (results.some((ok) => !ok)) toast.error(t('Some tasks could not be moved'))
    refresh()
  }
  const assign = async (taskId: string, sprintId: string) => {
    setTasks((cur) => cur.map((x) => (x.id === taskId ? { ...x, sprint_id: sprintId } : x)))
    await post(`/api/tasks/${encodeURIComponent(taskId)}/update`, { sprint_id: sprintId, actor: OPERATOR_ACTOR })
    refresh()
  }
  const addTask = async (sprintId: string | null, title: string) => {
    const { dateStr, timeStr } = nowStamp()
    await post('/api/tasks', {
      project: projectCode, agent_id: OPERATOR_ACTOR, created_date: dateStr, created_time: timeStr,
      title, status: 'todo', sprint_id: sprintId ?? '', position: '999',
    })
    refresh()
  }
  const endSprint = async (s: SprintRow, retro: string) => {
    const { dateStr } = nowStamp()
    const over = s.days_left != null && s.days_left < 0 ? `ran ${-s.days_left}d over` : t('in time')
    const facts = `planned ${s.bet_days ?? '—'}d, ${over} · done ${s.tasks_done}/${s.tasks_total} · ${hm(s.human_min)} human${s.budget_h ? ` of ${s.budget_h}h` : ''} · ${hm(s.agent_min)} agent`
    await post(`/api/sprints/${encodeURIComponent(s.id)}/update`, {
      status: 'ended', ended_date: dateStr, goals_shipped_n: s.tasks_done, l2: `${facts}\n\n${retro}`,
    })
    refresh()
  }

  return { sprints, tasksOf, backlog, refresh, assign, assignMany, addTask, endSprint }
}

export function SprintsPanel({ projectCode }: { projectCode: string }) {
  const [view, pickView] = useSprintsView(projectCode)
  const { sprints, tasksOf, backlog, refresh, assign, assignMany, addTask, endSprint } = useSprintWork(projectCode)
  // Clicking a task opens it — the full editor, not a status shortcut.
  const [editing, setEditing] = useState<TaskRow | null>(null)

  if (sprints === null) {
    return <LoadingSkeleton variant="text" count={3} label={t('Loading sprints')} className="py-12" />
  }

  return (
    <div className="flex flex-col gap-12">
      <div className="flex items-center gap-8 flex-wrap">
        <h2 className="text-16 font-semibold text-primary">{t('Sprints')}</h2>
        <span className="text-11 font-mono text-tertiary">{t('Blocks of work with planned days and an hour budget, three at most')}</span>
        <Segmented label={t('Sprints view')} shape="pill" value={view} onChange={pickView} className="ml-auto"
          options={(['runway', 'blocks'] as View[]).map((v) => [v, v] as const)} />
      </div>

      {sprints.length === 0 ? (
        <div className="rounded-card border border-dashed border-border-default px-16 py-14 flex items-center gap-12">
          <span className="text-12 text-tertiary">{t('No blocks running.')}</span>
          <NewSprint projectCode={projectCode} active={[]} backlog={backlog} onStarted={refresh} />
        </div>
      ) : view === 'runway' ? (
        <>
          <RunwayView sprints={sprints} tasksOf={tasksOf} onOpen={setEditing} onEnd={endSprint} onMoveMany={assignMany} onSprintChanged={refresh}
            newSprint={<NewSprint projectCode={projectCode} active={sprints} backlog={backlog} onStarted={refresh} />} />
          {/* The pairing: the runway says when, the radar says how healthy. */}
          <RadarPanel sprints={sprints} />
        </>
      ) : (
        <BlocksView sprints={sprints} tasksOf={tasksOf} onOpen={setEditing} onAssign={assign} onAssignMany={assignMany} onAdd={addTask} onEnd={endSprint} onMoveMany={assignMany} onSprintChanged={refresh} openKey={`sp-sprints-open:${projectCode}`}
          newSprint={<NewSprint projectCode={projectCode} active={sprints} backlog={backlog} onStarted={refresh} />} />
      )}
      <CalcExplainer sprints={sprints} />
      {editing && (
        <TaskAddModal
          projectCode={projectCode}
          initialStatus={editing.status || 'todo'}
          existingTask={editing as never}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); refresh() }}
        />
      )}
    </div>
  )
}
