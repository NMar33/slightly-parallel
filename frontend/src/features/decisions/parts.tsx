import { useState } from 'react'
import { Markdown } from '../../components/Markdown'
import { LABEL } from '../promptlib/taskstyle'
import {
  dayLabel, type Alternative, type Decision,
} from './data'
import { t } from '../../i18n/scope/system'

export function MetaLine({ d, className = '' }: { d: Decision; className?: string }) {
  const parts = [
    [dayLabel(d.row.created_date), d.row.created_time].filter(Boolean).join(', '),
    d.row.project, d.who,
  ].filter(Boolean)
  const weight = (d.row.weight ?? '').trim()
  return (
    <span className={`text-11 font-mono text-tertiary ${className}`} title={d.row.agent_id ?? ''}>
      {/* Only the two that differ from the usual are marked: a major one
          stands out, a minor one is known to be small. */}
      {weight === 'major' && <span className="text-status-amber">{t('Major')} · </span>}
      {weight === 'minor' && <span>{t('Minor')} · </span>}
      {parts.join(' · ')}
    </span>
  )
}

const MARK: Record<Alternative['verdict'], { sign: string; word: string; tone: string }> = {
  chosen: { sign: '✓', word: 'chosen', tone: 'text-status-green' },
  rejected: { sign: '✕', word: 'rejected', tone: 'text-tertiary' },
  other: { sign: '·', word: '', tone: 'text-tertiary' },
}

/** One alternative: the option, struck when it was turned down, and the reason. */
function AlternativeLine({ a }: { a: Alternative }) {
  const m = MARK[a.verdict]
  return (
    <li className="flex items-baseline gap-8 min-w-0">
      <span role={m.word ? 'img' : undefined} className={`shrink-0 w-12 text-12 font-mono ${m.tone}`} aria-label={m.word ? t(m.word) : undefined}>{m.sign}</span>
      <span className="min-w-0 text-13 leading-relaxed">
        <span className={a.verdict === 'rejected' ? 'text-secondary line-through decoration-border-default' : 'text-primary'}>
          {a.option}
        </span>
        {a.reason && <span className="text-secondary"> — {a.reason}</span>}
      </span>
    </li>
  )
}

export function Alternatives({ items }: { items: Alternative[] }) {
  if (items.length === 0) return null
  return (
    <section aria-label={t('Alternatives')} className="flex flex-col gap-4">
      <span className={LABEL}>{t('Alternatives')}</span>
      <ul className="flex flex-col gap-4">
        {items.map((a, i) => <AlternativeLine key={i} a={a} />)}
      </ul>
    </section>
  )
}

export function Why({ text }: { text: string }) {
  if (!text) return null
  return (
    <section aria-label={t('Why')} className="flex flex-col gap-4">
      <span className={LABEL}>{t('Why')}</span>
      <div className="text-13 text-secondary leading-relaxed max-w-[720px]"><Markdown text={text} /></div>
    </section>
  )
}

/** The chat where it was decided, folded. Absent when none was kept. */
export function Excerpt({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  return (
    <section aria-label={t('Where it was decided')} className="flex flex-col gap-4">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="flex items-center gap-8 text-left h-20 self-start">
        <span className={`text-10 text-tertiary transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden>▶</span>
        <span className={LABEL}>{t('Where it was decided')}</span>
      </button>
      {open && (
        <pre className="max-h-[320px] overflow-auto rounded-input border border-border-subtle bg-base px-12 py-10 text-12 font-mono text-secondary whitespace-pre-wrap break-words max-w-[720px]">
          {text}
        </pre>
      )}
    </section>
  )
}
