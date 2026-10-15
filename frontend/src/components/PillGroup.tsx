import { Segmented } from './Segmented'
import { LABEL } from './ui'

/**
 * The task window's value row: a small label, then a joined switch whose
 * picked item clears on a second click. The task window, the board's
 * overlays, the prompt library, rules, artifacts and the calendar draw it.
 *
 * `labelWidth` lines the switches of a stack of rows up under each other;
 * a row on its own leaves it out, so no gap opens after a short label.
 */
export function PillGroup({
  label, value, onChange, options, hint, labelWidth,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: Array<[string, string]>
  /** A tooltip on the label. */
  hint?: string
  /** The label column's width in px, for rows stacked under each other. */
  labelWidth?: number
}) {
  return (
    <div className="flex items-center gap-6 flex-wrap">
      <span className={`${LABEL} shrink-0`} title={hint} style={labelWidth ? { width: labelWidth } : undefined}>{label}</span>
      <Segmented label={label} value={value} onChange={onChange} options={options} clearable />
    </div>
  )
}
