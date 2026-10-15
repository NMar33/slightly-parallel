import type { ReactNode } from 'react'

/**
 * The one on/off switch, in the task window's colours: a small track that
 * is jade when on, and a word beside it. The rules page and the monitor
 * draw it.
 */
export function Switch({
  on, disabled, label, text, title, onChange,
}: {
  on: boolean
  disabled?: boolean
  /** The switch's accessible name. */
  label: string
  /** The word beside the track; the label when left out. */
  text?: ReactNode
  title?: string
  onChange: (next: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      title={title}
      onClick={() => onChange(!on)}
      className="inline-flex items-center gap-6 text-11 font-mono disabled:opacity-40 disabled:cursor-not-allowed group"
    >
      <span className={`relative inline-flex shrink-0 h-14 w-[26px] rounded-pill transition-colors ${on ? 'bg-brand' : 'bg-border-strong'}`}>
        <span className={`absolute top-2 h-10 w-10 rounded-pill bg-base shadow-sm transition-all ${on ? 'left-[14px]' : 'left-2'}`} />
      </span>
      <span className={on ? 'text-brand' : 'text-tertiary group-hover:text-primary'}>{text ?? label}</span>
    </button>
  )
}
