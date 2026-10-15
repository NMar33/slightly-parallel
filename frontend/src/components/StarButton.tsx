import { STAR_COLOR } from '../lib/marks'
import { t } from '../i18n/scope/shell'

/**
 * The ★ of an important thing: filled when starred, a faint ☆ otherwise
 * (shown on hover by the host when `quiet`). A click stars or unstars and
 * never reaches the card or row underneath.
 */
export function StarButton({ on, onToggle, what, quiet = false, size = 12 }: {
  on: boolean
  onToggle: (next: boolean) => void
  /** What is starred, for the label: "this task", "this agent". */
  what: string
  /** Unstarred, show only when the host is hovered (`group` on the host). */
  quiet?: boolean
  size?: number
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={on ? t('Unmark {what} as important', { what }) : t('Mark {what} as important', { what })}
      title={on ? t('Unmark {what} as important', { what }) : t('Mark {what} as important', { what })}
      onClick={(e) => { e.stopPropagation(); e.preventDefault(); onToggle(!on) }}
      className={`shrink-0 leading-none inline-flex items-center justify-center rounded-input hover:bg-hover ${
        on ? '' : quiet ? 'opacity-0 group-hover:opacity-100 focus:opacity-100 text-tertiary' : 'text-tertiary'}`}
      style={{ fontSize: size, width: size + 4, height: size + 4, color: on ? STAR_COLOR : undefined }}
    >
      {on ? '★' : '☆'}
    </button>
  )
}
