import { getJson } from '../../lib/getJson'
import type { EntryDetailLike } from '../../lib/entryText'
import { LABEL } from '../ui'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Pencil, Sparkles, ChevronRight, X } from 'lucide-react'
import { Card } from '../primitives/Card'
import { Row } from '../primitives/Row'
import { Chip } from '../primitives/Chip'
import { Badge } from '../primitives/Badge'
import { Input } from '../primitives/Input'
import { EmptyState, LoadingSkeleton } from '../states'
import type { Decision, DecisionSource } from './types'
import { t } from '../../i18n/scope/shell'

/**
 * C12 — Decision Log.
 *
 * PostHog-style filter chips over 32px dense rows.
 * `showProjectColumn` = true for the cross-project view (/decisions).
 *
 * Cyrillic-safe: substring match uses `String.prototype.toLocaleLowerCase()`
 * on both haystack and needle after `.normalize('NFC')` so composed vs
 * decomposed cyrillic ("рекогниция", "матолимп") both match.
 */

interface DecisionLogProps {
  decisions: Decision[]
  showProjectColumn?: boolean
  /** When present, hide the internal search input (search wired externally). */
  externalQuery?: string
  emptyHint?: ReactNode
  className?: string
}

type SourceFilter = 'all' | DecisionSource

interface DateRange {
  from?: string // YYMM-DD (lex-sortable)
  to?: string
}

const SOURCE_OPTIONS: { value: SourceFilter; label: string }[] = [
  { value: 'all', label: t('All sources') },
  { value: 'explicit', label: t('Explicit') },
  { value: 'auto', label: t('Auto') },
]

function normalize(s: string): string {
  return s.normalize('NFC').toLocaleLowerCase()
}

function includesCI(haystack: string, needle: string): boolean {
  if (!needle) return true
  return normalize(haystack).includes(normalize(needle))
}

function unique<T>(xs: T[]): T[] {
  return Array.from(new Set(xs))
}

export function DecisionLog({
  decisions,
  showProjectColumn = false,
  externalQuery,
  emptyHint,
  className = '',
}: DecisionLogProps) {
  const [internalQuery, setInternalQuery] = useState('')
  const query = externalQuery ?? internalQuery

  const [projectFilter, setProjectFilter] = useState<Set<string>>(new Set())
  const [agentFilter, setAgentFilter] = useState<Set<string>>(new Set())
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [dateRange, setDateRange] = useState<DateRange>({})
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // The list changed on the server (an interpretation rewritten): the
  // drilled bodies are stale too. Structural sharing keeps the prop
  // identical while nothing changed, so this fires only on a real change,
  // and the epoch in the drill's key makes an open drill fetch again.
  const [cacheEpoch, setCacheEpoch] = useState(0)
  useEffect(() => { _detailCache.clear(); setCacheEpoch((e) => e + 1) }, [decisions])

  const projects = useMemo(
    () =>
      unique(decisions.map(d => d.project).filter((p): p is string => !!p)).sort(),
    [decisions],
  )
  const agents = useMemo(
    () => unique(decisions.map(d => d.agent_id)).filter(Boolean).sort(),
    [decisions],
  )

  const filtered = useMemo(() => {
    return decisions.filter(d => {
      if (projectFilter.size > 0 && (!d.project || !projectFilter.has(d.project))) return false
      if (agentFilter.size > 0 && !agentFilter.has(d.agent_id)) return false
      if (sourceFilter !== 'all' && d.source !== sourceFilter) return false
      if (dateRange.from && d.created_date < dateRange.from) return false
      if (dateRange.to && d.created_date > dateRange.to) return false
      if (query) {
        const hay = [
          d.decision_text,
          d.rationale,
          d.agent_id,
          d.project ?? '',
          (d.tags ?? []).join(' '),
        ].join(' ')
        if (!includesCI(hay, query)) return false
      }
      return true
    })
  }, [decisions, projectFilter, agentFilter, sourceFilter, dateRange, query])

  const toggle = (set: Set<string>, val: string, setter: (s: Set<string>) => void) => {
    const next = new Set(set)
    if (next.has(val)) next.delete(val)
    else next.add(val)
    setter(next)
  }

  const activeFilterCount =
    projectFilter.size +
    agentFilter.size +
    (sourceFilter !== 'all' ? 1 : 0) +
    (dateRange.from ? 1 : 0) +
    (dateRange.to ? 1 : 0)

  const clearAll = () => {
    setProjectFilter(new Set())
    setAgentFilter(new Set())
    setSourceFilter('all')
    setDateRange({})
    if (externalQuery === undefined) setInternalQuery('')
  }

  return (
    <section className={`flex flex-col gap-16 ${className}`.trim()} aria-label={t('Decision log')}>
      {/* Filter bar */}
      <Card padding="sm">
        <div className="flex flex-col gap-12">
          {externalQuery === undefined && (
            <Input
              placeholder={t('Search decisions…')}
              value={internalQuery}
              onChange={e => setInternalQuery(e.currentTarget.value)}
              aria-label={t('Search decisions')}
            />
          )}

          <Row gap="8" wrap>
            {showProjectColumn && projects.length > 0 && (
              <FilterGroup label={t('Project')}>
                {projects.map(p => (
                  <Chip
                    key={p}
                    active={projectFilter.has(p)}
                    onClick={() => toggle(projectFilter, p, setProjectFilter)}
                  >
                    {p}
                  </Chip>
                ))}
              </FilterGroup>
            )}

            {agents.length > 0 && (
              <FilterGroup label={t('Agent')}>
                {agents.slice(0, 12).map(a => (
                  <Chip
                    key={a}
                    active={agentFilter.has(a)}
                    onClick={() => toggle(agentFilter, a, setAgentFilter)}
                  >
                    {a}
                  </Chip>
                ))}
              </FilterGroup>
            )}

            <FilterGroup label={t('Source')}>
              {SOURCE_OPTIONS.map(opt => (
                <Chip
                  key={opt.value}
                  active={sourceFilter === opt.value}
                  onClick={() => setSourceFilter(opt.value)}
                >
                  {opt.label}
                </Chip>
              ))}
            </FilterGroup>

            <FilterGroup label={t('Date range')}>
              <DateInput
                value={dateRange.from ?? ''}
                onChange={v => setDateRange(r => ({ ...r, from: v || undefined }))}
                aria-label={t('From date YYMM-DD')}
                placeholder="YYMM-DD"
              />
              <span className="text-tertiary text-12">→</span>
              <DateInput
                value={dateRange.to ?? ''}
                onChange={v => setDateRange(r => ({ ...r, to: v || undefined }))}
                aria-label={t('To date YYMM-DD')}
                placeholder="YYMM-DD"
              />
            </FilterGroup>

            {activeFilterCount > 0 && (
              <button
                type="button"
                onClick={clearAll}
                className="inline-flex items-center gap-4 h-32 px-12 text-13 text-tertiary hover:text-primary transition-colors duration-fast ease-out"
              >
                <X size={12} aria-hidden="true" />
                Clear ({activeFilterCount})
              </button>
            )}
          </Row>

          <p className="text-12 text-tertiary tabular">
            Showing {filtered.length} of {decisions.length}
          </p>
        </div>
      </Card>

      {/* Rows */}
      {filtered.length === 0 ? (
        <DecisionsEmpty hasFilters={activeFilterCount > 0 || !!query} hint={emptyHint} />
      ) : (
        <ul
          role="list"
          className="flex flex-col rounded-card border border-border-default bg-surface overflow-hidden"
        >
          {filtered.map((d, i) => (
            <DecisionRow
              key={d.id}
              decision={d}
              showProjectColumn={showProjectColumn}
              expanded={expandedId === d.id}
              onToggle={() => setExpandedId(expandedId === d.id ? null : d.id)}
              isLast={i === filtered.length - 1}
              cacheEpoch={cacheEpoch}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-4 min-w-0">
      <span className={`${LABEL} mr-4`}>{label}</span>
      {children}
    </div>
  )
}

interface DateInputProps {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  'aria-label'?: string
}
function DateInput({ value, onChange, placeholder, ...rest }: DateInputProps) {
  return (
    <input
      type="text"
      inputMode="numeric"
      value={value}
      placeholder={placeholder}
      onChange={e => onChange(e.currentTarget.value)}
      className="h-32 w-[104px] rounded-input border border-border-default bg-surface px-8 text-13 text-primary tabular font-mono placeholder:text-tertiary focus:outline-none focus:border-brand transition-colors duration-fast ease-out"
      {...rest}
    />
  )
}

interface DecisionRowProps {
  decision: Decision
  showProjectColumn: boolean
  expanded: boolean
  onToggle: () => void
  isLast: boolean
  /** Bumped when the list changes: an open drill fetches its body again. */
  cacheEpoch: number
}

function DecisionRow({ decision, showProjectColumn, expanded, onToggle, isLast, cacheEpoch }: DecisionRowProps) {
  const SourceIcon = decision.source === 'explicit' ? Pencil : Sparkles
  const sourceLabel = decision.source === 'explicit' ? t('Human decision') : t('Agent-inferred decision')
  const borderCls = isLast ? '' : 'border-b border-border-subtle'

  return (
    <li className={borderCls}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`decision-detail-${decision.id}`}
        className="w-full text-left flex items-start gap-12 px-12 min-h-row py-8 hover:bg-hover transition-colors duration-fast ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        {/* Source icon */}
        <span
          className={`shrink-0 mt-4 ${
            decision.source === 'explicit' ? 'text-status-info' : 'text-status-amber'
          }`}
          title={sourceLabel}
          aria-label={sourceLabel}
        >
          <SourceIcon size={14} aria-hidden="true" />
        </span>

        {/* Middle: decision text + rationale */}
        <div className="flex-1 min-w-0">
          <div className={`text-13 text-primary ${expanded ? '' : 'truncate'}`}>
            {decision.decision_text}
          </div>
          {decision.rationale && (
            <div
              className={`text-12 text-secondary mt-4 ${
                expanded ? '' : 'truncate'
              }`}
            >
              {decision.rationale}
            </div>
          )}
        </div>

        {/* Right rail: date + agent (+ project) */}
        <div className="shrink-0 flex items-center gap-8">
          {showProjectColumn && decision.project && (
            <Badge tone="info">{decision.project}</Badge>
          )}
          <span className="text-12 text-tertiary tabular font-mono whitespace-nowrap">
            {decision.created_date}
          </span>
          <Badge tone="neutral">{decision.agent_id}</Badge>
          <ChevronRight
            size={14}
            aria-hidden="true"
            className={`text-tertiary transition-transform duration-fast ease-out ${
              expanded ? 'rotate-90' : ''
            }`}
          />
        </div>
      </button>

      {expanded && (
        <div
          id={`decision-detail-${decision.id}`}
          className="px-12 pb-12 pl-[38px] flex flex-col gap-8 text-13 text-secondary bg-elevated"
        >
          {decision.rationale && (
            <p>
              <span className={`${LABEL} mr-8`}>
                Rationale
              </span>
              {decision.rationale}
            </p>
          )}
          <DecisionDrill key={`${decision.id}:${cacheEpoch}`} decisionId={decision.id} />

          <Row gap="12" wrap>
            <MetaCell label="ID" value={decision.id} mono />
            <MetaCell label={t('Source')} value={decision.source} />
            <MetaCell label={t('Agent')} value={decision.agent_id} mono />
            {decision.related_goal_id && (
              <MetaCell label={t('Goal')} value={decision.related_goal_id} mono />
            )}
            <MetaCell label={t('Date')} value={decision.created_date} mono />
          </Row>
          {decision.tags && decision.tags.length > 0 && (
            <Row gap="4" wrap>
              {decision.tags.map(t => (
                <span
                  key={t}
                  className="text-11 text-tertiary bg-surface border border-border-subtle rounded-pill px-8 py-4"
                >
                  #{t}
                </span>
              ))}
            </Row>
          )}
        </div>
      )}
    </li>
  )
}

/**
 * DecisionDrill — lazy fetches /api/decisions/{id} on mount, renders L3
 * alternatives + L4 raw context inline. Per-id in-memory cache avoids
 * re-fetch across expand/collapse cycles. Crude size cap: cleared wholesale
 * past MAX_DRILL_CACHE entries so a long session can't grow it unbounded
 * (entries are otherwise never invalidated).
 */
const MAX_DRILL_CACHE = 200
const _detailCache = new Map<string, { l2: string; l3: string[]; l4: string }>()

function DecisionDrill({ decisionId }: { decisionId: string }) {
  const cached = _detailCache.get(decisionId) ?? null
  const [state, setState] = useState<
    | { kind: 'loading' }
    | { kind: 'ok'; l2: string; l3: string[]; l4: string }
    | { kind: 'err'; msg: string }
  >(cached ? { kind: 'ok', ...cached } : { kind: 'loading' })
  const [openL3, setOpenL3] = useState(true)
  const [openL4, setOpenL4] = useState(false)

  useEffect(() => {
    if (cached) return
    let cancelled = false
    setState({ kind: 'loading' })
    // The lens detail of a decision: its paragraph, alternatives and excerpt.
    getJson<EntryDetailLike>(`/api/decisions/${encodeURIComponent(decisionId)}`)
      .then(data => {
        if (cancelled) return
        const payload = {
          l2: String(data?.l2 ?? ''),
          l3: Array.isArray(data?.l3) ? data.l3.map(String) : [],
          l4: String(data?.l4 ?? ''),
        }
        if (_detailCache.size >= MAX_DRILL_CACHE) _detailCache.clear()
        _detailCache.set(decisionId, payload)
        setState({ kind: 'ok', ...payload })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setState({ kind: 'err', msg: e instanceof Error ? e.message : String(e) })
      })
    return () => {
      cancelled = true
    }
  }, [decisionId, cached])

  if (state.kind === 'loading') {
    return (
      <LoadingSkeleton variant="text" count={2} label={t('Loading the detail')} />
    )
  }
  if (state.kind === 'err') {
    return (
      <div className="text-12 text-error">
        Couldn't load detail: {state.msg}
      </div>
    )
  }
  const hasL3 = state.l3.length > 0
  const hasL4 = !!state.l4.trim()
  if (!hasL3 && !hasL4) return null
  return (
    <div className="flex flex-col gap-8">
      {hasL3 && (
        <div>
          <button
            type="button"
            onClick={() => setOpenL3(v => !v)}
            className="text-11 uppercase tracking-wide text-brand hover:text-brand-hover"
          >
            {openL3 ? '▾' : '▸'} Alternatives considered ({state.l3.length})
          </button>
          {openL3 && (
            <ul className="mt-4 pl-16 flex flex-col gap-4 list-disc marker:text-tertiary">
              {state.l3.map((line, i) => (
                <li key={i} className="text-13 text-secondary">
                  {line}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {hasL4 && (
        <div>
          <button
            type="button"
            onClick={() => setOpenL4(v => !v)}
            className="text-11 uppercase tracking-wide text-brand hover:text-brand-hover"
          >
            {openL4 ? '▾' : '▸'} Raw context
          </button>
          {openL4 && (
            <pre className="mt-4 pl-16 text-12 text-secondary whitespace-pre-wrap font-mono">
              {state.l4}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

function MetaCell({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <span className={LABEL}>{label}</span>
      <span
        className={`text-12 text-primary ${mono ? 'font-mono tabular' : ''} truncate max-w-[240px]`}
      >
        {value}
      </span>
    </div>
  )
}

function DecisionsEmpty({ hasFilters, hint }: { hasFilters: boolean; hint?: ReactNode }) {
  return (
    <EmptyState
      title={hasFilters ? t('No decisions match these filters.') : t('No decisions yet.')}
      subtitle={
        hint ??
        (hasFilters
          ? t('Clear a filter or widen the date range.')
          : t('Agents log decisions as they work. A pencil marks one written by a person, a wand one an agent inferred.'))
      }
    />
  )
}

