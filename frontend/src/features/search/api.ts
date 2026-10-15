/**
 * One fetch, the whole answer.
 *
 * `GET /api/search` answers in milliseconds and holds 2,238 rows, so the
 * page asks once at the ceiling and narrows in the browser. `counts` and
 * `total` are over every match, not over the page that came back.
 */

import { getJson } from '../../lib/getJson'
import type { SearchHit } from '../../lib/searchHits'

export interface SearchAnswer {
  query: string
  hits: SearchHit[]
  counts: Record<string, number>
  total: number
}

export const FETCH_LIMIT = 1000

export async function fetchEverything(q: string, signal?: AbortSignal): Promise<SearchAnswer> {
  const url = `/api/search?q=${encodeURIComponent(q)}&limit=${FETCH_LIMIT}`
  const data = await getJson<Partial<SearchAnswer>>(url, signal)
  return {
    query: data.query ?? q,
    hits: data.hits ?? [],
    counts: data.counts ?? {},
    total: data.total ?? (data.hits?.length ?? 0),
  }
}
