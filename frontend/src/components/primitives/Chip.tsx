import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { t } from '../../i18n/scope/shell'

/**
 * Chip — filter/tag pill. PostHog pattern: click toggles `active`; optional
 * `count` badge on the right; optional `onRemove` for removable filters.
 *
 * Cyrillic-safe (renders "матолимп" cleanly).
 */

interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  active?: boolean
  count?: number
  onRemove?: () => void
  children: ReactNode
}

export const Chip = forwardRef<HTMLButtonElement, ChipProps>(function Chip(
  { active = false, count, onRemove, className = '', children, ...rest },
  ref,
) {
  const base =
    'inline-flex items-center gap-8 rounded-pill border px-12 h-32 text-13 font-medium transition-colors duration-fast ease-out'
  const state = active
    ? 'bg-brand-glow border-brand text-brand'
    : 'bg-surface border-border-default text-secondary hover:bg-hover hover:text-primary'
  return (
    <button
      ref={ref}
      type="button"
      aria-pressed={active}
      className={`${base} ${state} ${className}`.trim()}
      {...rest}
    >
      <span className="truncate max-w-[200px]">{children}</span>
      {typeof count === 'number' && (
        <span
          className={`tabular text-11 rounded-pill px-8 py-4 ${
            active ? 'bg-brand text-on-brand' : 'bg-elevated text-tertiary'
          }`}
        >
          {count}
        </span>
      )}
      {/* Presentational remove affordance — NOT its own interactive element:
          nesting a role="button" inside a <button> is invalid (nested
          interactive). Mouse users get a convenience click target; keyboard /
          AT users act on the chip button itself. */}
      {onRemove && (
        <span
          aria-hidden="true"
          title={t('Remove filter')}
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="ml-4 text-tertiary hover:text-primary cursor-pointer"
        >
          x
        </span>
      )}
    </button>
  )
})
