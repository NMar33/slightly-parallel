/**
 * The folded strips (Parked, Review later, Archived …): the full-height
 * column on the plain boards, and its header and cell in the swim lanes.
 */

import { type ReactNode } from 'react'
import { Button } from '../../../../components/primitives'
import type { TaskRow } from '../model'
import { KanbanColumnDropZone } from './drag'
import { t } from '../../../../i18n/scope/project'

/* ---------------------------------------------------------------------------
 * Archive — a column that is there but folded: a thin strip on the right,
 * always a drop target (drop a card or a batch handle to archive), with an
 * unfold control on top that opens it to a normal column of greyed cards;
 * dragging a card back onto the board restores it.
 * ------------------------------------------------------------------------- */

export function FoldColumn({
  label, n, open, onToggle, onDropTask, children, hint, footer, tone,
}: {
  label: string
  n: number
  open: boolean
  onToggle: () => void
  onDropTask: (id: string) => void
  children: ReactNode
  hint: string
  footer?: string
  tone?: string
}) {
  return (
    <KanbanColumnDropZone
      onDropTask={onDropTask}
      className={`rounded-input flex flex-col ${open ? 'bg-elevated p-6 gap-3 min-h-[180px]' : 'bg-elevated/60 border border-dashed items-center py-4 gap-6 min-h-[180px]'}`}
      style={open ? undefined : { borderColor: tone ? `color-mix(in srgb, ${tone} 45%, transparent)` : 'var(--border-default)' }}
    >
      {open ? (
        <>
          <div className="flex items-baseline gap-6 pb-3 border-b-2 border-border-default">
            <span className="text-11 uppercase tracking-wide font-mono font-bold" style={{ color: tone ?? 'var(--text-tertiary)' }}>{label}</span>
            <span className="text-10 text-tertiary font-mono">{n}</span>
            <Button variant="text" size="bare" onClick={onToggle} className="ml-auto" aria-label={`Fold the ${label} column`} title={t('Fold')}>›</Button>
          </div>
          {n === 0 && <div className="text-11 text-tertiary italic py-2">{hint}</div>}
          {children}
          {footer && <div className="text-10 text-tertiary font-mono pt-4">{footer}</div>}
        </>
      ) : (
        <>
          <Button variant="text" size="bare" onClick={onToggle} className="leading-none" aria-label={t('Unfold the {label} column', { label })} title={`${label} · ${n} · open`}>‹</Button>
          {/* The name runs down the whole strip — the column IS the label. */}
          <span
            className="flex-1 flex items-center uppercase font-mono select-none"
            style={{ writingMode: 'vertical-rl', fontSize: 15, letterSpacing: '0.55em', color: tone ? `color-mix(in srgb, ${tone} 70%, var(--text-tertiary))` : 'color-mix(in srgb, var(--text-tertiary) 80%, transparent)' }}
            title={hint}
          >
            {label.toLowerCase()}{n ? ` · ${n}` : ''}
          </span>
        </>
      )}
    </KanbanColumnDropZone>
  )
}

export function FoldHeader({ label, n, open, onToggle, tone }: { label: string; n: number; open: boolean; onToggle: () => void; tone?: string }) {
  return (
    <div className={`text-11 uppercase tracking-wide font-mono px-6 pb-4 border-b-2 flex gap-6 ${open ? 'items-baseline' : 'flex-col items-center'}`}
      style={{ borderBottomColor: tone ? `color-mix(in srgb, ${tone} 55%, transparent)` : 'var(--border-default)' }}>
      {open ? (
        <>
          <span style={{ color: tone ?? 'var(--text-tertiary)' }}>{label}</span>
          <span className="text-tertiary">{n}</span>
          <Button variant="text" size="bare" onClick={onToggle} className="ml-auto" aria-label={`Fold the ${label} column`} title={t('Fold')}>›</Button>
        </>
      ) : (
        // Just the unfold control: any vertical text here stretches the whole
        // header row and shoves every lane down — the strip stays anonymous
        // in swim lanes (tooltip carries the name) rather than broken.
        <Button variant="text" size="bare" onClick={onToggle} className="leading-none" aria-label={t('Unfold the {label} column', { label })} title={`${label} · ${n} · open`}>‹</Button>
      )}
    </div>
  )
}

export function FoldCell({
  open, items, onDropTask, render,
}: {
  open: boolean
  items: TaskRow[]
  onDropTask: (id: string) => void
  render: (t: TaskRow) => ReactNode
}) {
  return (
    <KanbanColumnDropZone
      onDropTask={onDropTask}
      className={`rounded-input flex flex-col ${open ? 'bg-elevated p-4 gap-2 min-h-[60px]' : 'bg-elevated/60 border border-dashed border-border-default items-center justify-center min-h-[60px]'}`}
    >
      {open ? items.map(render) : (
        <span className="text-10 font-mono text-tertiary" title={t('Drop here to archive')}>{items.length || ''}</span>
      )}
    </KanbanColumnDropZone>
  )
}
