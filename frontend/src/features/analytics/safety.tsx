/**
 * The page's own check before a query is sent, and the list of what keeps a
 * query from doing harm (the server's, from GET /api/analytics/schema).
 *
 * The server refuses anything but one SELECT whatever the page does; this
 * check only says why sooner, in words, and never sends the query.
 */

import { usePopover } from '../../hooks/usePopover'
import { ShieldCheck } from 'lucide-react'

import { t } from '../../i18n/scope/views'
const CHANGES = ['insert', 'update', 'delete', 'drop', 'alter', 'create', 'truncate', 'attach', 'detach', 'copy', 'export', 'import', 'install', 'load', 'pragma', 'set', 'call', 'vacuum', 'checkpoint']

/** What in this SQL would change something, outside quoted text; '' when nothing. */
export function unsafe(sql: string): string {
  const bare = sql.replace(/'(?:[^']|'')*'/g, "''").replace(/--[^\n]*/g, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ')
  if (/;\s*\S/.test(bare)) return t('Two statements in one: take out the ";". One query at a time.')
  const hit = CHANGES.find((w) => new RegExp(`\\b${w}\\b`, 'i').test(bare) && !(w === 'set' && /\bis\s+not\s+set\b/i.test(bare)))
  return hit ? t('"{v}" would change data. Only reading runs here: it was not sent.', { v: hit.toUpperCase() }) : ''
}

export function SafetyBadge({ lines }: { lines?: string[] }) {
  const { open, setOpen, rootRef } = usePopover()
  return (
    <span ref={rootRef} className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="inline-flex items-center gap-4 h-20 px-8 rounded-pill border text-11 font-mono"
        style={{ borderColor: 'var(--status-green)', color: 'var(--status-green)' }}>
        <ShieldCheck size={11} aria-hidden /> {t('read-only')}
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-4 z-50 w-[400px] max-w-[90vw] p-12 rounded-card border border-border-default bg-base shadow-lg flex flex-col gap-6 font-sans">
          <span className="text-13 font-medium text-primary">{t('A query cannot change your data')}</span>
          <ol className="flex flex-col gap-4 list-decimal pl-16 text-12 text-secondary leading-snug">
            {(lines ?? []).map((l) => <li key={l}>{l}</li>)}
          </ol>
        </div>
      )}
    </span>
  )
}
