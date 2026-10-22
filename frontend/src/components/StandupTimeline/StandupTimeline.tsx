import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Panel } from '../Panel'
import { EmptyState } from '../states'
import { getJson } from '../../lib/getJson'
import { StandupTimelineRow } from './StandupTimelineRow'
import type {
  FetchStandupDetail,
  StandupDetail,
  StandupsListResponse,
} from './types'
import { t, tn } from '../../i18n/scope/shell'

/**
 * StandupTimeline — timeline of standup entries with fractal drill-down.
 *
 * SCAN-parallel layers (mirrors `/standup.html`):
 *   L1 = row headline (`l1`) + microstats (open/closed/blockers/hours) —
 *        always visible, glanceable at scroll speed.
 *   L2 = "since last" prose — hydrated on expand, inline paragraph.
 *   L3 = open-goal bullets — nested toggle inside expanded region.
 *   L4 = today's plan — nested toggle inside expanded region.
 *
 * The query cache keeps each opened row's detail, so re-opening is instant.
 * Loading uses skeletons; errors surface with retry. Keyboard: Enter/Space to
 * expand a row, Esc to collapse when focus is anywhere in the expanded region.
 *
 * The aggregate one-day card (`StandupPanel`) keeps its own surface — this
 * timeline is the multi-entry counterpart for the Overview page.
 */

// ---------------------------------------------------------------------------
// Fetchers — defaults hit the backend; tests inject stubs to avoid network.
// ---------------------------------------------------------------------------

const defaultFetchList = (signal?: AbortSignal) =>
  getJson<StandupsListResponse>('/api/standups', signal)

const defaultFetchDetail: FetchStandupDetail = (id, signal) =>
  getJson<StandupDetail>(`/api/standups/${encodeURIComponent(id)}`, signal)

const STANDUPS_QUERY_KEY = ['standups'] as const

interface StandupTimelineProps {
  /** Cap the number of rows rendered. Defaults to all fetched. */
  limit?: number
  /** Injectable list fetcher — defaults to `GET /api/standups`. */
  fetchList?: (signal?: AbortSignal) => Promise<StandupsListResponse>
  /** Injectable detail fetcher — defaults to `GET /api/standups/{id}`. */
  fetchDetail?: FetchStandupDetail
  className?: string
}

export function StandupTimeline({
  limit,
  fetchList = defaultFetchList,
  fetchDetail = defaultFetchDetail,
  className = '',
}: StandupTimelineProps) {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: STANDUPS_QUERY_KEY,
    queryFn: ({ signal }) => fetchList(signal),
    staleTime: 5_000,
  })

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const rows = useMemo(() => {
    const all = data?.standups ?? []
    return typeof limit === 'number' ? all.slice(0, limit) : all
  }, [data, limit])

  const handleToggle = (id: string) => setExpandedId((cur) => (cur === id ? null : id))

  const tabs = data ? (
    <span className="text-11 tabular text-tertiary font-mono">
      {typeof limit === 'number' && data.total > rows.length
        ? t('{n} of {total} entries', { n: rows.length, total: data.total })
        : tn(rows.length, '{n} entry', '{n} entries')}
    </span>
  ) : null

  return (
    <Panel
      title={t('Standup · Timeline')}
      tabs={tabs}
      bodyPadding="none"
      className={className}
      aria-label={t('Standup timeline')}
    >
      {isLoading && <ListSkeleton rows={3} />}

      {isError && (
        <ErrorBlock
          message={error instanceof Error ? error.message : t('Unknown error.')}
          onRetry={() => refetch()}
        />
      )}

      {!isLoading && !isError && rows.length === 0 && (
        <EmptyState
          bare
          title={t('No standups yet')}
          subtitle={t('The first agent of a new day asks to write one. Type #standup to write one now.')}
        />
      )}

      {!isLoading && !isError && rows.length > 0 && (
        <ul
          role="list"
          className="flex flex-col divide-y divide-border-subtle"
          data-testid="standup-timeline"
        >
          {rows.map((row, i) => (
            <StandupTimelineRow
              key={row.id}
              row={row}
              isFresh={i === 0}
              expanded={expandedId === row.id}
              fetchDetail={fetchDetail}
              onToggle={() => handleToggle(row.id)}
              onCollapse={() => setExpandedId(null)}
            />
          ))}
        </ul>
      )}
    </Panel>
  )
}

function ListSkeleton({ rows }: { rows: number }) {
  return (
    <ul
      role="status"
      aria-live="polite"
      aria-label={t('Loading standups')}
      className="flex flex-col divide-y divide-border-subtle"
    >
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} className="flex items-start gap-12 px-16 py-12">
          <div className="h-12 w-64 rounded-input bg-hover motion-safe:animate-pulse" />
          <div className="flex-1 flex flex-col gap-6">
            <div className="h-12 w-3/4 rounded-input bg-hover motion-safe:animate-pulse" />
            <div className="h-10 w-1/2 rounded-input bg-hover motion-safe:animate-pulse" />
          </div>
        </li>
      ))}
    </ul>
  )
}

function ErrorBlock({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div role="alert" className="p-16 flex flex-col gap-8">
      <p className="text-13 text-status-red">Couldn't load standups: {message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="self-start font-mono text-11 border border-status-red rounded-pill px-12 py-4 text-status-red hover:bg-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand motion-safe:transition-colors motion-safe:duration-fast ease-out"
      >
        Retry ↻
      </button>
    </div>
  )
}