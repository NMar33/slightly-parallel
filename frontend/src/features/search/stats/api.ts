/**
 * The one fetch the numbers need.
 *
 * `GET /api/search/overview` was counted when the index was built, so with
 * no word it is a lookup, not work. With `?q=` it answers the same shape
 * over the rows that match, plus `near`.
 *
 * The sheet always holds the whole index as well, because a word's days
 * only mean something against every day.
 */

import { getJson } from '../../../lib/getJson'

export type Pair = [string, number]

interface Overview {
  query: string
  rows: number
  kinds: Pair[]
  days: Pair[]
  projects: Pair[]
  turn_lengths: Array<{ bucket: string; n: number }>
  words_said: number
  chats: Pair[]
  roles: Pair[]
  words: Array<{ word: string; n: number }>
  near?: Array<{ word: string; n: number; lift: number }>
}

const EMPTY: Overview = {
  query: '',
  rows: 0,
  kinds: [],
  days: [],
  projects: [],
  turn_lengths: [],
  words_said: 0,
  chats: [],
  roles: [],
  words: [],
}

export async function fetchOverview(q: string, signal?: AbortSignal): Promise<Overview> {
  const url = q ? `/api/search/overview?q=${encodeURIComponent(q)}` : '/api/search/overview'
  const data = await getJson<Partial<Overview>>(url, signal)
  return { ...EMPTY, ...data, query: data.query ?? q }
}
