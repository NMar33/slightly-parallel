import { useMemo, useState } from 'react'
import { Pencil, Sparkles } from 'lucide-react'
import { Panel } from '../Panel'
import { Segmented } from '../Segmented'
import type { SnapshotDecision } from '../../lib/api'
import { t } from '../../i18n/scope/shell'

/**
 * DecisionLogPanel — compact decision log used in the CEO Overview.
 *
 * Distinct from `components/DecisionLog` (which is the full search/filter view
 * mounted on the /decisions page). This is dense, read-only, purpose-built
 * for the "Command Center" dashboard.
 *
 * Each row: [source icon] [decision + rationale + tag] [project chip] [date]
 * Icon color encodes source:
 *   - explicit (pencil) → status-info
 *   - auto     (spark)  → status-amber
 *
 * Cyrillic-safe (rationale + text preserved verbatim).
 */

interface DecisionLogPanelProps {
  decisions: SnapshotDecision[]
  className?: string
}

type Filter = 'all' | 'explicit' | 'auto'

export function DecisionLogPanel({
  decisions,
  className = '',
}: DecisionLogPanelProps) {
  const [filter, setFilter] = useState<Filter>('all')

  const visible = useMemo(() => {
    if (filter === 'all') return decisions
    return decisions.filter((d) => (d.source || 'explicit') === filter)
  }, [decisions, filter])

  return (
    <Panel
      title={t('Decision Log')}
      className={className}
      bodyPadding="tight"
      tabs={
        <Segmented label={t('Decision source')} shape="pill" value={filter} onChange={setFilter}
          options={[['all', t('all')], ['explicit', t('explicit'), t('Written by a person')], ['auto', t('auto'), t('Inferred by an agent')]] as const} />
      }
    >
      {visible.length === 0 ? (
        <div className="py-24 text-center text-12 text-tertiary">
          {t('No decisions logged yet.')}
        </div>
      ) : (
        <ul role="list" className="divide-y divide-border-subtle">
          {visible.map((d) => (
            <DecisionRow key={d.id} decision={d} />
          ))}
        </ul>
      )}
    </Panel>
  )
}

function DecisionRow({ decision }: { decision: SnapshotDecision }) {
  const source = (decision.source || 'explicit') as 'explicit' | 'auto'
  const Icon = source === 'explicit' ? Pencil : Sparkles
  const iconTone = source === 'explicit' ? 'var(--status-info)' : 'var(--status-amber)'
  const badgeText = source === 'explicit' ? t('explicit') : t('auto-detected')

  return (
    <li
      className="grid gap-12 py-12 px-4 items-start"
      style={{ gridTemplateColumns: '24px minmax(0,1fr) auto' }}
    >
      <span
        aria-hidden
        className="w-24 h-24 rounded-input grid place-items-center shrink-0"
        style={{
          background: 'var(--bg-hover)',
          color: iconTone,
        }}
      >
        <Icon size={12} />
      </span>
      <div className="min-w-0">
        <div className="text-13 text-primary leading-snug">
          {decision.decision_text}
        </div>
        {decision.rationale && (
          <div className="text-12 text-secondary mt-2 leading-snug">
            {decision.rationale}
          </div>
        )}
        <div className="flex items-center gap-8 mt-4">
          <span
            className="inline-block px-6 py-1 rounded-input text-11 font-mono uppercase text-tertiary"
            style={{ background: 'var(--bg-hover)', letterSpacing: '0.05em' }}
          >
            {badgeText}
          </span>
          {decision.project && (
            <span
              className="inline-block px-6 py-1 rounded-input text-11 font-mono uppercase text-tertiary"
              style={{ background: 'var(--bg-hover)', letterSpacing: '0.05em' }}
            >
              {decision.project}
            </span>
          )}
          {decision.agent_id && (
            <span className="text-11 font-mono text-tertiary truncate">
              {decision.agent_id}
            </span>
          )}
        </div>
      </div>
      <span className="text-11 font-mono tabular text-tertiary whitespace-nowrap self-start">
        {decision.created_date}
      </span>
    </li>
  )
}

