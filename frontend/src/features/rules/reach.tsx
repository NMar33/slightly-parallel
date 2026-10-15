import { isExample, type KeptSet, type SetIntegration, type Vision } from '../visions/data'

/**
 * A rule's heading: the first sentence of its current wording. The message
 * that kept it opens with whatever the operator typed first ("why you moving
 * tasks?"), which names the incident, not the rule.
 */
export function ruleHeadline(v: Vision, fallback: string): string {
  const text = (v.l2 || '').trim()
  if (!text) return fallback
  const first = text.split('\n')[0]!.replace(/[*_`]/g, '')
  const sentence = /^(.+?[.!])(\s|$)/.exec(first)?.[1] ?? first
  return sentence.length > 140 ? `${sentence.slice(0, 139).trimEnd()}…` : sentence
}

/** The on/off switch, shared (components/Switch). */
export { Switch } from '../../components/Switch'

/* ------------------------------------------------------- where it reaches */

/**
 * Where a rule reaches, in the one model the rules page uses: a rule on its
 * own reaches no one. It reaches every project when it is for all agents
 * (Slightly Parallel keeps it written into every AGENTS.md), and the chosen projects
 * of every set it is in that was written somewhere. Archived reaches nothing.
 */

export const isArchived = (v: Vision) => (v.row.status || 'active') === 'archived'

export const isForAll = (v: Vision) => !isArchived(v) && (v.row.auto ?? '').trim().toLowerCase() === 'yes'

interface Place {
  project: string
  set: string
}

export interface Reach {
  all: boolean
  places: Place[]
}

export function reachOf(v: Vision, sets: KeptSet[], integrations: SetIntegration[]): Reach {
  // An example is a mock: whatever its switch or sets say, it is written nowhere.
  if (isArchived(v) || isExample(v.row)) return { all: false, places: [] }
  const places: Place[] = []
  for (const s of sets) {
    if (!s.items.includes(v.row.id)) continue
    for (const i of integrations) if (i.set_id === s.id) places.push({ project: i.project, set: s.name })
  }
  return { all: isForAll(v), places }
}
