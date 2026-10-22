/**
 * The swim-lane view: the lane label in the gutter (rename, delete, fold,
 * drag to reorder) and the lane × column grid the board renders.
 */

import { Fragment, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown } from 'lucide-react'
import { Button } from '../../../../components/primitives'
import { LABEL } from '../../../promptlib/taskstyle'
import { STRIP_TONES, bulkPayload, foldStacks, isToday, laneOf } from '../model'
import type { SortMode } from '../model'
import { TaskCard, StackWrap, TodayShadow } from './Card'
import { BatchTools, SortMenu } from './controls'
import { KanbanColumnDropZone, TaskDropSlot } from './drag'
import { FoldCell, FoldHeader } from './folds'
import { ARCHIVE, EMPTY_ROWS } from './model'
import type { LanesGridProps } from './types'
import { t } from '../../../../i18n/scope/project'

/**
 * LaneLabel — swim-lane row header with inline rename + delete affordances.
 * Click the text to edit inline; Escape cancels; Enter saves.
 * Delete is disabled while the lane has tasks.
 */
const LANE_DRAG = '__sp_lane__:'

/**
 * A lane name in an 88px gutter. The rows are tall — a lane holds cards —
 * so the height is there to be used: the name wraps between words, and
 * the only thing that ever gets cut is a single word too long for the
 * column. Each word is its own box, so the ellipsis lands on that word
 * instead of on the whole name.
 */
function LaneName({ name }: { name: string }) {
  const words = name.split(/\s+/).filter(Boolean)
  return (
    <span className="flex flex-wrap items-baseline gap-x-4 leading-tight">
      {words.map((w, i) => (
        <span key={`${i}:${w}`} className="max-w-full truncate">{w}</span>
      ))}
    </span>
  )
}

function LaneLabel({
  name, count, collapsed, onToggle, onRename, onDelete, onDropLane,
}: {
  name: string
  count: number
  collapsed: boolean
  onToggle: () => void
  onRename: (next: string) => void
  onDelete: () => void
  onDropLane: (draggedLane: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name)
  const [over, setOver] = useState(false)
  useEffect(() => { setDraft(name) }, [name])

  const commit = () => {
    setEditing(false)
    if (draft.trim() && draft.trim() !== name) onRename(draft.trim())
  }

  /** The count and the delete affordance — they follow the name or the fold. */
  const meta = (
    <>
      <span className="text-tertiary opacity-70">{count}</span>
      {name !== 'unassigned' && (
        <button
          type="button"
          onClick={onDelete}
          className={`opacity-0 group-hover:opacity-100 transition-opacity text-tertiary hover:text-error ${count > 0 ? 'cursor-not-allowed opacity-30!' : ''}`}
          title={count > 0 ? `${count} tasks. Move them first.` : t('Delete lane')}
          disabled={count > 0}
        >
          ×
        </button>
      )}
    </>
  )

  const fold = (
    <button
      type="button"
      onClick={onToggle}
      className={`inline-flex items-center gap-2 text-tertiary hover:text-primary normal-case tracking-normal ${collapsed ? 'shrink-0' : ''}`}
      aria-expanded={!collapsed}
      aria-label={collapsed ? `Expand lane ${name}` : `Collapse lane ${name}`}
      title={collapsed ? t('Expand lane') : t('Collapse lane')}
    >
      {collapsed ? <ChevronRight size={11} aria-hidden /> : <ChevronDown size={11} aria-hidden />}
    </button>
  )

  return (
    <div
      draggable={!editing}
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', LANE_DRAG + name)
        e.dataTransfer.effectAllowed = 'move'
      }}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('text/plain')) return
        e.preventDefault()
        if (!over) setOver(true)
      }}
      onDragLeave={(e) => {
        if (e.currentTarget.contains(e.relatedTarget as Node)) return
        setOver(false)
      }}
      onDrop={(e) => {
        setOver(false)
        const raw = e.dataTransfer.getData('text/plain')
        if (!raw.startsWith(LANE_DRAG)) return  // a task drop bubbles to its cell
        e.preventDefault()
        e.stopPropagation()
        onDropLane(raw.slice(LANE_DRAG.length))
      }}
      title={t('Drag to reorder lanes')}
      className={`${LABEL} px-4 border-r border-border-subtle group flex cursor-grab active:cursor-grabbing ${collapsed ? 'items-center gap-4 h-24' : 'flex-col justify-start gap-2 py-4'} ${over ? 'border-t-2 border-t-brand' : ''}`}
    >
    <div className="flex items-baseline gap-4 w-full min-w-0">
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit()
            if (e.key === 'Escape') { setDraft(name); setEditing(false) }
          }}
          className="bg-elevated text-primary border border-brand rounded-input px-4 py-1 text-11 font-mono w-full"
        />
      ) : (
        <>
          <button
            type="button"
            onClick={() => setEditing(true)}
            className={`text-left flex-1 min-w-0 hover:text-primary ${collapsed ? 'truncate' : ''}`}
            title={t('{name} · click to rename', { name })}
          >
            {/* Folded, the lane is one 24px line: the name stays on it and
                takes an ellipsis. Open, it may use as many lines as it needs. */}
            {collapsed ? name : <LaneName name={name} />}
          </button>
          {collapsed && meta}
        </>
      )}
    </div>
    {/* Open, the name owns the whole gutter and the numbers move down here
        beside the fold control; folded, everything sits on the one line. */}
    {collapsed ? fold : (
      <div className="flex items-center gap-4 self-start">
        {fold}
        {meta}
      </div>
    )}
    </div>
  )
}

/**
 * The swim-lane view: column headers, the Today band, one row per lane and
 * the add-lane form, on one grid that also carries the links layer.
 */
export function LanesGrid(props: LanesGridProps) {
  const {
    gridRef, columns, openStrips, showArchiveCol, showArchived, tasksByStatus, toggleStrip,
    handleDrop, copyMode, sorts, setSort, setAddingStatus, archivedN, toggleArchived, todayTasks,
    byLaneCol, handleDropToday, toggleToday, linkProps, multi, axes, onCardToday, onCardEdit,
    onCardRelease, showDesc, today, selection, toggleSelect, tasks, openStacks, toggleStack,
    mentions, noteCounts, evidenceCounts, statusSince, archivedTasks, linksLayer, lanes,
    collapsedLanes, toggleLane, renameLane, deleteLane, moveLaneBefore, allCollapsed, collapseAll,
    addingLane, setAddingLane, laneDraft, setLaneDraft, commitAddLane, setAddingAssignee,
  } = props
  return (
    <div ref={gridRef}
      className="relative grid gap-4"
      style={{
        gridTemplateColumns: `88px ${columns.map((c) => (c.strip && !openStrips[c.key] ? '28px' : 'minmax(180px, 1fr)')).join(' ')}${showArchiveCol ? (showArchived ? ' minmax(180px, 1fr)' : ' 28px') : ''}`,
        minWidth: `${88 + columns.reduce((w, c) => w + (c.strip && !openStrips[c.key] ? 32 : 200), 0) + (showArchiveCol ? (showArchived ? 200 : 32) : 0)}px`,
      }}
    >
      {/* Column headers — the corner cell folds or unfolds every lane */}
      <div className="flex items-end pb-4 px-4">
        <Button
          variant="text"
          size="bare"
          onClick={collapseAll}
          title={allCollapsed ? t('Expand all lanes') : t('Collapse all lanes')}
          aria-label={allCollapsed ? t('Expand all lanes') : t('Collapse all lanes')}
        >
          {allCollapsed ? <ChevronsUpDown size={12} aria-hidden /> : <ChevronsDownUp size={12} aria-hidden />}
          {allCollapsed ? t('expand') : t('collapse')}
        </Button>
      </div>
      {columns.map((col) => (
        col.strip ? (
          <FoldHeader
            key={col.key}
            label={col.label}
            n={(tasksByStatus[col.key] ?? []).length}
            open={!!openStrips[col.key]}
            onToggle={() => toggleStrip(col.key)}
            tone={STRIP_TONES[col.key]}
          />
        ) : (
        /* Dropping on the header moves cards to this column and
           leaves each one in the lane it was already in — the cells
           below can only ever mean "this column *and* this lane". */
        <KanbanColumnDropZone
          key={col.key}
          onDropTask={(id) => handleDrop(id, col.key)}
          className={`text-11 uppercase tracking-wide font-mono px-6 pb-4 border-b-2 border-border-default ${col.className === 'state-doing' ? '!border-b-brand' : col.className === 'state-done' ? '!border-b-status-green' : col.className === 'state-review' ? '!border-b-status-purple' : col.className === 'state-todo' ? '!border-b-status-amber' : ''} flex items-baseline gap-6`}
          title={`Drop here to move cards to ${col.label} in their own lanes`}
          hint={t('keeps lanes')}
        >
          <span>{col.label}</span>
          <span className="text-tertiary">
            {(tasksByStatus[col.key] ?? []).length}
          </span>
          {copyMode && (tasksByStatus[col.key] ?? []).length > 0 && (
            <BatchTools
              items={tasksByStatus[col.key] ?? []}
              label={t('{column} (every lane)', { column: col.label })}
              dragPayload={bulkPayload(col.key)}
            />
          )}
          <span className="ml-auto inline-flex items-center gap-2">
            <SortMenu mode={(sorts[col.key] ?? 'manual') as SortMode} onPick={(m) => setSort(col.key, m)} />
            <button
              type="button"
              onClick={() => setAddingStatus(col.key)}
              className="text-11 text-brand hover:text-brand-hover font-mono"
              aria-label={`Add task to ${col.label}`}
            >
              +
            </button>
          </span>
        </KanbanColumnDropZone>
        )
      ))}
      {showArchiveCol && <FoldHeader label={t('Archived')} n={archivedN} open={showArchived} onToggle={toggleArchived} />}
      {/* The Today lane — the same tasks, seen a second time */}
      {todayTasks.length > 0 && (
        <Fragment key="__today">
          <div className="text-11 font-mono px-2 py-4 flex items-start gap-4 border-b border-brand/25">
            <span className="text-brand">☀</span>
            <span className="text-primary font-semibold">{t('Today')}</span>
            <span className="text-tertiary">{todayTasks.length}</span>
          </div>
          {columns.map((col) => {
            const items = byLaneCol.todayCols.get(col.key) ?? EMPTY_ROWS
            return (
              <KanbanColumnDropZone
                key={col.key}
                onDropTask={(id) => handleDropToday(id, col.key)}
                className="rounded-input flex flex-col gap-2 p-3 min-h-[52px] border-b border-brand/25"
                style={{ backgroundColor: 'color-mix(in srgb, var(--brand) 5%, transparent)' }}
              >
                {copyMode && items.length > 0 && (
                  <BatchTools items={items} label={`today · ${col.label}`} dragPayload={bulkPayload(col.key, undefined, true)} />
                )}
                {items.map((task) => (
                  <TodayShadow key={task.id} onDrop={() => void toggleToday(task)}>
                    <TaskCard task={task} {...linkProps(task, true)} compact showDesc={false} copyMode={copyMode} showProject={multi} axes={axes} today onToggleToday={onCardToday} onEdit={onCardEdit} onRelease={onCardRelease} />
                  </TodayShadow>
                ))}
              </KanbanColumnDropZone>
            )
          })}
          {showArchiveCol && <div className="border-b border-brand/25" aria-hidden />}
        </Fragment>
      )}
      {/* Lane rows */}
      {lanes.map((lane) => {
        const collapsed = collapsedLanes.has(lane)
        return (
        <Fragment key={lane}>
          <LaneLabel
            name={lane}
            count={byLaneCol.laneN.get(lane) ?? 0}
            collapsed={collapsed}
            onToggle={() => toggleLane(lane)}
            onRename={(next) => renameLane(lane, next)}
            onDelete={() => deleteLane(lane)}
            onDropLane={(dragged) => moveLaneBefore(dragged, lane)}
          />
          {columns.map((col) => {
            const items = byLaneCol.cells.get(`${lane}\n${col.key}`) ?? EMPTY_ROWS
            if (col.strip) {
              return (
                <FoldCell
                  key={col.key}
                  open={!!openStrips[col.key]}
                  items={items}
                  onDropTask={(id) => handleDrop(id, col.key, lane)}
                  render={(task) => (
                    <TaskDropSlot key={task.id} onDropTask={(id) => handleDrop(id, col.key, lane, task.id)}>
                      <TaskCard task={task} {...linkProps(task)} compact showDesc={showDesc} copyMode={copyMode} showProject={multi} axes={axes} today={isToday(task, today)} onToggleToday={onCardToday} selectedIndex={selection.indexOf(task.id) + 1 || null} onSelect={toggleSelect} onEdit={onCardEdit} onRelease={onCardRelease} />
                    </TaskDropSlot>
                  )}
                />
              )
            }
            if (collapsed) {
              // One line: the count, the batch handle in copy mode, still
              // a drop target — tasks can land here without unfolding.
              return (
                <KanbanColumnDropZone
                  key={col.key}
                  onDropTask={(id) => handleDrop(id, col.key, lane)}
                  className={`group/cell bg-elevated rounded-input px-6 h-24 flex items-center gap-6 ${col.className === 'state-doing' ? 'bg-brand/6' : ''}`}
                >
                  <span className={`text-11 font-mono tabular ${items.length ? 'text-secondary' : 'text-tertiary opacity-60'}`}>
                    {items.length}
                  </span>
                  {copyMode && items.length > 0 && (
                    <BatchTools
                      items={items}
                      label={`${col.label} · ${lane}`}
                      dragPayload={bulkPayload(col.key, lane)}
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => { setAddingAssignee(lane === 'unassigned' ? '' : lane); setAddingStatus(col.key) }}
                    className="ml-auto text-11 text-brand hover:text-brand-hover font-mono opacity-0 group-hover/cell:opacity-100 focus:opacity-100"
                    aria-label={`Add task to ${col.label} in lane ${lane}`}
                  >
                    +
                  </button>
                </KanbanColumnDropZone>
              )
            }
            return (
              <KanbanColumnDropZone
                key={col.key}
                onDropTask={(id) => handleDrop(id, col.key, lane)}
                className={`group/cell bg-elevated rounded-input p-4 flex flex-col gap-2 min-h-[60px] ${col.className === 'state-doing' ? 'bg-brand/6' : ''}`}
              >
                <div className="flex items-center justify-end gap-4 -mb-1 min-h-[16px]">
                  {copyMode && items.length > 0 && (
                    <BatchTools
                      items={items}
                      label={`${col.label} · ${lane}`}
                      dragPayload={bulkPayload(col.key, lane)}
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => { setAddingAssignee(lane === 'unassigned' ? '' : lane); setAddingStatus(col.key) }}
                    className="text-11 leading-none text-brand hover:text-brand-hover font-mono opacity-0 group-hover/cell:opacity-100 focus:opacity-100 transition-opacity"
                    aria-label={`Add task to ${col.label} in lane ${lane}`}
                    title={t('Add task · {column} · {lane}', { column: col.label, lane })}
                  >
                    +
                  </button>
                </div>
                {foldStacks(items, tasks).map(({ task, behind, ordinal, total }) => (
                  <TaskDropSlot
                    key={task.id}
                    onDropTask={(id) => handleDrop(id, col.key, lane, task.id)}
                  >
                    <StackWrap
                      stack={{ behind, ordinal, total }}
                      open={openStacks.has(task.stack_id || '')}
                      onToggle={() => toggleStack(task.stack_id || '')}
                      renderBehind={(t) => (
                        <TaskCard key={t.id} task={t} {...linkProps(t)} compact showDesc={showDesc} copyMode={copyMode} showProject={multi} axes={axes} today={isToday(t, today)} onToggleToday={onCardToday} selectedIndex={selection.indexOf(t.id) + 1 || null} onSelect={toggleSelect} onEdit={onCardEdit} onRelease={onCardRelease} />
                      )}
                    >
                    <TaskCard
                      task={task}
                      today={isToday(task, today)}
                      onToggleToday={onCardToday}
                      selectedIndex={selection.indexOf(task.id) + 1 || null}
                      onSelect={toggleSelect}
                      compact
                      showDesc={showDesc}
                      copyMode={copyMode}
                      showProject={multi}
                      mention={mentions[task.id]}
                      notesN={noteCounts[task.id]} evidenceN={evidenceCounts[task.id]}
                      agedSince={statusSince[task.id]}
                      axes={axes}
                    {...linkProps(task)}
                      onEdit={onCardEdit} onRelease={onCardRelease}
                    />
                    </StackWrap>
                  </TaskDropSlot>
                ))}
              </KanbanColumnDropZone>
            )
          })}
          {showArchiveCol && (
          <FoldCell
            open={showArchived}
            items={archivedTasks.filter((t) => laneOf(t) === lane)}
            onDropTask={(id) => handleDrop(id, ARCHIVE, lane)}
            render={(task) => (
              <TaskDropSlot key={task.id} onDropTask={(id) => handleDrop(id, ARCHIVE, lane)}>
                <TaskCard task={task} {...linkProps(task)} compact showDesc={showDesc} copyMode={copyMode} showProject={multi} axes={axes} today={isToday(task, today)} onToggleToday={onCardToday} selectedIndex={selection.indexOf(task.id) + 1 || null} onSelect={toggleSelect} onEdit={onCardEdit} onRelease={onCardRelease} />
              </TaskDropSlot>
            )}
          />
          )}
        </Fragment>
        )
      })}
      {/* Add-lane control (inline form, no prompt dialogs) */}
      <div className="col-span-full pt-6">
        {addingLane ? (
          <form
            onSubmit={(e) => { e.preventDefault(); commitAddLane() }}
            className="flex items-center gap-6 px-4"
          >
            <input
              autoFocus
              value={laneDraft}
              onChange={(e) => setLaneDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') { setAddingLane(false); setLaneDraft('') }
              }}
              placeholder={t('New lane name, such as an assignee')}
              className="bg-elevated text-primary border border-brand rounded-input px-8 py-2 text-11 font-mono w-[240px]"
              aria-label={t('New lane name')}
            />
            <button
              type="submit"
              className="text-11 font-mono text-brand hover:text-brand-hover"
            >
              {t('add')}
            </button>
            <Button variant="text" size="bare" onClick={() => { setAddingLane(false); setLaneDraft('') }}>
              {t('cancel')}
            </Button>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setAddingLane(true)}
            className="text-11 font-mono text-brand hover:text-brand-hover px-4"
          >
            {t('+ add lane')}
          </button>
        )}
      </div>
      {linksLayer}
    </div>
  )
}
