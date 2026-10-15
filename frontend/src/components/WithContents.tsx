import { type ReactNode } from 'react'

import { LABEL } from '../features/promptlib/taskstyle'

/**
 * A long page read with a contents rail — the idiom /decisions and the
 * truth pages already use: a sticky list of the sections on the left, the
 * document on the right. The page fills the window; only the prose inside
 * keeps a reading measure.
 *
 * Items name sections that exist on the page: each `id` is the id of a
 * section with `scroll-mt-16`, and the link jumps to it.
 */

export interface ContentsItem {
  id: string
  text: string
  /** A count or a short word beside the entry. */
  note?: string
}

export function WithContents({
  label,
  items,
  children,
}: {
  label: string
  items: ContentsItem[]
  children: ReactNode
}) {
  return (
    <div className="grid gap-24 lg:grid-cols-[240px_minmax(0,1fr)]">
      <nav
        aria-label={label}
        className="flex flex-col gap-2 lg:sticky lg:top-[16px] lg:self-start lg:max-h-[calc(100vh-120px)] lg:overflow-y-auto pr-4"
      >
        <span className={`${LABEL} px-8 pb-2`}>{label}</span>
        {items.map((it) => (
          <a
            key={it.id}
            href={`#${it.id}`}
            title={it.text}
            className="px-8 py-2 text-12 text-secondary hover:text-primary flex items-baseline gap-6 min-w-0"
          >
            <span className="truncate">{it.text}</span>
            {it.note && (
              <span className="ml-auto text-10 font-mono text-tertiary tabular shrink-0">{it.note}</span>
            )}
          </a>
        ))}
      </nav>
      <div className="flex flex-col gap-24 min-w-0">{children}</div>
    </div>
  )
}
