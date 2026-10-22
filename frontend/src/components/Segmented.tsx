import { t } from '../i18n/scope/shell'
/**
 * The one segmented switch: a row of joined buttons, one of them on.
 *
 * Two registers, and nothing else varies. `input` is the square-cornered
 * strip the truth pages put under a label — the filters and the version
 * line. `pill` is the rounded strip a toolbar carries — the mode, the
 * view, the range. Height follows the register (24 for `input`, 20 for
 * `pill`) unless a caller says otherwise, and the item that is on is the
 * brand colour unless `tone="hover"` asks for the quieter one.
 *
 * Clicking the item that is already on clears the value when `clearable`
 * is set; otherwise it does nothing.
 */
export function Segmented<T extends string>({
  label, value, onChange, options, shape = 'input', height, tone = 'brand', clearable = false, className = '',
}: {
  /** The accessible name of the group. */
  label: string
  value: T | ''
  onChange: (v: T) => void
  /** Value, the word on the button, and an optional tooltip. */
  options: Array<readonly [T, string, string?]>
  shape?: 'input' | 'pill'
  height?: 20 | 24
  tone?: 'brand' | 'hover'
  clearable?: boolean
  className?: string
}) {
  const h = height ?? (shape === 'pill' ? 20 : 24)
  const frame = shape === 'pill'
    ? 'inline-flex items-center gap-2 rounded-pill border border-border-subtle bg-elevated p-2'
    : 'inline-flex rounded-input border border-border-default overflow-hidden'
  // Written out: Tailwind reads the class names, so they cannot be composed.
  const tall = h === 24 ? 'h-24' : 'h-20'
  const size = shape === 'pill' ? `${tall} px-10 rounded-pill text-10` : `${tall} px-8 text-11`
  const on = tone === 'hover' ? 'bg-hover text-primary' : 'bg-brand text-on-brand'
  const off = tone === 'hover' ? 'text-tertiary hover:text-secondary' : 'text-tertiary hover:text-primary'
  return (
    <div role="radiogroup" aria-label={label} className={`${frame} ${className}`}>
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
            className={`${size} whitespace-nowrap shrink-0 font-mono transition-colors ${picked ? on : `${off} ${shape === 'input' ? 'hover:bg-hover' : ''}`}`}
          >
            {text}
          </button>
        )
      })}
    </div>
  )
}
