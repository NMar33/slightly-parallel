import { t } from '../i18n/scope/shell'
/**
 * A row of separate pills, one of them on.
 *
 * Segmented is one joined control for a few short options; PillRow is
 * separate pills for options that are names or may wrap.
 *
 * The API mirrors Segmented: options are [value, text, hint?] tuples, the
 * group is a radiogroup and every pill a radio. Two sizes — `sm` (20 high,
 * the chips beside a small label) and `md` (24 high, the editor's rows).
 * The pill that is on is the brand colour; the others are outlined.
 *
 * Clicking the pill that is already on clears the value when `clearable`
 * is set; otherwise it does nothing.
 */
export function PillRow<T extends string>({
  label, value, onChange, options, clearable = false, size = 'md', gap = 4, className = '',
}: {
  /** The accessible name of the group. */
  label: string
  value: T | ''
  onChange: (v: T) => void
  /** Value, the word on the pill, and an optional tooltip. */
  options: Array<readonly [T, string, string?]>
  clearable?: boolean
  size?: 'sm' | 'md'
  /** Space between pills — 6 when the row sits inside a gap-6 line. */
  gap?: 4 | 6
  className?: string
}) {
  // Written out: Tailwind reads the class names, so they cannot be composed.
  const dims = size === 'sm' ? 'h-20 px-8 text-10' : 'h-24 px-10 text-11'
  return (
    <div role="radiogroup" aria-label={label} className={`flex items-center flex-wrap ${gap === 6 ? 'gap-6' : 'gap-4'} ${className}`}>
      {options.map(([v, text, hint]) => {
        const picked = value === v
        return (
          <button
            key={v || 'all'}
            type="button"
            role="radio"
            aria-checked={picked}
            title={hint ?? (picked && clearable ? t('Click again to clear') : undefined)}
            onClick={() => onChange(picked && clearable ? ('' as T) : v)}
            className={`${dims} rounded-pill border font-mono whitespace-nowrap ${
              picked ? 'border-brand bg-brand text-on-brand' : 'border-border-default text-secondary hover:border-brand'
            }`}
          >
            {text}
          </button>
        )
      })}
    </div>
  )
}
