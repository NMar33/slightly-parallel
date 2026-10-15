import { todayYYMMDD } from '../../utils/dateUtils'
import { useMemo } from 'react'
import { AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'

import { fail } from '../../lib/getJson'
import { KeptBook, KeptSection, type BookCtx } from '../kept/Book'
import { LABEL } from '../promptlib/taskstyle'
import { jump } from '../visions/chapters'
import { cleanTitle, dateOf, useKept, useSetFields, type Vision } from '../visions/data'
import { PROBLEMS_GUIDE } from '../visions/guides'
import { stamp } from '../visions/parts'
import {
  Learned, PostedAttempts, RulesFromIt, SeverityChip, isOpen, severityRank,
} from './parts'
import { t } from '../../i18n/scope/system'

/**
 * Problems — what was learned. A problem is worth keeping after it is
 * fixed: what happened, what fixed it, and the rules the operator wrote on
 * its basis. Open problems stay in view in a strip under the header. A rule
 * is never made from a problem on its own — each problem has Create rule,
 * and the rule points back at it. The page is the kept book
 * (features/kept/Book) with those parts.
 */
export function ProblemsMemory() {
  const { visions: problems, loading, error, near, complete } = useKept('problem')
  // The rules only for their link back to a problem: no record is read.
  const { visions: rules } = useKept('rule', '', { details: false })
  const rulesByProblem = useMemo(() => {
    const m = new Map<string, Vision[]>()
    for (const r of rules) {
      const pid = r.row.related_incident
      if (pid) m.set(pid, [...(m.get(pid) ?? []), r])
    }
    return m
  }, [rules])

  return (
    <KeptBook kind="problem" title={t('Problems')} icon={AlertTriangle} guide={PROBLEMS_GUIDE}
      entries={problems} loading={loading} error={error} near={near} complete={complete}
      empty={t('No problems yet. Add #problem to a message to keep it.')}
      modes={[['month', 'month'], ['tag', 'tag'], ['project', 'project'], ['set', 'sets']]} defaultMode="month"
      mark={(v) => isOpen(v) && <span role="img" className="h-6 w-6 rounded-pill bg-status-amber shrink-0 self-center" aria-label={t('open')} />}
      belowGuide={(shown) => <OpenNow shown={shown} />}
      section={(v, ctx) => <ProblemSection v={v} ctx={ctx} rules={rulesByProblem.get(v.row.id) ?? []} />} />
  )
}

/** The open problems, worst first, one click from each. */
function OpenNow({ shown }: { shown: Vision[] }) {
  const open = shown.filter(isOpen)
    .sort((a, b) => severityRank(a) - severityRank(b) || dateOf(b.row).getTime() - dateOf(a.row).getTime())
  if (!open.length) return null
  return (
    <nav aria-label={t('Open now')} className="rounded-card border border-status-amber/40 bg-status-amber/5 px-12 py-8 flex items-center gap-8 flex-wrap">
      <span className={`${LABEL} text-status-amber`}>{t('Open now')}</span>
      <span className="text-11 font-mono text-tertiary tabular">{open.length}</span>
      {open.map((v) => (
        <button key={v.row.id} type="button" onClick={() => jump(v.row.id)}
          className="inline-flex items-center gap-6 h-24 px-8 rounded-input border border-border-subtle bg-surface text-12 text-primary hover:border-brand hover:text-brand max-w-[360px]">
          <SeverityChip severity={v.row.severity} compact />
          <span className="truncate">{cleanTitle(v.row.l1)}</span>
        </button>
      ))}
    </nav>
  )
}

function ProblemSection({ v, ctx, rules }: { v: Vision; ctx: BookCtx; rules: Vision[] }) {
  const fields = useSetFields('problem')
  const open = isOpen(v)
  const toggle = () => fields.mutate(
    { id: v.row.id, ...(open ? { status: 'resolved', resolved_date: todayYYMMDD() } : { status: 'open', resolved_date: '' }) },
    { onSuccess: () => toast.success(open ? t('Marked as resolved') : t('Reopened')), onError: fail },
  )
  return (
    <KeptSection v={v} kind="problem" ctx={ctx}
      status={<>
        <span className={`text-11 font-mono shrink-0 ${open ? 'text-status-amber' : 'text-status-green'}`}>
          {open ? t('Open') : v.row.resolved_date ? t('Resolved {date}', { date: stamp(v.row.resolved_date) }) : t('Resolved')}
        </span>
        <SeverityChip severity={v.row.severity} />
      </>}
      actions={
        <button type="button" onClick={toggle} disabled={fields.isPending}
          className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand disabled:opacity-40">
          {open ? t('Resolve') : t('Reopen')}
        </button>
      }
      renderBody={(text) => <Learned text={text} />}
      emptyBody={v.kept ? undefined : <PostedAttempts id={v.row.id} />}
      after={<RulesFromIt problem={v} rules={rules} />} />
  )
}
