/**
 * What the menus and cards over the terminal share: where one stands, the
 * first button taking the keyboard, copying an id, opening a page of
 * Slightly Parallel, and the frame of a record's card.
 */

import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { X } from 'lucide-react'

import { writeClipboard } from '../../../lib/useCopy'
import { post } from '../../aqua/app/bridge'
import { t } from '../../../i18n/scope/msgmenu'

/** Place the menu near the pointer and scroll its actions when space runs out. */
export function place(x: number, y: number, W: number, H: number, w: number, h: number): CSSProperties {
  const width = Math.max(0, Math.min(W, w - 16))
  const height = Math.max(0, Math.min(H, h - 16))
  const left = Math.max(8, Math.min(x, w - width - 8))
  const proposed = y + height > h - 8 ? y - height : y
  const top = Math.max(8, Math.min(proposed, h - height - 8))
  return { left, top, width, maxHeight: Math.max(0, h - top - 8), overflowY: 'auto', overscrollBehaviorY: 'contain' }
}

/** Keep a card and its actions scrollable inside the pane, even before its contents load. */
export function placeCard(x: number, y: number, W: number, w: number, h: number): CSSProperties {
  return place(x, y, W, 280, w, h)
}

/** The first button of a menu takes the keyboard. */
export function useFirstFocus(ref: React.RefObject<HTMLElement | null>, again: unknown = null) {
  useEffect(() => { ref.current?.querySelector<HTMLElement>('button:not([disabled])')?.focus() }, [ref, again])
}

export async function copyId(id: string, say: (s: string) => void) {
  say(await writeClipboard(id) ? t('Copied {id}', { id }) : t('The browser did not allow copying'))
}

/** A page of Slightly Parallel, in the app's own window when the app holds this one, else a browser tab. */
export function openPage(path: string) {
  const url = `${window.location.origin}${path}`
  if (!post({ op: 'open', url })) window.open(url, '_blank', 'noopener')
}

export const DIM: CSSProperties = { color: 'var(--aq-term-dim)' }
export const FG: CSSProperties = { color: 'var(--aq-term-fg)' }

/** A record's card over the terminal: its id and chips on top, what it holds, then its actions. */
export function RecordCard({ label, id, style, chips, actions, children, close }: {
  /** What the record is, for the dialog's name: "Decision", "Core"… */
  label: string
  id: string
  style: CSSProperties
  chips?: ReactNode
  actions: ReactNode
  children: ReactNode
  close: () => void
}) {
  const box = useRef<HTMLDivElement>(null)
  useFirstFocus(box)
  return (
    <div ref={box} className="mm-pop lab-menu lab-list lab-card flex flex-col" role="dialog" aria-label={`${label} ${id}`} data-record={label}
      style={style}>
      <div className="lab-list-head shrink-0">
        <span className="font-mono">{id}</span>
        <span className="lab-list-sub">{label}</span>
        {chips}
        <button type="button" className="lab-edge-btn icon ml-auto" aria-label={t('Close')} onClick={close}><X size={12} /></button>
      </div>
      <div className="min-h-0 overflow-auto px-10 pb-6 flex flex-col gap-6">{children}</div>
      <div className="shrink-0 pt-2" style={{ borderTop: '1px solid var(--aq-term-frame, rgba(255,255,255,0.1))' }}>{actions}</div>
    </div>
  )
}

/** One action of a card. */
export function Action({ icon, label, onClick, disabled }: { icon: ReactNode; label: string; onClick: () => void; disabled?: boolean }) {
  return <button type="button" className="lab-list-row" disabled={disabled} onClick={onClick}>{icon}{label}</button>
}

/** A small titled part of a card. */
export function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-10 uppercase tracking-wide" style={DIM}>{title}</span>
      {children}
    </div>
  )
}
