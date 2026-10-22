import { useQuery } from '@tanstack/react-query'

import type { FetchStandupDetail, StandupDetail } from './types'
import { t } from '../../i18n/scope/shell'

/** One row's L2/L3/L4 as the row draws it. */
export interface DetailState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  detail?: StandupDetail
  error?: string
}

/**
 * Hydrate one row's L2/L3/L4 once it is opened. The query cache keeps it,
 * so re-opening is instant; a change on the server (the freshness stamp)
 * reads it again. A failed read keeps the row open with a retry.
 */
export function useStandupDetail(id: string, open: boolean, fetchDetail: FetchStandupDetail) {
  const q = useQuery({
    queryKey: ['standups', 'detail', id],
    queryFn: ({ signal }) => fetchDetail(id, signal),
    enabled: open,
    staleTime: 5_000,
  })
  const detail: DetailState | undefined = q.data && !(q.isError && q.isFetching)
    ? { status: 'ready', detail: q.data }
    : q.isFetching ? { status: 'loading' }
    : q.isError ? { status: 'error', error: q.error instanceof Error ? q.error.message : t('Unknown error.') }
    : undefined
  return { detail, retry: () => { void q.refetch() } }
}
