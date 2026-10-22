/**
 * The shape of `GET /api/architecture/state` — the wire, and nothing else.
 *
 * The ledger is a stream of per-scan answers to "what did you do to the
 * shape?": typed changes over a closed vocabulary (8 groups, 24 types)
 * plus a check receipt naming the groups that were looked at. Reading
 * and folding live in `ledger.ts`; this file is only what the server
 * sends, so both sides can be checked against one description.
 */

type Op = 'add' | 'change' | 'remove'

export type Change = {
  id: string
  created_date: string
  created_time: string
  agent_id: string
  op: Op
  type: string
  group: string
  name: string
  path: string[]
  note: string
  task: string
  decision: string
  fields: Record<string, string>
  trigger_id: string
}

export type ScanAnswer = {
  id: string
  date: string
  time: string
  agent_id: string
  l1: string
  changes: Change[]
  /** The groups its receipt named: looked at, nothing changed. */
  checked: string[]
  answered: boolean
}

export type State = {
  project: string
  /** Group → its types, in contract order — the server owns the vocabulary. */
  groups: Record<string, string[]>
  scans: ScanAnswer[]
  /** Changes posted without a scan behind them, newest first. */
  loose: Change[]
  counts: { types: { type: string; n: number }[]; ops: { op: string; n: number }[] }
  /** Standing debt and action-needed rows — nothing later removed them. */
  owes: Change[]
  total_changes: number
}
