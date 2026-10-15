/**
 * The board's dialogs and panels: which columns show, what a drop into a
 * sorted column means, which kind a new link is, and the ⓘ panel.
 */

import { usePopover } from '../../../../hooks/usePopover'
import { useRef, type ReactNode } from 'react'
import { Info } from 'lucide-react'
import { Modal } from '../../../../components/Modal'
import { Button, IconButton } from '../../../../components/primitives'
import { useModalA11y } from '../../useModalA11y'
import { SORT_MODES } from '../model'
import type { LinkKind, SortMode, TaskRow } from '../model'
import { t } from '../../../../i18n/scope/project'

import { rich } from '../../../../i18n/rich'
/** Gear popup: tick the columns this board shows. Hiding a column hides
 *  its tasks too (they stay in the data — nothing is dumped elsewhere). */
export function ColumnSettings({
  columns, hidden, counts, onToggle, onClose,
}: {
  columns: Array<{ key: string; label: string; strip?: boolean }>
  hidden: Record<string, boolean>
  counts: Record<string, number>
  onToggle: (key: string, hide: boolean) => void
  onClose: () => void
}) {
  const rows = [
    ...columns.map((c) => ({ key: c.key, label: c.label, note: c.strip ? t('folded strip') : '' })),
    { key: '__archive__', label: t('Archived'), note: t('folded strip') },
  ]
  return (
    <Modal label={t('Board columns')} onClose={onClose} width="w-[380px]">
      <div className="flex flex-col gap-10">
        <div className="flex items-center gap-8">
          <h2 className="text-14 font-semibold text-primary">{t('Board columns')}</h2>
          <IconButton label={t('Close')} onClick={onClose} className="ml-auto">×</IconButton>
        </div>
        <div className="flex flex-col gap-2">
          {rows.map((r) => {
            const on = !hidden[r.key]
            const n = counts[r.key] ?? 0
            return (
              <label key={r.key} className="flex items-center gap-8 px-8 py-4 rounded-input hover:bg-hover cursor-pointer text-12">
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => onToggle(r.key, on)}
                  className="accent-[var(--brand)]"
                  aria-label={`Show ${r.label}`}
                />
                <span className="text-primary">{r.label}</span>
                {r.note && <span className="text-10 font-mono text-tertiary">{r.note}</span>}
                <span className={`ml-auto text-11 font-mono ${!on && n > 0 ? 'text-status-amber' : 'text-tertiary'}`}>
                  {n}{!on && n > 0 ? ' hidden' : ''}
                </span>
              </label>
            )
          })}
        </div>
        <p className="text-11 text-tertiary leading-relaxed">
          {t('Hiding a column hides its tasks from this board — they stay in the data and come back when you tick it again. Remembered per board.')}
        </p>
      </div>
    </Modal>
  )
}

/** The drop landed in a sorted view, where its position cannot stick —
 *  the operator chooses what the manual order should be first. */
export function SortedDropDialog({
  mode, column, onManual, onAdopt, onCancel,
}: {
  mode: SortMode
  column: string
  onManual: () => void
  onAdopt: () => void
  onCancel: () => void
}) {
  const label = SORT_MODES.find(([m]) => m === mode)?.[1] ?? mode
  return (
    <Modal label={t('Sorted column')} onClose={onCancel} width="w-[440px]">
      <div className="flex flex-col gap-10">
        <p className="text-13 text-secondary leading-relaxed">
          {rich(t('{column} is sorted by {order}, so a card dropped here would not stay where you put it.'), { column: <strong className="text-primary">{column}</strong>, order: <strong className="text-primary">{label}</strong> })}
        </p>
        <div className="flex flex-col gap-4">
          <button type="button" onClick={onManual} className="flex flex-col items-start gap-1 px-10 py-6 rounded-input border border-border-default hover:border-brand text-left">
            <span className="text-12 font-mono font-semibold text-primary">{t('Use my order')}</span>
            <span className="text-11 text-tertiary">{t('Go back to your own order, then drag the card again')}</span>
          </button>
          <button type="button" onClick={onAdopt} className="flex flex-col items-start gap-1 px-10 py-6 rounded-input border border-border-default hover:border-brand text-left">
            <span className="text-12 font-mono font-semibold text-primary">{t('Keep the sorted order')}</span>
            <span className="text-11 text-tertiary">{t('Save the sorted order as your own, then place the card')}</span>
          </button>
        </div>
        <div className="flex justify-end">
          <Button variant="text" size="bare" onClick={onCancel}>{t('cancel · esc')}</Button>
        </div>
      </div>
    </Modal>
  )
}

/** After the second click: which kind of link? Direction = click order
 *  ("this must finish before that"). */
export function KindPicker({
  from, to, onPick, onCancel,
}: {
  from?: TaskRow
  to?: TaskRow
  onPick: (kind: LinkKind) => void
  onCancel: () => void
}) {
  const name = (t?: TaskRow) => t?.title || t?.id || '?'
  return (
    <Modal label={t('Link kind')} onClose={onCancel} width="w-[420px]">
      <div className="flex flex-col gap-10">
        <div className="text-12 text-secondary leading-relaxed">
          <span className="text-primary font-medium">{name(from)}</span>
          <span className="text-tertiary"> … </span>
          <span className="text-primary font-medium">{name(to)}</span>
        </div>
        <div className="flex flex-col gap-4">
          {([
            ['blocks', 'blocks', t('the first must be done before the second'), 'text-status-red'],
            ['parent', t('is parent of'), t('the second is a sub-task of the first'), 'text-brand'],
            ['relates', t('relates to'), t('related, no order'), 'text-tertiary'],
          ] as Array<[LinkKind, string, string, string]>).map(([k, label, hint, tone]) => (
            <button
              key={k}
              type="button"
              onClick={() => onPick(k)}
              className="flex items-baseline gap-8 px-10 py-6 rounded-input border border-border-default hover:border-brand text-left"
            >
              <span className={`text-12 font-mono font-semibold ${tone}`}>{label}</span>
              <span className="text-11 text-tertiary">{hint}</span>
            </button>
          ))}
        </div>
        <div className="flex justify-end">
          <Button variant="text" size="bare" onClick={onCancel}>{t('cancel · esc')}</Button>
        </div>
      </div>
    </Modal>
  )
}

/**
 * KanbanInfo — command, workflow, and the few facts that actually change
 * how the board is used. No prose.
 */
export function KanbanInfo() {
  // Clicking outside closes; Escape and the focus round-trip are the
  // panel's own (useModalA11y, mounted with it).
  const { open, setOpen, rootRef } = usePopover({ escape: false })

  return (
    <span ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        aria-label={t('About the board')}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="h-20 w-20 inline-flex items-center justify-center rounded-pill text-tertiary hover:text-primary hover:bg-hover transition-colors"
      >
        <Info size={12} aria-hidden />
      </button>
      {open && <KanbanInfoPanel onClose={() => setOpen(false)} />}
    </span>
  )
}

/** The ⓘ panel — its own component so the a11y hook (Escape, focus trap,
 *  focus back to the button) lives and dies with the open panel. */
function KanbanInfoPanel({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null)
  useModalA11y(dialogRef, onClose)
  return (
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-label={t('About the board')}
          className="absolute left-0 top-[calc(100%+6px)] z-dropdown w-[440px] max-w-[90vw] rounded-card border border-border-default bg-surface shadow-lg p-14 flex flex-col gap-10 normal-case tracking-normal"
        >
          <InfoBlock title={t('Who writes')}>
            {t('Agents add tasks with the')} <code>{t('#task')}</code> {t('command. You add one with')} <code>+</code> {t('on a column, and edit a task by clicking its card.')}
          </InfoBlock>
          <InfoBlock title={t('Batches')}>
            {rich(t('Turn on {copy}, copy a column and paste it to an agent. When the agent reports back, drag the column\'s handle onto the next column to move all its tasks. In {lanes} a batch is one lane in one column; the column header still moves every lane.'), { copy: <code>{t('copy')}</code>, lanes: <code>{t('swim lanes')}</code> })}
          </InfoBlock>
          <InfoBlock title={t('Links')}>
            {t('Turn on')} <code>{t('links')}</code> {t('to draw lines between linked tasks: a red arrow for blocks, a line for parent and sub-task, a dotted line for relates. Click a card\'s link button, then another card, and pick the kind. Click a line to change its kind, swap its ends or remove it. Hover a card to highlight its links. A task has one parent, and blocks and parent links cannot form a loop. A card blocked by an open task has a red edge; a parent shows how many sub-tasks are done.')}
          </InfoBlock>
          <InfoBlock title={t('Story and Storyboard')}>
            {t('In a task, open')} <em>{t('Story')}</em> {t('and add a note: a paragraph for an article, a post, a release note, a report line, an FAQ, or a')}{' '}
            <em>{t('prompt')}</em> {t('note on how to write about it. Below the board, the')}{' '}
            <em>{t('Storyboard')}</em> {t('puts notes into documents and copies them as a pack for an agent.')}{' '}
            {t('The agent posts the finished text back as a version under the document; you can also paste one.')}
          </InfoBlock>
          <InfoBlock title={t('Selecting cards')}>
            <strong>{t('Shift-click')}</strong> {t('cards to select them; each shows its place in the order you picked. A bar at the bottom groups them into a queue, plans them for today or copies them. Drag any selected card to move them all: to a column, a lane, Today or the archive. Esc clears the selection.')}
          </InfoBlock>
          <InfoBlock title={t('Stacks')}>
            {rich(t('For steps that come one after another, type the next steps under a new task ({add}), or shift-click cards in order and group them. The board shows the first step with a {chip} chip; click the chip to see the rest. When the first step moves on, the next one appears, marked {next} for a day.'), { add: <em>{t('Add a next step')}</em>, chip: <code>⧉ 1/5</code>, next: <em>{t('next up')}</em> })}
          </InfoBlock>
          <InfoBlock title={t('Today')}>
            {t('Ctrl-click a card (⌘-click on a Mac) to add it to the')} <em>{t('Today')}</em>{' '}
            {t('lane at the top. The card also stays in its column; moving either moves both. Today\'s plan is cleared at midnight. With')}{' '}
            <code>{t('copy')}</code> {t('on, each Today cell has its own copy button and handle: drag the handle to move the day\'s cards to a column or a lane.')}
          </InfoBlock>
          <InfoBlock title={t('Strips')}>
            {t('The colored strips beside the columns hold tasks that are not in play: parked, review later, done archived, and archived. Drag a card onto a strip to put it there, and click the arrow on a strip to open it as a full column. The ⚙ next to the view switcher sets which columns the board shows; a hidden column hides its tasks.')}
          </InfoBlock>
          <InfoBlock title={t('Age and order')}>
            {t('A card that stays in one column gets a corner mark: gray after a day, amber after a week, red after two weeks (Done and Archive do not age). Hover it for the days. The ⇅ in a column header sorts the column by age, priority, impact or quick wins; your own order is kept. Dragging in a sorted column asks which order to keep.')}
          </InfoBlock>
          <InfoBlock title={t('Also')}>
            <code>{t('desc')}</code> {t('shows each task\'s description on its card. Drag a card to another column to change its status, or above another card to reorder. Every change is saved in the task\'s history. Settings › Tasks sets when the Done column collapses.')}
          </InfoBlock>
        </div>
  )
}

function InfoBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-10 uppercase tracking-wider text-tertiary font-medium mb-2">
        {title}
      </div>
      <p className="text-12 text-secondary leading-relaxed">{children}</p>
    </div>
  )
}
