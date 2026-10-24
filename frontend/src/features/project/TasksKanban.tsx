import { useCallback, useEffect, useRef, useState } from 'react'
import { SprintStrip } from './SprintStrip'
import { Storyboard } from './Storyboard'
import { useMarkToggle } from '../../lib/marks'
import { Button, toast } from '../../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { ReleasePromptModal } from './kanban/ReleasePrompt'
import { CarryOverModal } from './kanban/CarryOver'
import { OPERATOR_ACTOR } from './types'
import { fail, postJson } from '../../lib/getJson'
import { SELECTION, glowOf, isToday, normalizeStatus, readModalPrefs } from './kanban/model'
import { useBoardData } from './kanban/boardData'
import { LinksHelp, LinksOverlay } from './kanban/LinksOverlay'
import { TaskAddModal } from './kanban/TaskWindow'
import { stepClash } from './kanban/parts'
import { useEvidenceAsk } from './kanban/board/evidenceAsk'
import { writeOrder } from './kanban/board/model'
import { ColumnSettings, KindPicker, SortedDropDialog } from './kanban/board/dialogs'
import { LanesGrid } from './kanban/board/Lanes'
import { ColumnsGrid } from './kanban/board/Columns'
import type { GridProps } from './kanban/board/types'
import { useLanes } from './kanban/board/useLanes'
import { boardDrops, type PendingDrop } from './kanban/board/drops'
import { boardWrites } from './kanban/board/writes'
import { useDayPlan } from './kanban/board/useDayPlan'
import { useSelection } from './kanban/board/useSelection'
import { useLinking } from './kanban/board/useLinking'
import { useBoardColumns } from './kanban/board/useBoardColumns'
import { DayBar, SelectionBar } from './kanban/board/bars'
import { BoardToolbar, useBoardSwitches } from './kanban/board/Toolbar'
export { stepClash }
// The task window's historical import path.
export { writeOrder }
// The order writer moved to board/model; the tests still import it here.

import type { KanbanBoard, SortMode, TaskRow } from './kanban/model'

// Everything the model and note modules define is still reachable from
// here — the board is the historical import path for the whole feature.
export * from './kanban/model'
export * from './kanban/notes'
import { t } from '../../i18n/scope/project'
import { decodeSafe } from '../../hooks/useHashState'


/**
 * TasksKanban — kanban board with 3 view modes (classic / workflow / lanes)
 * and HTML5 drag-drop. Backed by /api/tasks + /api/tasks/{id}/update.
 *
 * The board's state lives in hooks beside it (kanban/board/): the columns
 * and their remembered choices, the day plan, the selection, linking and
 * the lanes; this file wires them together and draws the toolbar and the
 * windows.
 */
export function TasksKanban({
  projectCode,
  board,
}: {
  projectCode: string
  board?: KanbanBoard
}) {
  const evidenceAsk = useEvidenceAsk()
  // Every per-board memory (view, lanes, order, collapse) keys on this.
  const boardKey = board ? board.id : projectCode
  const boardProjects = board ? board.projects : [projectCode]
  const multi = boardProjects.length > 1
  const sw = useBoardSwitches()
  const { showDesc, copyMode, onlyRemembered, onlyToday } = sw
  // Descriptions are needed both to show them and to copy them.
  const needsBodies = showDesc || copyMode
  // Everything the board reads, from the app's query cache (kanban/boardData):
  // the tasks, and on the cards chat mentions, time in the column (aging),
  // notes, evidence and links. `setTasks` edits the cache optimistically.
  const {
    tasks, setTasks, loading, loadError,
    mentions, statusSince, noteCounts, evidenceCounts, links,
    refresh: refreshBoard, reloadLinks,
  } = useBoardData(boardKey, boardProjects, needsBodies)
  // A reload asked for by a write (`refreshTick`) refetches the board's
  // queries, side by side; the first load is the queries' own. The sprint
  // strip reads the tick too.
  const [refreshTick, setRefreshTick] = useState(0)
  useEffect(() => {
    if (refreshTick > 0) void refreshBoard()
  }, [refreshTick, refreshBoard])
  const bump = () => setRefreshTick((n) => n + 1)
  const { patchMany, setArchived } = boardWrites({ setTasks, bump })

  const [addingStatus, setAddingStatus] = useState<string | null>(null)
  // Lane a cell "+" was pressed in (swim lanes); '' = unassigned, null = none.
  const [addingAssignee, setAddingAssignee] = useState<string | null>(null)
  const [editingTask, setEditingTask] = useState<TaskRow | null>(null)
  const [releaseTask, setReleaseTask] = useState<TaskRow | null>(null)
  // Sprint blocks: filter (sprint id | 'none' | null) — active filter also
  // means new tasks join that sprint.
  const [sprintFilter, setSprintFilter] = useState<string | null>(null)
  const [sprintTick, setSprintTick] = useState(0)
  const assignSprint = async (taskId: string, sprintId: string) => {
    setTasks((cur) => cur.map((t) => (t.id === taskId ? { ...t, sprint_id: sprintId } : t)))
    await postJson(`/api/tasks/${encodeURIComponent(taskId)}/update`, { sprint_id: sprintId, actor: OPERATOR_ACTOR }).catch(fail)
    bump()
    setSprintTick((t) => t + 1)
  }
  // Which value axes the operator wants to see (editor gear); cards follow.
  const [axes, setAxes] = useState(() => readModalPrefs().axes)

  const day = useDayPlan({ tasks, setTasks, patchMany, bump })
  const { today, todayTasks, toggleToday } = day
  const cols = useBoardColumns({
    boardKey, tasks, todayTasks, today, statusSince, sprintFilter, onlyRemembered, onlyToday,
  })
  const { view, setView, sorts, setSort, columns, columnKeyOf, tasksByStatus } = cols
  const sel = useSelection({ tasks, today, columnKeyOf, patchMany, setArchived })
  const lk = useLinking({ links, reloadLinks })
  const { linksMode, linkInfo, linkSource, hoverId, hoverGraph } = lk

  // A drag into a sorted column pauses here for the three-way choice.
  const [pendingDrop, setPendingDrop] = useState<PendingDrop | null>(null)
  /** Write the column's *displayed* (sorted) order into real positions. */
  const commitOrder = async (colKey: string) => {
    const shown = tasksByStatus[colKey] ?? []
    const writes = shown
      .map((t, i) => ({ id: t.id, position: i }))
      .filter((w, i) => Number(shown[i]!.position) !== w.position)
    setTasks((cur) => cur.map((t) => {
      const w = writes.find((x) => x.id === t.id)
      return w ? { ...t, position: w.position } : t
    }))
    const failed = await writeOrder(writes, postJson)
    if (failed) {
      toast.error(t('{failed} of {total} positions didn\'t save', { failed, total: writes.length }))
      bump()
    }
  }

  // Stacks opened by their chip — a queue unfolds in place, like a day.
  const [openStacks, setOpenStacks] = useState<Set<string>>(() => new Set())
  const toggleStack = (sid: string) => setOpenStacks((cur) => {
    const next = new Set(cur)
    if (next.has(sid)) next.delete(sid); else next.add(sid)
    return next
  })

  // The columns' grid: the links layer lives inside it, so lines scroll
  // with the cards instead of being redrawn after them.
  const gridRef = useRef<HTMLDivElement>(null)
  // The ★ on a card is the task's `remember` field, set through the marks
  // API so a star from the chat (#important) and one from here are one.
  const markToggle = useMarkToggle()
  const toggleImportant = (task: TaskRow, next: boolean) => {
    setTasks((cur) => cur.map((t) => (t.id === task.id ? { ...t, remember: next ? 'yes' : '' } : t)))
    markToggle(next, 'task', task.id, { project: task.project })
  }
  /**
   * The cards' handlers, one stable function each. TaskCard is memoized,
   * and a fresh closure per card per render would make every card redraw
   * whenever the board does. The ref carries the latest board state, so
   * the functions themselves never have to change identity.
   */
  const cardOps = useRef({ toggleImportant, toggleToday, targetPicked: lk.targetPicked, tasks })
  cardOps.current = { toggleImportant, toggleToday, targetPicked: lk.targetPicked, tasks }
  const { setHoverId, setLinkSource } = lk
  const onCardHover = useCallback((id: string, on: boolean) => setHoverId(on ? id : null), [setHoverId])
  const onCardArm = useCallback((id: string) => setLinkSource((cur) => (cur === id ? null : id)), [setLinkSource])
  const onCardTarget = useCallback((id: string) => cardOps.current.targetPicked(id), [])
  const onCardOpen = useCallback((id: string) => {
    const t = cardOps.current.tasks.find((x) => x.id === id)
    if (t) setEditingTask(t)
  }, [])
  const onCardEdit = useCallback((t: TaskRow) => setEditingTask(t), [])
  const onCardRelease = useCallback((t: TaskRow) => setReleaseTask(t), [])
  const onCardToday = useCallback((t: TaskRow) => { void cardOps.current.toggleToday(t) }, [])
  const onCardImportant = useCallback((t: TaskRow, next: boolean) => cardOps.current.toggleImportant(t, next), [])
  /** The wiring every render of a card gets — home card, stack queue,
   *  archive, today copy — so they all hover, light, link and star alike.
   *  Every handler is one of the stable per-board functions (the card says
   *  which task it is), and hover is wired only where it can light
   *  something: links mode on and the card actually linked — so resting
   *  the mouse on an ordinary card re-renders nothing. `shadow` marks the
   *  today copy: it lights up but lines stay on the home card. */
  const linkProps = (task: TaskRow, shadow = false) => ({
    onImportant: onCardImportant,
    link: linkInfo[task.id],
    linksMode,
    armed: linkSource === task.id,
    glow: glowOf(hoverGraph, hoverId, task.id),
    shadow,
    onHover: linksMode && linkInfo[task.id]?.n ? onCardHover : undefined,
    onArm: onCardArm,
    onTarget: linkSource && linkSource !== task.id ? onCardTarget : undefined,
    onOpenTask: onCardOpen,
  })
  const linksLayer = linksMode ? (
    <LinksOverlay
      containerRef={gridRef}
      links={links}
      hoverId={hoverId}
      graph={hoverGraph}
      onDelete={lk.deleteLink}
      onUpdate={lk.updateLink}
      onOpenTask={(id) => { const t = tasks.find((x) => x.id === id); if (t) setEditingTask(t) }}
    />
  ) : null

  // A link may name a task (`#tasks&task=tk_…`, search results do): open its
  // window once the tasks are in, then drop the parameter so a reload does
  // not reopen it.
  const deepLinked = useRef(false)
  useEffect(() => {
    if (deepLinked.current || loading) return
    deepLinked.current = true
    const wanted = /(?:^|&)task=([^&]+)/.exec(window.location.hash)?.[1]
    const hit = wanted ? tasks.find((t) => t.id === decodeSafe(wanted)) : undefined
    if (hit) {
      setEditingTask(hit)
      const url = new URL(window.location.href)
      url.hash = url.hash.replace(/&task=[^&]+/, '')
      window.history.replaceState(window.history.state, '', url.toString())
    }
  }, [loading, tasks])

  const [colSettings, setColSettings] = useState(false)

  // Swim lanes: their state and operations live in board/useLanes.
  const {
    lanes, collapsedLanes, toggleLane, allCollapsed, collapseAll,
    addingLane, setAddingLane, laneDraft, setLaneDraft,
    renameLane, deleteLane, commitAddLane, moveLaneBefore,
  } = useLanes({ boardKey, view, tasks, setTasks, setRefreshTick })

  // Drops — a card, a batch, the selection, the archive (board/drops).
  const { handleDrop } = boardDrops({
    tasks, setTasks, columnKeyOf, today, sorts, setPendingDrop, setArchived, moveSelection: sel.moveSelection, setRefreshTick,
  })
  /** Dropping into a Today cell means: go to that column, and plan it today. */
  const handleDropToday = (draggedId: string, colKey: string, lane?: string) => {
    if (draggedId === SELECTION) {
      const rows = sel.selectedTasks.map((t) => ({ id: t.id, patch: { today_on: today } }))
      void sel.moveSelection(colKey, lane).then(() => patchMany(rows))
      return
    }
    const t = tasks.find((x) => x.id === draggedId)
    handleDrop(draggedId, colKey, lane)
    if (t && !isToday(t, today)) void toggleToday(t)
  }

  /** What both grids draw from — the board owns it all, they only render it. */
  const gridProps: GridProps = {
    gridRef, columns, openStrips: cols.openStrips, showArchiveCol: cols.showArchiveCol, showArchived: cols.showArchived,
    tasksByStatus, toggleStrip: cols.toggleStrip,
    handleDrop, copyMode, sorts, setSort, setAddingStatus, archivedN: cols.archivedN, toggleArchived: cols.toggleArchived, todayTasks,
    byLaneCol: cols.byLaneCol, handleDropToday, toggleToday, linkProps, multi, axes, onCardToday, onCardEdit,
    onCardRelease, showDesc, today, selection: sel.selection, toggleSelect: sel.toggleSelect, tasks, openStacks, toggleStack,
    mentions, noteCounts, evidenceCounts, statusSince, archivedTasks: cols.archivedTasks, linksLayer,
  }

  if (loading) return <LoadingSkeleton variant="card" count={3} label={t('Loading tasks')} />

  return (
    <div className="flex flex-col gap-12">
      {loadError && (
        <ErrorBanner
          title={t('Could not load tasks')}
          message={loadError}
          onRetry={bump}
        />
      )}

      <SprintStrip
        projects={boardProjects}
        filter={sprintFilter}
        onFilter={setSprintFilter}
        onAssignTask={(taskId, sprintId) => void assignSprint(taskId, sprintId)}
        tick={refreshTick + sprintTick}
      />

      <BoardToolbar
        sw={sw} linksMode={linksMode} toggleLinks={lk.toggleLinks}
        tasksN={tasks.length} todayN={todayTasks.length} projectCode={projectCode}
        view={view} onView={setView} onColumns={() => setColSettings(true)}
      />

      {/* Board */}
      <div className="relative" onMouseLeave={() => setHoverId(null)}>
      {linksMode && linkSource && (
        <div className="mb-6 text-11 font-mono text-brand flex items-center gap-8">
          {t('linking from')} <span className="text-primary">{tasks.find((t) => t.id === linkSource)?.title ?? linkSource}</span> {t('— click the other card')}
          <Button variant="text" size="bare" onClick={() => setLinkSource(null)}>{t('cancel')}</Button>
        </div>
      )}
      <SelectionBar sel={sel} evidenceAsk={evidenceAsk} />
      <DayBar day={day} />
      {view === 'lanes' ? (
        <div className="overflow-x-auto">
          <LanesGrid {...gridProps}
            lanes={lanes} collapsedLanes={collapsedLanes} toggleLane={toggleLane}
            renameLane={renameLane} deleteLane={deleteLane} moveLaneBefore={moveLaneBefore}
            allCollapsed={allCollapsed} collapseAll={collapseAll}
            addingLane={addingLane} setAddingLane={setAddingLane}
            laneDraft={laneDraft} setLaneDraft={setLaneDraft} commitAddLane={commitAddLane}
            setAddingAssignee={setAddingAssignee}
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <ColumnsGrid {...gridProps} doneLimit={cols.doneLimit} doneExpanded={cols.doneExpanded} setDoneExpanded={cols.setDoneExpanded} />
        </div>
      )}

      {lk.linksHelp && <LinksHelp onClose={() => lk.setLinksHelp(false)} />}
      <Storyboard projects={boardProjects} boardKey={boardKey} />
      {colSettings && (
        <ColumnSettings
          columns={cols.allColumns}
          hidden={cols.hiddenCols}
          counts={(() => {
            const c: Record<string, number> = {}
            for (const t of tasks) {
              if (t.archived_at) { c.__archive__ = (c.__archive__ ?? 0) + 1; continue }
              const k = normalizeStatus(t.status)
              c[k] = (c[k] ?? 0) + 1
            }
            return c
          })()}
          onToggle={(key, hide) => cols.setColHidden(key, hide)}
          onClose={() => setColSettings(false)}
        />
      )}
      {pendingDrop && (
        <SortedDropDialog
          mode={(sorts[pendingDrop.targetStatus] ?? 'manual') as SortMode}
          column={columns.find((c) => c.key === pendingDrop.targetStatus)?.label ?? pendingDrop.targetStatus}
          onManual={() => {
            // Back to the hand-made order; the drag is discarded on purpose.
            setSort(pendingDrop.targetStatus, 'manual')
            setPendingDrop(null)
          }}
          onAdopt={() => {
            const d = pendingDrop
            setPendingDrop(null)
            void commitOrder(d.targetStatus).then(() => {
              setSort(d.targetStatus, 'manual')
              handleDrop(d.draggedId, d.targetStatus, d.targetLane, d.beforeTaskId, true)
            })
          }}
          onCancel={() => setPendingDrop(null)}
        />
      )}
      {lk.pendingLink && (
        <KindPicker
          from={tasks.find((t) => t.id === lk.pendingLink?.from)}
          to={tasks.find((t) => t.id === lk.pendingLink?.to)}
          onPick={(kind) => { const p = lk.pendingLink; if (p) void lk.createLink(p.from, p.to, kind) }}
          onCancel={() => lk.setPendingLink(null)}
        />
      )}
      </div>

      {/* The press-release window lives here, not in the card: cards
          re-render under the board's polling. */}
      {releaseTask && <ReleasePromptModal task={releaseTask} onClose={() => setReleaseTask(null)} />}
      {day.carryOpen && day.leftover.length > 0 && (
        <CarryOverModal rows={day.leftover} today={today} onCarry={(c, l) => void day.carryOver(c, l)} onClose={day.closeCarry} />
      )}

      {/* Add / edit task popup modal */}
      {(addingStatus || editingTask) && (
        <TaskAddModal
          projectCode={projectCode}
          boardProjects={boardProjects}
          initialSprint={sprintFilter && sprintFilter !== 'none' ? sprintFilter : undefined}
          initialStatus={addingStatus || editingTask?.status || 'unclassified'}
          initialAssignee={addingAssignee ?? undefined}
          existingTask={editingTask}
          onClose={() => {
            setAddingStatus(null)
            setAddingAssignee(null)
            setEditingTask(null)
            setAxes(readModalPrefs().axes)
          }}
          onSaved={(o) => {
            // ▶ keeps the window open for the next task — only refresh.
            if (!o?.keepOpen) {
              setAddingStatus(null)
              setAddingAssignee(null)
              setEditingTask(null)
            }
            setAxes(readModalPrefs().axes)
            setRefreshTick((t) => t + 1)
          }}
          onLinksChanged={() => void reloadLinks()}
          onOpenOther={(id) => {
            const t = tasks.find((x) => x.id === id)
            if (t) { setAddingStatus(null); setEditingTask(t) }
          }}
          onRelease={(t) => {
            // One window at a time: the release window takes the editor's place.
            setAddingStatus(null)
            setAddingAssignee(null)
            setEditingTask(null)
            setReleaseTask(t)
          }}
        />
      )}
    </div>
  )
}
