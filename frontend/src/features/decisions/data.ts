import { dayStamp } from '../../utils/dateUtils'
import { entryText, type EntryDetailLike } from '../../lib/entryText'
import { keepPreviousData, useQueries, useQuery } from '@tanstack/react-query'

import { api, qk } from '../../lib/api'
import { getJson } from '../../lib/getJson'
import { agentLabel } from '../../utils/agentLabel'
import { firstLoad, settled } from '../visions/data'

/**
 * Decisions — what the decisions page reads.
 *
 * A decision holds four things, by name: the decision (what was chosen), why
 * (with what would make us undo it), the alternatives, and the excerpt of the
 * chat where it was decided. The server still answers with its storage keys;
 * `text` is read first when it is there.
 */

export interface DecisionRow {
  id: string
  created_date: string | null
  created_time: string | null
  project: string | null
  agent_id: string | null
  decision_text: string | null
  rationale: string | null
  alternatives_n?: number | null
  /** minor · normal · major: what undoing it would cost. An older row has none. */
  weight?: string | null
  files_affected_n?: number | null
  source?: string | null
  tags?: string | null
}

interface DecisionDetail extends EntryDetailLike {
  metadata: DecisionRow
}

type Verdict = 'chosen' | 'rejected' | 'other'

export interface Alternative {
  option: string
  verdict: Verdict
  reason: string
}

export interface Decision {
  row: DecisionRow
  decision: string
  why: string
  alternatives: Alternative[]
  excerpt: string
  /** The sentence of `why` that says what would undo it; '' when it says none. */
  undo: string
  who: string
}

const VERDICT_RE = /^(rejected|chosen|accepted|kept|superseded|not chosen)\b[:,;]?\s*/i

function verdictOf(word: string): Verdict {
  const w = word.toLowerCase()
  if (w.startsWith('chosen') || w.startsWith('accepted') || w.startsWith('kept')) return 'chosen'
  if (w.startsWith('rejected') || w.startsWith('not chosen') || w.startsWith('superseded')) return 'rejected'
  return 'other'
}

/**
 * One line of the alternatives, read for its shape. Agents wrote them three
 * ways: "option — rejected: reason", "Rejected: option — reason", and
 * "Alternative: option — rejected, reason". A line in no shape stays whole.
 */
function parseAlternative(line: string): Alternative {
  const text = line.trim().replace(/^alternative:\s*/i, '')
  const lead = text.match(VERDICT_RE)
  if (lead) {
    const rest = text.slice(lead[0].length)
    const [option, ...why] = rest.split(/\s[—–-]\s/)
    return { option: (option ?? rest).trim(), verdict: verdictOf(lead[1]!), reason: why.join(' — ').trim() }
  }
  const parts = text.split(/\s[—–]\s/)
  for (let i = 1; i < parts.length; i++) {
    const m = parts[i]!.match(VERDICT_RE)
    if (m) {
      const reason = [parts[i]!.slice(m[0].length), ...parts.slice(i + 1)].join(' — ').trim()
      return { option: parts.slice(0, i).join(' — ').trim(), verdict: verdictOf(m[1]!), reason }
    }
  }
  return { option: text, verdict: 'other', reason: '' }
}

const UNDO_RE = /\b(revisit|undo|reversal|reverse|revert|reconsider|would change)\b/i

/** The sentence that says what would make us undo it. Never invented. */
function undoOf(why: string): string {
  const sentences = why.split(/(?<=[.!?])\s+/)
  return sentences.find((s) => UNDO_RE.test(s))?.trim() ?? ''
}

/** The list of decisions: the rows alone (which projects, which days), no document read. */
export function useDecisionRows(project = '') {
  return useQuery({
    queryKey: ['decisions-page', project],
    queryFn: ({ signal }) =>
      getJson<{ decisions: DecisionRow[] }>(
        `/api/decisions?limit=500${project ? `&project=${encodeURIComponent(project)}` : ''}`, signal,
      ),
  })
}

const EVERY = () => true

/**
 * Every decision. `want` says which rows are on show and so need their own
 * document (the reasons, the alternatives, the excerpt); the rest are drawn
 * from the row — the decision and its rationale — until they are wanted.
 */
export function useDecisions(project = '', want: (row: DecisionRow) => boolean = EVERY) {
  const list = useDecisionRows(project)
  // The snapshot every page already holds — not a second read of it under another key.
  const agents = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal), staleTime: 60_000 })
  const rows = list.data?.decisions ?? []
  const details = useQueries({
    queries: rows.map((r) => ({
      queryKey: ['decisions-page', 'one', r.id],
      queryFn: ({ signal }: { signal: AbortSignal }) => getJson<DecisionDetail>(`/api/decisions/${r.id}`, signal),
      staleTime: 60_000,
      placeholderData: keepPreviousData,
      enabled: want(r),
    })),
  })
  const names = new Map((agents.data?.agents ?? []).map((a) => [a.agent_id, agentLabel(a)]))
  const decisions: Decision[] = rows.flatMap((r, i) => {
    const q = details[i]
    // A wanted row waits for its document; one not on show is drawn from the row.
    if (!q || (want(r) && !settled(q))) return []
    const d = q.data
    const held = entryText(d)
    const why = held.text.trim() || (r.rationale ?? '').trim()
    return [{
      row: d?.metadata ?? r,
      decision: (held.line || r.decision_text || '').trim(),
      why,
      alternatives: held.list.map(parseAlternative),
      excerpt: held.long.trim(),
      undo: undoOf(why),
      who: names.get(r.agent_id ?? '') ?? r.agent_id ?? '',
    }]
  })
  decisions.sort((a, b) => stampOf(b.row).localeCompare(stampOf(a.row)))
  return { decisions, loading: firstLoad(list.isLoading, details.filter((_, i) => want(rows[i]!))), error: list.isError }
}

function stampOf(r: DecisionRow): string {
  return `${r.created_date ?? ''} ${r.created_time ?? ''}`
}

/** A decision's day, in the one spelling (`dateUtils.dayStamp`). */
export function dayLabel(date: string | null): string {
  return dayStamp(date ?? '')
}

export function matches(d: Decision, q: string): boolean {
  if (!q) return true
  const hay = `${d.decision} ${d.why} ${d.alternatives.map((a) => `${a.option} ${a.reason}`).join(' ')} ${d.who} ${d.row.project ?? ''}`
    .normalize('NFC').toLocaleLowerCase()
  return q.normalize('NFC').toLocaleLowerCase().split(/\s+/).every((w) => hay.includes(w))
}
