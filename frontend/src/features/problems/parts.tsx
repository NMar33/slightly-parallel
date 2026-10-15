import { getJson } from '../../lib/getJson'
import { entryText, type EntryDetailLike } from '../../lib/entryText'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '../../components/primitives'
import { FIELD, LABEL } from '../promptlib/taskstyle'
import { cleanTitle, useRuleFromProblem, type Vision } from '../visions/data'
import { InterpretationText } from '../visions/parts'
import { t } from '../../i18n/scope/system'

/**
 * The problems page's own parts: the interpretation read as what happened and
 * what fixed it, the rules written from a problem, and the form that writes
 * one. A rule is never made from a problem on its own.
 */

export function isOpen(v: Vision): boolean {
  return (v.row.status ?? 'open') !== 'resolved'
}

const RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }

export function severityRank(v: Vision): number {
  return RANK[v.row.severity ?? ''] ?? 3
}


const TONE: Record<string, string> = {
  high: 'border-status-red/50 text-status-red',
  medium: 'border-status-amber/50 text-status-amber',
  low: 'border-border-default text-tertiary',
}

export function SeverityChip({ severity, compact = false }: { severity?: string | null; compact?: boolean }) {
  if (!severity) return null
  if (compact) {
    const dot = severity === 'high' ? 'bg-status-red' : severity === 'medium' ? 'bg-status-amber' : 'bg-border-strong'
    return <span role="img" className={`h-6 w-6 rounded-pill shrink-0 ${dot}`} title={severity} aria-label={severity} />
  }
  return (
    <span className={`inline-flex items-center h-20 px-6 rounded-pill border text-10 font-mono shrink-0 ${TONE[severity] ?? TONE.low}`}>
      {severity}
    </span>
  )
}

/** The first paragraph is what happened; the paragraphs after it are what fixed it. */
function splitLearned(text: string): { happened: string; fixed: string } {
  const parts = (text ?? '').trim().split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
  return { happened: parts[0] ?? '', fixed: parts.slice(1).join('\n\n') }
}

export function Learned({ text }: { text: string }) {
  const { happened, fixed } = splitLearned(text)
  return (
    <div className="flex flex-col gap-12">
      <div className="flex flex-col gap-4">
        <span className={LABEL}>{t('What happened')}</span>
        <InterpretationText text={happened} />
      </div>
      {fixed && (
        <div className="flex flex-col gap-4 border-l-2 border-status-green/60 pl-12">
          <span className={`${LABEL} text-status-green`}>{t('What fixed it')}</span>
          <InterpretationText text={fixed} />
        </div>
      )}
    </div>
  )
}

/**
 * A problem an agent posted before #problem existed may have no L2, only the
 * attempts in L3. Those attempts are what was learned, so they are shown.
 */
export function PostedAttempts({ id }: { id: string }) {
  const q = useQuery({
    queryKey: ['problems', 'layers', id],
    queryFn: async ({ signal }) => {
      return getJson<EntryDetailLike>(`/api/problems/${id}`, signal)
    },
    staleTime: 60_000,
  })
  const tried = entryText(q.data).list
  if (q.isLoading) return null
  if (!tried.length) return <p className="text-13 text-tertiary">{t('Nothing was written about it yet.')}</p>
  return (
    <div className="flex flex-col gap-4">
      <span className={LABEL}>{t('What was tried')}</span>
      <ul className="list-disc pl-20 flex flex-col gap-2 text-13 text-primary leading-relaxed">
        {tried.map((t, i) => <li key={i} className="break-words">{t}</li>)}
      </ul>
    </div>
  )
}

/** The rules written from this problem, and Create rule. */
export function RulesFromIt({ problem, rules }: { problem: Vision; rules: Vision[] }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [title, setTitle] = useState('')
  const make = useRuleFromProblem()
  const id = problem.row.id
  const close = () => { setOpen(false); setText(''); setTitle('') }
  const save = () =>
    make.mutate(
      { problemId: id, text: text.trim(), title: title.trim() },
      {
        onSuccess: () => { toast.success(t('Rule created')); close() },
        onError: (e) => toast.error(String((e as Error).message)),
      },
    )

  return (
    <section aria-label={t('Rules from it')} className="flex flex-col gap-6 rounded-input bg-elevated/60 px-12 py-8">
      <div className="flex items-center gap-8">
        <span className={LABEL}>{t('Rules from it')}</span>
        <span className="text-11 font-mono text-tertiary tabular">{rules.length}</span>
        {!open && (
          <button type="button" onClick={() => setOpen(true)}
            className="ml-auto inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand">
            <Plus size={12} aria-hidden /> {t('Create rule')}
          </button>
        )}
      </div>
      {rules.length === 0 && !open && (
        <p className="text-12 text-tertiary">{t('No rules from this problem yet. Create rule writes one linked to it.')}</p>
      )}
      {rules.map((r) => (
        <div key={r.row.id} className="flex items-center gap-8 min-w-0">
          <span className="text-13 text-primary truncate">{cleanTitle(r.row.l1)}</span>
          <span className="text-10 font-mono text-tertiary shrink-0">{r.row.id}</span>
          {r.row.auto === 'yes' && (
            <span className="inline-flex items-center h-20 px-6 rounded-pill border border-brand/50 text-brand text-10 font-mono shrink-0">
              {t('for all agents')}
            </span>
          )}
          {r.row.status === 'off' && <span className="text-10 font-mono text-tertiary shrink-0">{t('off')}</span>}
        </div>
      ))}
      {open && (
        <div className="flex flex-col gap-8 pt-4">
          <div className="flex flex-col gap-3">
            <label className={LABEL} htmlFor={`rule-${id}`}>{t('Rule')}</label>
            <textarea
              id={`rule-${id}`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              placeholder={t('Write the rule')}
              className={`${FIELD} font-sans text-13 leading-relaxed resize-y`}
            />
          </div>
          <div className="flex flex-col gap-3">
            <label className={LABEL} htmlFor={`rule-title-${id}`}>{t('Title')}</label>
            <input
              id={`rule-title-${id}`}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('Optional')}
              maxLength={200}
              className={FIELD}
            />
          </div>
          <div className="flex items-center gap-8">
            <Button variant="primary" size="sm" onClick={save} disabled={make.isPending || !text.trim()}>
              {t('Save')}
            </Button>
            <Button variant="ghost" size="sm" onClick={close}>{t('Cancel')}</Button>
          </div>
        </div>
      )}
    </section>
  )
}
