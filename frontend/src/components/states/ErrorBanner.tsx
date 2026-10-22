import { useState } from 'react'
import { Button } from '../primitives/Button'
import { t } from '../../i18n/scope/shell'

/**
 * ErrorBanner — dismissible inline error, with an optional Retry action.
 *
 * Use for recoverable failures (a fetch that errored, a stale ETag, a
 * backend that went away). For unrecoverable renders, throw and let a
 * top-level error boundary catch instead.
 *
 *   <ErrorBanner
 *     title="Could not load projects"
 *     message="Backend returned 503. Retry in a moment."
 *     onRetry={() => queryClient.invalidateQueries(['snapshot'])}
 *   />
 *
 * Uses --status-red for the border accent; message text stays --text-primary
 * so it's still WCAG-AA on any surface.
 */

interface ErrorBannerProps {
  title: string
  message?: string
  onRetry?: () => void
  onDismiss?: () => void
  /** Hide the internal dismiss button (parent controls visibility). */
  hideDismiss?: boolean
  className?: string
}

export function ErrorBanner({
  title,
  message,
  onRetry,
  onDismiss,
  hideDismiss = false,
  className = '',
}: ErrorBannerProps) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null

  const handleDismiss = () => {
    setDismissed(true)
    onDismiss?.()
  }

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`rounded-card border bg-surface p-12 flex items-start gap-12 ${className}`.trim()}
      style={{ borderColor: 'var(--status-red)' }}
      data-testid="error-banner"
    >
      <div
        aria-hidden="true"
        className="flex items-center justify-center shrink-0 rounded-pill"
        style={{
          width: 20,
          height: 20,
          background: 'var(--status-red)',
          color: 'var(--bg-base)',
          fontSize: 13,
          fontWeight: 600,
          lineHeight: 1,
          marginTop: 2,
        }}
      >
        !
      </div>
      <div className="flex-1 min-w-0 flex flex-col gap-4">
        <div className="text-13 font-semibold text-primary">{title}</div>
        {message && <div className="text-12 text-secondary">{message}</div>}
      </div>
      <div className="flex items-center gap-8 shrink-0">
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Retry
          </Button>
        )}
        {!hideDismiss && (
          <button
            type="button"
            onClick={handleDismiss}
            aria-label={t('Dismiss')}
            className="inline-flex items-center justify-center h-24 w-24 rounded-input text-secondary hover:bg-hover hover:text-primary transition-colors duration-fast ease-out"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <path d="M2 2 L10 10 M10 2 L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
