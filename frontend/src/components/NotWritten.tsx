import type { ReactNode } from 'react'

import { LABEL } from '../features/promptlib/taskstyle'
import { t } from '../i18n/scope/shell'

/**
 * Entries an agent was asked for and never wrote.
 *
 * A kept #skill or #artifact with nothing behind it is not a skill or an
 * artifact: it is a request the agent did not answer. It stands apart from
 * the list, under the same heading everywhere — the date, the project, the
 * id, the message that was kept, and whatever the page offers to do about
 * it. A row that opens is a button; a row that only offers an act is a line.
 */

interface NotWrittenRow {
  id: string
  /** The date line: when the message was kept. */
  stamp: string
  project: string
  /** The message that was kept. */
  text: string
  /** Set on the row that is open. */
  active?: boolean
  /** Given when the row opens into the entry. */
  onOpen?: () => void
  /** Copy the request, Archive — whatever the page offers. */
  action?: ReactNode
}

export function NotWritten({ blurb, rows }: { blurb: string; rows: NotWrittenRow[] }) {
  if (!rows.length) return null
  return (
    <section aria-label={t('Not written')} className="flex flex-col gap-4 border-t border-border-subtle pt-12">
      <div className="px-8 flex flex-col gap-2">
        <span className={LABEL}>{t('Not written')}</span>
        <span className="text-11 text-tertiary leading-relaxed">{blurb}</span>
      </div>
      {rows.map((r) => {
        const line = (
          <span className="text-10 font-mono text-tertiary tabular shrink-0">
            {r.stamp} · {r.project || t('No project')} · {r.id}
          </span>
        )
        if (!r.onOpen) {
          return (
            <div key={r.id} className="flex items-baseline gap-12 flex-wrap px-8 py-4 rounded-input border border-transparent">
              {line}
              <span className="text-12 text-secondary min-w-0 flex-1">{r.text}</span>
              {r.action}
            </div>
          )
        }
        return (
          <div key={r.id}
            className={`px-8 py-4 flex flex-col gap-3 rounded-input border ${r.active ? 'border-brand bg-brand-glow' : 'border-transparent'}`}>
            <button type="button" onClick={r.onOpen} aria-current={r.active ? 'true' : undefined}
              className="text-left flex flex-col gap-3 rounded-input hover:text-primary">
              {line}
              <span className="text-12 text-secondary leading-relaxed">{r.text}</span>
            </button>
            {r.action}
          </div>
        )
      })}
    </section>
  )
}
