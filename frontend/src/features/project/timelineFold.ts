/**
 * Folding agent groups on the timeline: a folded group becomes one lane
 * that stands in for its members — their stretches of activity drawn as
 * pieces of that lane, their task marks and links moved onto it.
 */

import type { AgentMeta, LaneMark, TimelineLink } from '../../components/AgentTimeline/AgentTimeline'
import { groupKey } from '../../lib/groups'
import { agentLabel } from '../../utils/agentLabel'

type Folded = {
  agents: AgentMeta[]
  /** member id → the lane it is drawn on now (itself when not folded). */
  laneOf: (id: string) => string
}

export function foldGroups(agents: AgentMeta[], folded: Set<string>): Folded {
  const byGroup = new Map<string, AgentMeta[]>()
  for (const a of agents) {
    const g = a.agent_group || ''
    if (g && folded.has(g)) (byGroup.get(g) ?? byGroup.set(g, []).get(g)!).push(a)
  }
  const map = new Map<string, string>()
  const out: AgentMeta[] = []
  const placed = new Set<string>()
  for (const a of agents) {
    const g = a.agent_group || ''
    const members = g ? byGroup.get(g) : undefined
    if (!members) { out.push(a); continue }
    const id = groupKey(g)
    map.set(a.agent_id, id)
    if (placed.has(g)) continue
    placed.add(g)
    const first = members.map((m) => m.created_date).sort()[0]!
    const last = members.map((m) => m.last_active || m.created_date).sort().at(-1)!
    out.push({
      agent_id: id,
      agent_name: g,
      agent_group: g,
      created_date: first,
      last_active: last,
      message_count: members.reduce((n, m) => n + (m.message_count ?? 0), 0),
      members: members.map((m) => agentLabel(m)),
      spans: members.map((m) => ({ from: m.created_date, to: m.last_active || m.created_date })),
    })
  }
  return { agents: out, laneOf: (id) => map.get(id) ?? id }
}

/** Marks keyed by lane: a folded group's lane carries its members' marks. */
export function foldMarks(marks: Record<string, LaneMark[]>, laneOf: (id: string) => string): Record<string, LaneMark[]> {
  const out: Record<string, LaneMark[]> = {}
  for (const [id, list] of Object.entries(marks)) (out[laneOf(id)] ??= []).push(...list)
  return out
}

/** Links between lanes; one inside a folded group has no line to draw. */
export function foldLinks(links: TimelineLink[], laneOf: (id: string) => string): TimelineLink[] {
  return links
    .map((l) => ({ ...l, from_id: laneOf(l.from_id), to_id: laneOf(l.to_id) }))
    .filter((l) => l.from_id !== l.to_id)
}
