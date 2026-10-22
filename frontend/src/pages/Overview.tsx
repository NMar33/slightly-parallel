/**
 * The Overview — the home page. The page itself is drawn by features/overview
 * (Home); this file holds its loading, empty and error states.
 */

import { useEffect } from 'react'

import { Card } from '../components/primitives'
import { EmptyState } from '../components/states'
import { api, type SnapshotResponse } from '../lib/api'
import { useOverviewData } from '../features/overview/data'
import { Home } from '../features/overview/home'
import { t } from '../i18n/scope/pages'

// Re-exported so the test file builds its fixture from the same shape the
// fetcher returns — one source of truth in lib/api.
export type { SnapshotResponse } from '../lib/api'

export interface OverviewProps {
  /** Test hook: bypass the network. Defaults to the shared `api.snapshot`. */
  fetcher?: (signal?: AbortSignal) => Promise<SnapshotResponse>
}

export function Overview({ fetcher = api.snapshot }: OverviewProps = {}) {
  useEffect(() => { document.title = `${t('Overview')} — Slightly Parallel` }, [])
  const data = useOverviewData(fetcher)
  const snap = data.snapshot
  if (data.loading && !snap) return <OverviewSkeleton />
  if (data.error && !snap) return <OverviewError error={data.error} onRetry={() => void data.refetch()} />
  if (!snap) return <OverviewEmpty />
  if (snap.projects.length === 0 && snap.kpi.projects === 0) return <OverviewEmpty />
  return <Home data={data} />
}

export default Overview

// -----------------------------------------------------------------------------
// Empty / Loading / Error
// -----------------------------------------------------------------------------

function OverviewSkeleton() {
  return (
    <div
      className="flex flex-col gap-16"
      data-testid="overview-skeleton"
      aria-busy="true"
    >
      <Card padding="md" className="animate-pulse">
        <div className="h-12 w-1/2 bg-hover rounded-input" />
      </Card>
      <div className="grid gap-16 grid-cols-1 lg:grid-cols-[1.5fr_1fr]">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} padding="md" className="animate-pulse">
            <div className="h-12 w-96 bg-hover rounded-input mb-12" />
            <div className="h-16 w-full bg-hover rounded-input mb-8" />
            <div className="h-16 w-3/4 bg-hover rounded-input" />
          </Card>
        ))}
      </div>
    </div>
  )
}

function OverviewEmpty() {
  return (
    <div data-testid="overview-empty">
      <EmptyState
        title={t('No projects yet')}
        subtitle={t('Integrate a project on the Setup page, then start an agent in it.')}
        cta={{ label: t('Open Setup'), href: '/setup' }}
      />
    </div>
  )
}

function OverviewError({
  error,
  onRetry,
}: {
  error: unknown
  onRetry: () => void
}) {
  const msg = error instanceof Error ? error.message : t('Unknown error.')
  return (
    <div data-testid="overview-error">
      <Card padding="lg">
        <div className="text-20 font-semibold text-primary mb-8">
          {t("Couldn't load overview")}
        </div>
        <p className="text-13 text-secondary mb-12">{msg}</p>
        <button
          type="button"
          onClick={onRetry}
          className="text-13 font-medium text-brand hover:text-brand-hover transition-colors duration-fast ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand rounded-input px-8 py-4"
        >
          {t('Retry')}
        </button>
      </Card>
    </div>
  )
}
