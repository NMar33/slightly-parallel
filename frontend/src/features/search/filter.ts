/**
 * The filter line — clauses, facet counts, and the shape of the results.
 *
 * The page fetches one query at `limit=1000` and does every narrowing here,
 * in the browser. Nothing in this file touches the network or React, so the
 * counting and the narrowing can be tested on their own.
 *
 * A clause is one narrowing: a group and a value. Clauses in the same group
 * are an "or" — kind:task plus kind:scan keeps both. Clauses in different
 * groups are an "and". A facet's count is taken over the hits that every
 * *other* group's clauses already keep, so the number says what that cut
 * would buy before it is made.
 */

import type { SearchHit } from '../../lib/searchHits'
import { t } from '../../i18n/scope/system'

export type FacetGroup = 'kind' | 'project' | 'month' | 'where' | 'role'

const GROUPS: FacetGroup[] = ['kind', 'project', 'month', 'where', 'role']

export const GROUP_TITLE: Record<FacetGroup, string> = {
  kind: t('Kind'),
  project: t('Project'),
  month: t('Month'),
  where: t('Word sits in'),
  role: t('Who said it'),
}

export interface Clause {
  group: FacetGroup
  value: string
}

/** The value a hit shows in one group, or '' when the group does not apply. */
export function facetValue(hit: SearchHit, group: FacetGroup): string {
  switch (group) {
    case 'kind':
      return hit.kind
    case 'project':
      return hit.project || '(no project)'
    case 'month':
      return monthOf(hit.date) || '(no date)'
    case 'where':
      return hit.where
    case 'role':
      return hit.kind === 'turn' ? (hit.role ?? '') : ''
  }
}

/**
 * One month, written `YYYY-MM`, from either date format in the store.
 *
 * Entries carry `YYMM-DD` (`2609-21`); chats and agents used to carry
 * `YYYY-MM`. Both end up as `2026-09`, so the group holds one kind of label.
 */
export function monthOf(date: string): string {
  if (!date) return ''
  if (/^20\d{2}-\d{2}/.test(date)) return date.slice(0, 7)
  const m = /^(\d{2})(\d{2})/.exec(date)
  return m ? `20${m[1]}-${m[2]}` : ''
}

/** Does this hit survive every clause? */
function keeps(hit: SearchHit, clauses: Clause[]): boolean {
  for (const group of GROUPS) {
    const wanted = clauses.filter((c) => c.group === group)
    if (wanted.length === 0) continue
    const value = facetValue(hit, group)
    if (!value) return false
    if (!wanted.some((c) => c.value === value)) return false
  }
  return true
}

export function applyClauses(hits: SearchHit[], clauses: Clause[]): SearchHit[] {
  if (clauses.length === 0) return hits
  return hits.filter((h) => keeps(h, clauses))
}

/** How many matches are left after each clause, in the order they were pushed. */
export function narrowingChain(hits: SearchHit[], clauses: Clause[]): number[] {
  const chain = [hits.length]
  for (let i = 0; i < clauses.length; i += 1) {
    chain.push(applyClauses(hits, clauses.slice(0, i + 1)).length)
  }
  return chain
}

interface FacetValue {
  value: string
  count: number
  active: boolean
}

export interface Facet {
  group: FacetGroup
  /** How many hits the counts are taken over. */
  base: number
  values: FacetValue[]
}

/** Every group with its counted values, biggest first, ties by name. */
export function buildFacets(hits: SearchHit[], clauses: Clause[]): Facet[] {
  const facets: Facet[] = []
  for (const group of GROUPS) {
    const others = clauses.filter((c) => c.group !== group)
    const base = applyClauses(hits, others)
    const tally = new Map<string, number>()
    for (const h of base) {
      const value = facetValue(h, group)
      if (!value) continue
      tally.set(value, (tally.get(value) ?? 0) + 1)
    }
    if (tally.size === 0) continue
    const values = [...tally.entries()]
      .map(([value, count]) => ({
        value,
        count,
        active: clauses.some((c) => c.group === group && c.value === value),
      }))
      .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
    facets.push({ group, base: base.length, values })
  }
  return facets
}

export function toggleClause(clauses: Clause[], clause: Clause): Clause[] {
  const at = clauses.findIndex((c) => c.group === clause.group && c.value === clause.value)
  if (at === -1) return [...clauses, clause]
  return clauses.filter((_, i) => i !== at)
}

export function popClause(clauses: Clause[]): Clause[] {
  return clauses.slice(0, -1)
}

/* --------------------------------------------------------------------------
 * The results: entries as rows, turns gathered under their chat.
 * ----------------------------------------------------------------------- */

export interface ChatBlock {
  agentId: string
  /** The chat's title, as the turn hits carry it. */
  title: string
  project: string
  /** The newest day any matching turn in this chat was written. */
  date: string
  turns: SearchHit[]
  /** How many times the word sits in this chat's matching turns. */
  occurrences: number
}

interface Results {
  /** Every hit that is not a turn, in the order the server sent them. */
  entries: SearchHit[]
  /** Chats holding matching turns, newest chat first. */
  chats: ChatBlock[]
  /** Entry rows then turn rows, in the order they are drawn. */
  rows: SearchHit[]
}

export function buildResults(hits: SearchHit[]): Results {
  const entries = hits.filter((h) => h.kind !== 'turn')
  const byChat = new Map<string, ChatBlock>()
  for (const h of hits) {
    if (h.kind !== 'turn') continue
    const agentId = h.agent_id ?? h.id.split('#')[0]
    const block = byChat.get(agentId)
    if (block) {
      block.turns.push(h)
      block.occurrences += h.count ?? 1
      if (h.date > block.date) block.date = h.date
    } else {
      byChat.set(agentId, {
        agentId,
        title: h.title || agentId,
        project: h.project,
        date: h.date,
        turns: [h],
        occurrences: h.count ?? 1,
      })
    }
  }
  const chats = [...byChat.values()].sort(
    (a, b) => b.date.localeCompare(a.date) || a.agentId.localeCompare(b.agentId),
  )
  for (const c of chats) c.turns.sort((a, b) => (a.turn ?? 0) - (b.turn ?? 0))
  const rows = [...entries, ...chats.flatMap((c) => c.turns)]
  return { entries, chats, rows }
}

/* --------------------------------------------------------------------------
 * Marking the word.
 * ----------------------------------------------------------------------- */

interface MarkedPart {
  text: string
  hit: boolean
}

/**
 * The text cut into the matched word and the rest of it.
 *
 * The server matches a plain lower-cased substring, so this does the same:
 * every occurrence, case kept, no regular expression and no raw HTML.
 */
export function markParts(text: string, needle: string): MarkedPart[] {
  const word = needle.trim().toLowerCase()
  if (!text) return []
  if (!word) return [{ text, hit: false }]
  const hay = text.toLowerCase()
  const parts: MarkedPart[] = []
  let at = 0
  for (;;) {
    const found = hay.indexOf(word, at)
    if (found === -1) break
    if (found > at) parts.push({ text: text.slice(at, found), hit: false })
    parts.push({ text: text.slice(found, found + word.length), hit: true })
    at = found + word.length
  }
  if (at < text.length) parts.push({ text: text.slice(at), hit: false })
  return parts
}
