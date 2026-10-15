/**
 * The plain column boards (classic 3-col and workflow 5-col): the grid of
 * status columns with their Today band, Done limit, strips and archive.
 */

import { STRIP_HINTS, STRIP_TONES, bulkPayload, foldStacks, isToday } from '../model'
import type { SortMode } from '../model'
import { TaskCard, StackWrap, TodayShadow } from './Card'
import { BatchTools, SortMenu } from './controls'
import { KanbanColumnDropZone, TaskDropSlot } from './drag'
import { FoldColumn } from './folds'
import { ARCHIVE, EMPTY_ROWS } from './model'
import type { ColumnsGridProps } from './types'
import { t } from '../../../../i18n/scope/project'

/**
 * The plain boards (3-col, 5-col): one column per status, the folded
 * strips, and the archive, on one grid that also carries the links layer.
 */
export function ColumnsGrid(props: ColumnsGridProps) {
  const {
    gridRef, columns, openStrips, showArchiveCol, showArchived, tasksByStatus, toggleStrip,
    handleDrop, copyMode, sorts, setSort, setAddingStatus, archivedN, toggleArchived, todayTasks,
    byLaneCol, handleDropToday, toggleToday, linkProps, multi, axes, onCardToday, onCardEdit,
    onCardRelease, showDesc, today, selection, toggleSelect, tasks, openStacks, toggleStack,
    mentions, noteCounts, evidenceCounts, statusSince, archivedTasks, linksLayer, doneLimit,
    doneExpanded, setDoneExpanded,
  } = props
  return (
    <div ref={gridRef}
      className="relative grid gap-6"
      style={{
        gridTemplateColumns: `${columns.map((c) => (c.strip && !openStrips[c.key] ? '28px' : 'minmax(200px, 1fr)')).join(' ')}${showArchiveCol ? (showArchived ? ' minmax(200px, 1fr)' : ' 28px') : ''}`,
        minWidth: `${columns.reduce((w, c) => w + (c.strip && !openStrips[c.key] ? 32 : 210), 0) + (showArchiveCol ? (showArchived ? 210 : 32) : 0)}px`,
      }}
    >
      {columns.map((col) => {
        const items = tasksByStatus[col.key] || []
        if (col.strip) {
          return (
            <FoldColumn
              key={col.key}
              label={col.label}
              n={items.length}
              open={!!openStrips[col.key]}
              onToggle={() => toggleStrip(col.key)}
              onDropTask={(id) => handleDrop(id, col.key)}
              hint={STRIP_HINTS[col.key] ?? t('Drop a card here')}
              tone={STRIP_TONES[col.key]}
            >
              {items.map((task) => (
                <TaskDropSlot key={task.id} onDropTask={(id) => handleDrop(id, col.key, undefined, task.id)}>
                  <TaskCard task={task} {...linkProps(task)} showDesc={showDesc} copyMode={copyMode} showProject={multi} axes={axes} notesN={noteCounts[task.id]} evidenceN={evidenceCounts[task.id]} mention={mentions[task.id]} today={isToday(task, today)} onToggleToday={onCardToday} selectedIndex={selection.indexOf(task.id) + 1 || null} onSelect={toggleSelect} onEdit={onCardEdit} onRelease={onCardRelease} />
                </TaskDropSlot>
              ))}
            </FoldColumn>
          )
        }
        const limited = col.key === 'done' && items.length > doneLimit
        const shownRaw = limited ? items.slice(0, doneLimit) : items
        const shown = foldStacks(shownRaw, tasks)
        return (
          <KanbanColumnDropZone
            key={col.key}
            onDropTask={(id) => handleDrop(id, col.key)}
            label={`${col.label} column`}
            className={`bg-elevated rounded-input p-6 flex flex-col gap-3 min-h-[180px]`}
          >
            <div className={`flex items-baseline gap-6 pb-3 border-b-2 ${col.className === 'state-doing' ? 'border-b-brand' : col.className === 'state-done' ? 'border-b-status-green' : col.className === 'state-review' ? 'border-b-status-purple' : col.className === 'state-todo' ? 'border-b-status-amber' : 'border-border-default'}`}>
              <span className="text-11 uppercase tracking-wide font-mono text-primary font-bold">
                {col.label}
              </span>
              <span className="text-10 text-tertiary font-mono">{items.length}</span>
              {copyMode && items.length > 0 && (
                <BatchTools
                  items={items}
                  label={col.label}
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
            </div>
            {todayTasks.length > 0 && (() => {
              const mine = byLaneCol.todayCols.get(col.key) ?? EMPTY_ROWS
              return (
                <KanbanColumnDropZone
                  onDropTask={(id) => handleDropToday(id, col.key)}
                  className="rounded-input flex flex-col gap-2 p-3 min-h-[44px] border-b border-brand/25 mb-1"
                  style={{ backgroundColor: 'color-mix(in srgb, var(--brand) 5%, transparent)' }}
                >
                  {mine.length > 0 && (
                    <span className="flex items-center gap-6">
                      <span className="text-10 font-mono text-brand/80">{t('☀ today ·')} {mine.length}</span>
                      {copyMode && (
                        <BatchTools items={mine} label={`today · ${col.label}`} dragPayload={bulkPayload(col.key, undefined, true)} />
                      )}
                    </span>
                  )}
                  {mine.map((task) => (
                    <TodayShadow key={task.id} onDrop={() => void toggleToday(task)}>
                      <TaskCard task={task} {...linkProps(task, true)} compact showDesc={false} copyMode={copyMode} showProject={multi} axes={axes} today onToggleToday={onCardToday} onEdit={onCardEdit} onRelease={onCardRelease} />
                    </TodayShadow>
                  ))}
                </KanbanColumnDropZone>
              )
            })()}
            {items.length === 0 && (
              <div className="text-11 text-tertiary italic py-2">{t('Empty')}</div>
            )}
            {shown.map(({ task, behind, ordinal, total }) => (
              <TaskDropSlot
                key={task.id}
                onDropTask={(id) => handleDrop(id, col.key, undefined, task.id)}
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
            {col.key === 'done' && (limited || doneExpanded) && (
              <button
                type="button"
                onClick={() => setDoneExpanded(!doneExpanded)}
                className="text-11 font-mono text-tertiary hover:text-brand text-left py-2"
              >
                {limited
                  ? t('+ {n} older · show all', { n: items.length - shownRaw.length })
                  : t('− hide older')}
              </button>
            )}
          </KanbanColumnDropZone>
        )
      })}
      {showArchiveCol && (
      <FoldColumn
        label={t('Archived')}
        n={archivedN}
        open={showArchived}
        onToggle={toggleArchived}
        onDropTask={(id) => handleDrop(id, ARCHIVE)}
        hint={t('Drop a card or a batch handle here to archive it')}
        footer={t('Drag a card to the board to restore it')}
      >
        {archivedTasks.map((task) => (
          <TaskDropSlot key={task.id} onDropTask={(id) => handleDrop(id, ARCHIVE)}>
            <TaskCard task={task} {...linkProps(task)} showDesc={showDesc} copyMode={copyMode} showProject={multi} axes={axes} today={isToday(task, today)} onToggleToday={onCardToday} selectedIndex={selection.indexOf(task.id) + 1 || null} onSelect={toggleSelect} onEdit={onCardEdit} onRelease={onCardRelease} />
          </TaskDropSlot>
        ))}
      </FoldColumn>
      )}
      {linksLayer}
    </div>
  )
}
