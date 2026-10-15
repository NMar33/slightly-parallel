/**
 * The strips above the board's grid: the selection's action bar, and the
 * day's line — the carry-over button and the Today band with its two
 * actions. Each draws one hook's state (useSelection, useDayPlan).
 */

import { Layers } from 'lucide-react'
import { CopyButton } from '../parts'
import { fromWhen } from '../carry'
import { columnText, normalizeStatus } from '../model'
import type { EvidenceAsk } from '../model'
import type { DayPlan } from './useDayPlan'
import type { Selection } from './useSelection'
import { t, tn } from '../../../../i18n/scope/project'

export function SelectionBar({ sel, evidenceAsk }: { sel: Selection; evidenceAsk: EvidenceAsk }) {
  const { selection, selectedTasks } = sel
  if (selection.length === 0) return null
  return (
    <div
      role="region"
      aria-label={t('Selected tasks')}
      className="fixed bottom-16 left-1/2 -translate-x-1/2 z-50 flex items-center gap-8 flex-wrap rounded-pill border border-brand bg-surface shadow-lg px-14 py-8 text-11 font-mono"
    >
      <span className="text-primary font-semibold">{selection.length} {t('selected')}</span>
      <span className="text-tertiary">{t('Drag to move all')}</span>
      <button
        type="button"
        onClick={() => void sel.groupSelection()}
        disabled={selection.length < 2}
        title={selection.length < 2
          ? t('Shift-click a second card. A group needs at least two.')
          : t('Group them behind “{title}”, in this order, in its column.', { title: String(selectedTasks[0]?.title ?? '').slice(0, 28) })}
        className="h-24 px-10 rounded-pill border border-border-default text-secondary hover:text-brand hover:border-brand disabled:opacity-40 inline-flex items-center gap-4"
      >
        <Layers size={10} aria-hidden /> {t('group them')}
      </button>
      <button
        type="button"
        onClick={() => void sel.todaySelection()}
        className="h-24 px-10 rounded-pill border border-border-default text-secondary hover:text-brand hover:border-brand"
        title={t('Plan all of them for today')}
      >
        {t('☀ today')}
      </button>
      <CopyButton text={columnText(selectedTasks, evidenceAsk)} label={tn(selection.length, '{n} selected task', '{n} selected tasks')} />
      <button
        type="button"
        onClick={sel.clear}
        className="h-24 px-8 rounded-pill text-tertiary hover:text-primary"
        title={t('Clear the selection (Esc)')}
      >
        {t('× clear')}
      </button>
    </div>
  )
}

export function DayBar({ day }: { day: DayPlan }) {
  const { leftover, carryOpen, todayTasks, dayBusy, today } = day
  return (
    <>
      {leftover.length > 0 && !carryOpen && (
        <button
          type="button"
          onClick={() => day.setCarryOpen(true)}
          className="mb-6 h-20 px-8 rounded-pill border border-status-amber text-11 font-mono text-status-amber hover:bg-hover inline-flex items-center gap-6"
          title={t('Planned for an earlier day and still open')}
        >
          ☾ {tn(leftover.length, '{n} task from {when}', '{n} tasks from {when}', { when: fromWhen(leftover, today) })}
        </button>
      )}
      {todayTasks.length > 0 && (
        <div className="mb-6 flex items-center gap-8 flex-wrap text-11 font-mono">
          <span className="text-brand">{t('☀ Today ·')} {todayTasks.length}</span>
          <span className="text-tertiary">
            {todayTasks.filter((t) => normalizeStatus(t.status) === 'done').length} {t('done')}
          </span>
          <button
            type="button"
            onClick={() => void day.todayAllDone()}
            disabled={dayBusy}
            className="h-20 px-8 rounded-pill border border-border-default text-tertiary hover:text-status-green hover:border-status-green disabled:opacity-40"
            title={`Move the ${day.unfinished.length} unfinished cards planned for today to Done. Can be undone.`}
          >
            {dayBusy ? '…' : t('✓ all done')}
          </button>
          <button
            type="button"
            onClick={() => void day.todayDismiss()}
            disabled={dayBusy}
            className="h-20 px-8 rounded-pill border border-border-default text-tertiary hover:text-primary disabled:opacity-40"
            title={t('Clear today\'s plan')}
          >
            {dayBusy ? '…' : t('× dismiss')}
          </button>
        </div>
      )}
    </>
  )
}
