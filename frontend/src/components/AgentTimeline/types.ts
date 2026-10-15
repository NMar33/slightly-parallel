/**
 * Types for the agent swim-lane timeline: the public data contract
 * (AgentMeta, LaneMark, TimelineLink …), the component's props, and the
 * internal shapes the layout maths produces (Lane, Edge, GroupBand).
 * Re-exported from AgentTimeline.tsx, the path other modules import.
 */

import type { ScaleTime } from 'd3-scale'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/**
 * Minimum agent shape this component needs. A superset of the backend's
 * `Agent` model — extra fields on the input are ignored.
 */
export interface AgentMeta {
  agent_id: string
  agent_name?: string
  chat_title?: string
  /** Operator grouping — lanes with one name sit together under it. */
  agent_group?: string
  /** A folded group standing in for its members: their names, and the
   *  stretches each was active, drawn as pieces of one lane. */
  members?: string[]
  spans?: Array<{ from: string; to: string }>
  tool?: string
  cwd?: string
  project?: string
  parent_agent_id?: string | null
  created_date: string
  last_active: string
  message_count?: number
  l1_headline?: string
}

/** A captured turn on an agent's lane that named a task. */
export interface LaneMark {
  task_id: string
  title: string
  at: string          // ISO local
  role: 'user' | 'agent'
  session_id?: string
  turn?: number
}

/** Marks that fell into the same hour on one lane render as one diamond. */
export interface LaneMarkCluster {
  agent: AgentMeta
  at: Date
  marks: LaneMark[]
}

/** An operator-drawn connection between two lanes. */
export interface TimelineLink {
  id: string
  from_id: string
  to_id: string
  kind: string
  style: 'solid' | 'dashed' | 'dotted' | string
  note: string
  /** ISO local anchors; empty = the target's creation for both ends. */
  from_at?: string
  to_at?: string
}

export interface AgentTimelineProps {
  agents: AgentMeta[]
  /** Task mentions per agent id — drawn as diamonds on the lane. */
  marks?: Record<string, LaneMark[]>
  /** Click on a diamond (one mark or an hour cluster). */
  onMarkClick?: (cluster: LaneMarkCluster) => void
  /** Draws an hour's marks in place of the diamond, centred on (0, 0) and
   *  at most one row tall. Absent: the diamond. */
  renderMark?: (group: LaneMark[], laneColor: string) => React.ReactNode
  /** With `renderMark`: what a task looks like in the hover list, and the
   *  word for its state, in place of ◆ / ◇. */
  markSwatch?: (taskId: string) => { node: React.ReactNode; label: string } | undefined
  /** Operator-drawn links, drawn in their style with a note dot. */
  links?: TimelineLink[]
  /** Click on a link's dot. */
  onLinkClick?: (link: TimelineLink) => void
  /** Fixed height override; default computes from lane count (min 240px). */
  height?: number
  /** Extra classes for the outer wrapper. */
  className?: string
  /** Callback when the user clicks an agent bar. */
  onAgentClick?: (agent: AgentMeta) => void
  /** When set, lane labels grow a rename affordance (the pencil). */
  onRenameRequest?: (agent: AgentMeta) => void
  /** When set, lane labels grow an eye — open the agent's page. */
  onOpenRequest?: (agent: AgentMeta) => void
  /** When set, a group's bracket and a folded group's label fold and
   *  unfold it; `folded` names the groups folded now. */
  onGroupToggle?: (name: string) => void
  folded?: Set<string>
  /**
   * Connect mode: bars become pick targets. `from` is the lane already
   * picked (highlighted) — the parent turns two picks into a link.
   */
  connect?: { active: boolean; from: string | null }
  /** A bar was picked in connect mode, with the date under the cursor. */
  onConnectPick?: (agent: AgentMeta, at: Date) => void
  /**
   * Emit render-timing to a callback (for tests / perf budget hook).
   */
  onRendered?: (ms: number) => void
}

// ---------------------------------------------------------------------------
// Internal shapes
// ---------------------------------------------------------------------------

export interface Lane {
  agent: AgentMeta
  index: number
  created: Date
  lastActive: Date
  color: string
}

export interface Edge {
  fromIndex: number
  toIndex: number
  fromDate: Date
  toDate: Date
  color: string
}

export interface GroupBand {
  name: string
  first: number
  last: number
  color: string
}

export interface TooltipState {
  agent: AgentMeta
  /** Set when hovering a task mark: the cluster under the cursor. */
  cluster?: LaneMarkCluster
  /** Set when hovering a link's dot. */
  link?: { link: TimelineLink; from: AgentMeta; to: AgentMeta }
}

/** A link with its geometry resolved against the current scale. */
export interface DrawnLink {
  link: TimelineLink
  from: Lane
  to: Lane
  x1: number
  y1: number
  x2: number
  y2: number
  mx: number
  my: number
}

/** The chart's time → x scale. */
export type XScale = ScaleTime<number, number>

/** Shared hover plumbing: place the tip, then set its content. */
export type PlaceTip = (evt: { clientX: number; clientY: number }) => void
export type SetTooltip = (state: TooltipState | null) => void
