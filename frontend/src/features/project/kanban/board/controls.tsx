/**
 * The board's small controls: the column sort menu, the toolbar's on/off
 * switches, and a batch's copy button plus drag handle.
 */

import { usePopover } from '../../../../hooks/usePopover'
import { Layers } from 'lucide-react'
import { CopyButton } from '../parts'
import { SORT_MODES, columnText } from '../model'
import type { SortMode, TaskRow } from '../model'
import { useEvidenceAsk } from './evidenceAsk'
import { t, tn } from '../../../../i18n/scope/project'

/** Column-header ⇅: pick the view order; the ✓ names what is in charge. */
export function SortMenu({
  mode, onPick,
}: {
  mode: SortMode
  onPick: (m: SortMode) => void
}) {
  const { open, setOpen, rootRef } = usePopover()
  return (
    <span ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t('Sort column')}
        aria-expanded={open}
        title={mode === 'manual' ? t('Sort this column. Your own order is kept.') : `Sorted by ${SORT_MODES.find(([m]) => m === mode)?.[1]}`}
        className={`h-16 w-16 inline-flex items-center justify-center rounded-input text-11 leading-none ${
          mode !== 'manual' ? 'text-brand' : 'text-tertiary hover:text-primary hover:bg-hover'
        }`}
      >
        ⇅
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-[calc(100%+4px)] z-30 w-[190px] rounded-card border border-border-default bg-surface shadow-lg py-4 normal-case tracking-normal">
          {SORT_MODES.map(([m, label]) => (
            <button
              key={m}
              type="button"
              role="menuitemradio"
              aria-checked={mode === m}
              onClick={() => { onPick(m); setOpen(false) }}
              className={`w-full text-left px-10 py-4 text-11 font-mono flex items-center gap-6 hover:bg-hover ${
                mode === m ? 'text-primary' : 'text-tertiary'
              }`}
            >
              <span className="w-10 shrink-0">{mode === m ? '✓' : ''}</span>
              {label}
            </button>
          ))}
        </div>
      )}
    </span>
  )
}

/** A small on/off pill — the board's two view switches. */
export function SwitchChip({
  on, onToggle, label, title,
}: {
  on: boolean
  onToggle: () => void
  label: string
  title: string
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      title={title}
      aria-pressed={on}
      className={`text-11 font-mono px-10 py-2 rounded-pill border transition-colors ${
        on
          ? 'bg-brand/16 text-brand border-brand'
          : 'bg-elevated text-tertiary border-border-default hover:text-primary'
      }`}
    >
      {label}
    </button>
  )
}

/**
 * BatchTools — copy every task in a batch, and the handle that drags the
 * whole batch elsewhere. A "batch" is a column on the plain boards and a
 * single lane×column CELL in the swim-lane view, which is the unit that
 * actually matters there.
 *
 * The pair models the loop "copy the batch → agent works → move it on".
 */
export function BatchTools({
  items, label, dragPayload,
}: {
  items: TaskRow[]
  label: string
  dragPayload: string
}) {
  const evidenceAsk = useEvidenceAsk()
  return (
    <span className="inline-flex items-center gap-2">
      <CopyButton text={columnText(items, evidenceAsk)} label={tn(items.length, 'the {n} task in {column}', 'all {n} tasks in {column}', { column: label })} />
      <span
        draggable
        title={tn(items.length, 'Drag to move the {n} task out of {column}', 'Drag to move all {n} tasks out of {column}', { column: label })}
        aria-label={`Move all tasks out of ${label}`}
        onDragStart={(e) => {
          e.dataTransfer.effectAllowed = 'move'
          e.dataTransfer.setData('text/plain', dragPayload)
        }}
        className="cursor-grab active:cursor-grabbing select-none inline-flex items-center gap-2 text-10 font-mono px-4 h-16 rounded-input bg-brand/12 text-brand hover:bg-brand/20"
      >
        <Layers size={10} aria-hidden />
        {items.length}
      </span>
    </span>
  )
}
