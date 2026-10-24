import { useRef, type ReactNode } from 'react'

import { useModalA11y } from '../features/project/useModalA11y'

/**
 * Modal — the one frame for everything centred over the page. The house
 * scrim (55% bg-base), the rounded-card surface, Escape / focus trap /
 * focus return (useModalA11y), and a click on the scrim closes. Width
 * comes from the caller (`w-[520px]`-style classes on `width`, or
 * `w-full` plus a pixel `maxWidth`); tall content scrolls inside.
 *
 *   <Modal label="Edit the block" onClose={...} width="w-[520px]">…</Modal>
 *
 * Two tones, one scrim:
 *   - `dialog` (default) asks one thing — confirm, name, pick. Default
 *     border, shadow-lg.
 *   - `window` is a workspace you stay in for a while — the task, a
 *     press release, the carry-over, a calendar entry or milestone. The
 *     same scrim, blurred (backdrop-blur-sm), a strong border and
 *     shadow-2xl so the workspace stands off the page.
 *
 * A window that is portaled (createPortal to body) stays portaled by its
 * caller; a later-mounted modal paints over an earlier one at the same
 * z-modal, and useModalA11y gives the keyboard to the top one.
 */
export function Modal({
  label, labelledBy, onClose, tone = 'dialog', width = 'w-[480px]', maxWidth, padding = 'p-16',
  className = '', top = false, isolateKeys = false, children,
}: {
  /** aria-label; or name the dialog by a heading id with `labelledBy`. */
  label?: string
  labelledBy?: string
  onClose: () => void
  tone?: 'dialog' | 'window'
  /** Tailwind width classes for the dialog box. */
  width?: string
  /** A pixel cap on the box (for widths chosen at runtime). */
  maxWidth?: number
  padding?: string
  /** Extra classes on the box (its inner layout). */
  className?: string
  /** Align to the top (a tall reader) instead of the centre. */
  top?: boolean
  /** Keep key events from bubbling (through React) to the page behind. */
  isolateKeys?: boolean
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  useModalA11y(ref, onClose)
  const isWindow = tone === 'window'
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation()
  // A text selection that starts in the dialog and ends on the backdrop
  // sends the click to the backdrop: it closed the window and lost the edit.
  const pressedBackdrop = useRef(false)
  return (
    <div
      role="presentation"
      onMouseDown={(e) => { pressedBackdrop.current = e.target === e.currentTarget }}
      className={`fixed inset-0 z-modal flex justify-center ${isWindow ? 'p-16 backdrop-blur-sm' : 'p-24'} ${top ? 'items-start pt-48' : 'items-center'}`}
      style={{ backgroundColor: 'color-mix(in srgb, var(--bg-base) 55%, transparent)' }}
      onClick={(e) => { if (e.target === e.currentTarget && pressedBackdrop.current) onClose() }}
      onKeyDown={isolateKeys ? stop : undefined}
      onKeyUp={isolateKeys ? stop : undefined}
    >
      <div ref={ref} role="dialog" aria-modal="true"
        aria-label={labelledBy ? undefined : label} aria-labelledby={labelledBy}
        className={`${width} max-w-[94vw] ${isWindow ? 'max-h-[92vh]' : 'max-h-[90vh]'} overflow-y-auto rounded-card border bg-surface ${isWindow ? 'border-border-strong shadow-2xl' : 'border-border-default shadow-lg'} ${padding} ${className}`}
        style={maxWidth !== undefined ? { maxWidth } : undefined}
        onClick={isWindow ? stop : undefined}>
        {children}
      </div>
    </div>
  )
}
