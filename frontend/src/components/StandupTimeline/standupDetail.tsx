/**
 * The opened standup: the since-last prose (L2), and the open goals (L3)
 * and today's plan (L4) behind their own small toggles.
 */

import { useEffect, useState, type ReactNode } from 'react'

import { LABEL } from '../ui'
import { LoadingSkeleton } from '../states'
import type { DetailState } from './useStandupDetail'
import { t } from '../../i18n/scope/shell'

// ---------------------------------------------------------------------------
// L2 rail — "since last" prose, loading/error/empty variants
// ---------------------------------------------------------------------------

export function L2Rail({
  detail,
  onRetry,
}: {
  detail: DetailState | undefined
  onRetry: () => void
}) {
  const status = detail?.status ?? 'idle'
  const text = detail?.detail?.l2?.trim() ?? ''

  return (
    <div className="flex flex-col gap-4">
      <span className={LABEL}>
        since last standup
      </span>

      {status === 'loading' && (
        <LoadingSkeleton variant="text" count={1} label={t('Loading detail')} />
      )}

      {status === 'error' && (
        <ErrorRow
          message={detail?.error ?? t('Unknown error.')}
          onRetry={onRetry}
        />
      )}

      {status === 'ready' && text && (
        <p className="text-13 text-primary leading-relaxed max-w-reading">
          {text}
        </p>
      )}

      {status === 'ready' && !text && (
        <p className="text-13 text-tertiary italic">{t('Nothing recorded since the last standup.')}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Nested drawer — small disclosure toggle for L3/L4.
// ---------------------------------------------------------------------------

export function NestedDrawer({
  label,
  labelOpen,
  disabled,
  children,
}: {
  label: string
  labelOpen: string
  disabled: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (disabled) setOpen(false)
  }, [disabled])
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        disabled={disabled}
        className="inline-flex items-center gap-4 text-12 font-mono text-secondary hover:text-brand disabled:opacity-50 disabled:hover:text-secondary border-b border-dotted border-tertiary hover:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-input px-2 motion-safe:transition-colors motion-safe:duration-fast ease-out"
      >
        <span
          aria-hidden="true"
          className={`inline-block text-10 motion-safe:transition-transform motion-safe:duration-fast ease-out ${
            open ? 'rotate-90' : ''
          }`}
        >
          ▸
        </span>
        {open ? labelOpen : label}
      </button>
      {open && <div className="mt-8">{children}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// L3 — open goals bullets
// ---------------------------------------------------------------------------

export function L3Block({ detail }: { detail: DetailState | undefined }) {
  if (!detail || detail.status === 'loading') {
    return <LoadingSkeleton variant="text" count={3} label={t('Loading open goals')} />
  }
  if (detail.status === 'error') {
    return (
      <p className="text-12 text-status-red italic">
        Couldn't load: {detail.error}
      </p>
    )
  }
  const items = detail.detail?.l3 ?? []
  if (items.length === 0) {
    return <p className="text-12 text-tertiary italic">{t('No open goals recorded.')}</p>
  }
  return (
    <div className="rounded-card border border-border-subtle bg-surface px-16 py-12 max-w-reading">
      <p className={`${LABEL} mb-8`}>
        open goals
      </p>
      <ul className="list-disc pl-16 flex flex-col gap-6 text-13 text-primary leading-relaxed">
        {items.map((it, i) => (
          <li key={i}>
            <GoalLine text={it} />
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Split an open-goal bullet like `alpha-labs · SDK generator (g_a4) · 55% · 2/5d`
 * into a headline + trailing meta chips. Falls back to raw text if the line
 * doesn't have the pipe-separator shape.
 */
function GoalLine({ text }: { text: string }) {
  const parts = text.split('·').map(s => s.trim()).filter(Boolean)
  if (parts.length <= 1) return <span>{text}</span>
  const [head, ...meta] = parts
  return (
    <span>
      <span className="text-primary">{head}</span>
      {meta.map((m, i) => (
        <span key={i} className="text-tertiary font-mono ml-8 text-12">
          <span aria-hidden className="opacity-50 mr-4">·</span>
          {m}
        </span>
      ))}
    </span>
  )
}

// ---------------------------------------------------------------------------
// L4 — today's plan
// ---------------------------------------------------------------------------

export function L4Block({ detail }: { detail: DetailState | undefined }) {
  if (!detail || detail.status === 'loading') {
    return <LoadingSkeleton variant="text" count={2} label={t('Loading today plan')} />
  }
  if (detail.status === 'error') {
    return (
      <p className="text-12 text-status-red italic">
        Couldn't load: {detail.error}
      </p>
    )
  }
  const raw = detail.detail?.l4 ?? ''
  const blocks = raw.split(/\n\s*\n/).map(b => b.trim()).filter(Boolean)
  if (blocks.length === 0) {
    return (
      <p className="text-12 text-tertiary italic">
        No plan for today recorded.
      </p>
    )
  }
  return (
    <div className="rounded-card border border-border-subtle bg-base px-16 py-12 max-w-reading flex flex-col gap-12">
      <p className={LABEL}>
        today's plan
      </p>
      {blocks.map((b, i) => (
        <p
          key={i}
          className="text-13 text-primary leading-relaxed whitespace-pre-line"
        >
          {b}
        </p>
      ))}
    </div>
  )
}

function ErrorRow({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div role="alert" className="flex items-center gap-8 text-12 text-status-red">
      <span>Couldn't load: {message}</span>
      <button
        type="button"
        onClick={onRetry}
        className="font-mono text-11 border border-status-red rounded-pill px-8 py-2 hover:bg-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand motion-safe:transition-colors motion-safe:duration-fast ease-out"
      >
        Retry ↻
      </button>
    </div>
  )
}
