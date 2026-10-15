import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { ChevronDown } from 'lucide-react'

import { LABEL } from '../ui'
import { Badge } from '../primitives/Badge'
import { Row } from '../primitives/Row'
import { formatHours } from '../../utils/format'
import { L2Rail, L3Block, L4Block, NestedDrawer } from './standupDetail'
import { useStandupDetail } from './useStandupDetail'
import type { FetchStandupDetail, StandupRow } from './types'
import { t } from '../../i18n/scope/shell'

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

interface StandupTimelineRowProps {
  row: StandupRow
  isFresh: boolean
  expanded: boolean
  fetchDetail: FetchStandupDetail
  onToggle: () => void
  onCollapse: () => void
}

export function StandupTimelineRow({
  row,
  isFresh,
  expanded,
  fetchDetail,
  onToggle,
  onCollapse,
}: StandupTimelineRowProps) {
  const { detail, retry: onRetry } = useStandupDetail(row.id, expanded, fetchDetail)
  const isCross = row.project === '_all'
  const authorLabel =
    row.agent_id === null || row.agent_id === '' || row.agent_id === 'operator'
      ? 'human'
      : 'agent'
  const projectLabel = isCross ? '_all · cross' : row.project || '—'

  // Esc collapses when focus is anywhere in the expanded region.
  const onExpandedKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onCollapse()
    }
  }

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`standup-detail-${row.id}`}
        className="w-full text-left flex items-start gap-12 px-16 py-12 hover:bg-hover transition-colors duration-fast ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-brand motion-safe:transition-colors"
      >
        {/* Left rail: date stamp + fresh dot */}
        <div className="shrink-0 flex flex-col items-start gap-4" style={{ width: 68 }}>
          <span className="text-11 font-mono tabular text-tertiary">
            {row.created_date}
          </span>
          {row.created_time && (
            <span className="text-11 font-mono tabular text-tertiary opacity-70">
              {row.created_time}
            </span>
          )}
          {isFresh && (
            <span
              className="inline-flex items-center gap-4 text-10 font-mono uppercase mt-2"
              style={{ color: 'var(--brand)', letterSpacing: '0.08em' }}
              aria-label={t('Most recent standup')}
            >
              <span
                aria-hidden
                className="inline-block w-6 h-6 rounded-pill"
                style={{
                  background: 'var(--brand)',
                  boxShadow: '0 0 6px var(--brand-glow)',
                }}
              />
              fresh
            </span>
          )}
        </div>

        {/* Middle: project chip + L1 headline + microstats */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-8 mb-4 flex-wrap">
            <Badge tone={isCross ? 'active' : 'info'}>{projectLabel}</Badge>
            <span
              className={LABEL}
            >
              <span className={authorLabel === 'human' ? 'text-brand' : 'text-secondary'}>
                {row.agent_id || 'operator'}
              </span>
              <span className="opacity-50 mx-4">·</span>
              {authorLabel}
            </span>
          </div>
          <div
            className={`text-13 text-primary leading-snug ${expanded ? '' : 'line-clamp-2'}`}
          >
            {row.l1 || '—'}
          </div>
          <Microstats row={row} />
        </div>

        {/* Right rail: chevron + expand label */}
        <div className="shrink-0 flex items-center gap-8 mt-2">
          <span className="text-11 font-mono text-tertiary hidden sm:inline">
            {expanded ? 'hide' : 'expand'}
          </span>
          <ChevronDown
            size={14}
            aria-hidden="true"
            className={`text-tertiary motion-safe:transition-transform motion-safe:duration-fast ease-out ${
              expanded ? 'rotate-180' : ''
            }`}
          />
        </div>
      </button>

      {expanded && (
        <div
          id={`standup-detail-${row.id}`}
          onKeyDown={onExpandedKeyDown}
          className="px-16 pb-16 pl-[92px] pt-4 flex flex-col gap-12 text-13 text-secondary bg-elevated"
        >
          {/* L2 — since-last prose */}
          <L2Rail detail={detail} onRetry={onRetry} />

          {/* Nested L3/L4 drawers */}
          <div className="flex flex-col gap-8">
            <NestedDrawer
              label={t('Show open goals')}
              labelOpen={t('Hide open goals')}
              disabled={detail?.status !== 'ready'}
            >
              <L3Block detail={detail} />
            </NestedDrawer>

            <NestedDrawer
              label={t('Show today\'s plan')}
              labelOpen={t('Hide today\'s plan')}
              disabled={detail?.status !== 'ready'}
            >
              <L4Block detail={detail} />
            </NestedDrawer>
          </div>

          {/* Metadata footer — always visible when expanded */}
          <Row gap="12" wrap>
            <MetaCell label="ID" value={row.id} mono />
            <MetaCell label={t('Project')} value={row.project || '—'} mono />
            <MetaCell label={t('Author')} value={row.agent_id || 'operator'} mono />
            <MetaCell label={t('Date')} value={row.created_date} mono />
            {row.created_time && (
              <MetaCell label={t('Time')} value={row.created_time} mono />
            )}
          </Row>
        </div>
      )}
    </li>
  )
}

// ---------------------------------------------------------------------------
// Microstats · `<N> open · <N> closed · <N> blockers · <X>h today`
// Mirrors editorial `microstatsHtml`. Zeros render — the shape of the day
// carries signal even when a count is 0.
// ---------------------------------------------------------------------------

function Microstats({ row }: { row: StandupRow }) {
  const hoursStr = formatHours(row.hours_today)
  const hasBlockers = row.blockers_n > 0
  return (
    <div className="text-11 text-tertiary font-mono mt-6 tabular flex items-center gap-6 flex-wrap">
      <span aria-hidden className="opacity-50">·</span>
      <span className="text-secondary">
        <span className="text-primary tabular font-semibold">{row.goals_open_n}</span> open
      </span>
      <span aria-hidden className="opacity-50">·</span>
      <span className="text-secondary">
        <span className="text-primary tabular font-semibold">{row.goals_closed_n}</span> closed
      </span>
      <span aria-hidden className="opacity-50">·</span>
      <span className={hasBlockers ? 'text-status-red' : 'text-secondary'}>
        <span
          className={`tabular font-semibold ${
            hasBlockers ? 'text-status-red' : 'text-primary'
          }`}
        >
          {row.blockers_n}
        </span>{' '}
        blocker{row.blockers_n === 1 ? '' : 's'}
      </span>
      <span aria-hidden className="opacity-50">·</span>
      <span className="text-secondary">
        <span className="tabular font-semibold" style={{ color: 'var(--brand)' }}>
          {hoursStr}h
        </span>{' '}
        today
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

function MetaCell({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <span className={LABEL}>
        {label}
      </span>
      <span
        className={`text-12 text-primary ${mono ? 'font-mono tabular' : ''} truncate max-w-[240px]`}
      >
        {value}
      </span>
    </div>
  )
}
