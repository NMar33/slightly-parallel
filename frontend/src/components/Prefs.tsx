import type { ReactNode } from 'react'

/**
 * The settings strip the task window opens under its gear, and every page
 * that grows a gear of its own uses after it.
 *
 * A row is a label and its choices; a chip is one choice, pressed or not.
 * Two pages that both let you set a size should set it with the same
 * control, so there is one of each here rather than one per page.
 */

/** One labelled group of choices inside a settings strip. */
export function PrefRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-6">
      <span className="text-10 uppercase tracking-wide font-mono text-tertiary">
        {label}
      </span>
      <span className="inline-flex items-center gap-2">{children}</span>
    </span>
  )
}

/** One choice in a row: pressed when it is the one in force. */
export function PrefChip({
  on, onClick, title, children,
}: {
  on: boolean
  onClick: () => void
  title?: string
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      title={title}
      className={`text-10 font-mono px-8 py-2 rounded-pill border transition-colors ${
        on
          ? 'bg-brand/16 text-brand border-brand'
          : 'bg-surface text-tertiary border-border-default hover:text-primary'
      }`}
    >
      {children}
    </button>
  )
}
