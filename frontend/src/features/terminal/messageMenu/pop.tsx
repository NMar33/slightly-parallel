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

/** A menu of a known height at the point, kept inside the window. */
export function place(x: number, y: number, W: number, H: number, w: number, h: number) {
  return { left: Math.min(Math.max(8, x), Math.max(8, w - W - 8)), top: y + H > h - 8 ? Math.max(8, y - H) : y, width: W }
}

/**
 * A card of a height not known before it is read: below the point when
 * there is room (or more room than above), else above it; it scrolls
 * inside when taller than the room.
 */
export function placeCard(x: number, y: number, W: number, w: number, h: number): CSSProperties {
  const left = Math.min(Math.max(8, x), Math.max(8, w - W - 8))
  const width = Math.min(W, Math.max(200, w - 16))
  const below = h - y - 8
  const above = y - 28
  if (below >= 280 || below >= above) return { left, top: y, width, maxHeight: Math.max(120, below) }
  return { left, bottom: h - y + 20, width, maxHeight: Math.max(120, above) }
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
