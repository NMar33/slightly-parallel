import { useMemo, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { ChevronRight, SquareTerminal } from 'lucide-react'

import { StarButton } from '../StarButton'
import { STATE_COLOR, STATE_WORD, showTerminal, terminalOfAgent, useTerminals } from '../../lib/terminal'
import { StateDot } from '../../features/terminal/parts'
import { GROUP_COLOR } from '../../lib/groups'
import { STAR_COLOR, useMarkToggle, useMarks } from '../../lib/marks'
import { persistPref, readPref } from '../../lib/uiPrefs'
import type { SnapshotAgent, SnapshotActivity } from '../../lib/api'
import { agentLabel } from '../../utils/agentLabel'
import { t, tn } from '../../i18n/scope/shell'

/**
 * AgentTree — nested tree per project showing parent-child agent hierarchy.
 *
 * Renders in sidebar. Each project's agents are laid out as roots (no
 * parent_agent_id, or parent not in same project) with children indented via
 * connector lines (│ + └─) drawn with absolute-positioned pseudo-elements.
 *
 * Activity dot color:
 *   - done   → status-green (agent finished recently)
 *   - active → brand jade   (agent produced activity within RECENT_DAYS)
 *   - idle   → text-tertiary (nothing recent)
 *
 * Starred agents (★, the Important mark) come first at every level. Agents
 * the operator grouped (agent_group) sit under one row per group, in the
 * group colour, folding open to their members; "archived" starts folded
 * and goes last. The fold is remembered per project and group.
 *
 * Uses only design tokens — no raw hex. Both light and dark themes are
 * first-class, so this tree paints correctly in either. The sidebar in this
 * app is theme-aware (bg-surface), unlike variant-2's forced-dark sidebar.
 */

const RECENT_DAYS = 3

interface AgentTreeProps {
  agents: SnapshotAgent[]
  activity: SnapshotActivity[]
  /** Project filter. If unset, walks every agent. */
  project?: string
  className?: string
}

interface Node {
  agent: SnapshotAgent
  depth: number
}

function daysAgo(ts: string): number {
  const m = ts.match(/^(\d{2})(\d{2})-(\d{2})/)
  if (!m) return Infinity
  const y = 2000 + parseInt(m[1]!, 10)
  const mo = parseInt(m[2]!, 10) - 1
  const d = parseInt(m[3]!, 10)
  return (Date.now() - new Date(y, mo, d).getTime()) / 86_400_000
}

function statusOf(
  agent: SnapshotAgent,
  freshest: string | undefined,
): 'active' | 'done' | 'idle' {
  const ts = freshest ?? agent.last_active ?? agent.created_date ?? ''
  const age = ts ? daysAgo(ts.slice(0, 7)) : Infinity
  if (age <= RECENT_DAYS) return 'active'
  if (agent.message_count > 0) return 'done'
  return 'idle'
}

/**
 * Build a flat list preserving depth by walking parent→children edges.
 * Cycles are guarded via `visited`. Orphans (parent not present) treated as roots.
 */
function buildNodes(agents: SnapshotAgent[], starred: (id: string) => boolean = () => false): Node[] {
  const byId = new Map(agents.map((a) => [a.agent_id, a]))
  const children = new Map<string | null, SnapshotAgent[]>()
  for (const a of agents) {
    const p = a.parent_agent_id && byId.has(a.parent_agent_id) ? a.parent_agent_id : null
    const arr = children.get(p) ?? []
    arr.push(a)
    children.set(p, arr)
  }
  // Sort each level by created_date ASC then agent_id.
  for (const [k, arr] of children) {
    arr.sort((a, b) =>
      Number(starred(b.agent_id)) - Number(starred(a.agent_id)) ||
      (a.created_date || '').localeCompare(b.created_date || '') ||
      a.agent_id.localeCompare(b.agent_id),
    )
    children.set(k, arr)
  }

  const out: Node[] = []
  const visited = new Set<string>()
  function walk(parent: string | null, depth: number) {
    for (const a of children.get(parent) ?? []) {
      if (visited.has(a.agent_id)) continue
      visited.add(a.agent_id)
      out.push({ agent: a, depth })
      walk(a.agent_id, depth + 1)
    }
  }
  walk(null, 0)
  // Sweep any remaining (unlikely) agents as depth-0.
  for (const a of agents) {
    if (!visited.has(a.agent_id)) {
      out.push({ agent: a, depth: 0 })
      visited.add(a.agent_id)
    }
  }
  return out
}

export function AgentTree({
  agents,
  activity,
  project,
  className = '',
}: AgentTreeProps) {
  const freshestByAgent = useMemo(() => {
    const m = new Map<string, string>()
    for (const a of activity ?? []) {
      const prev = m.get(a.agent_id) ?? ''
      if (a.created_date > prev) m.set(a.agent_id, a.created_date)
    }
    return m
  }, [activity])

  const filtered = useMemo(
    () => (project ? agents.filter((a) => a.project === project) : agents),
    [agents, project],
  )

  const terms = useTerminals().data?.sessions
  const has = useMarks().has
  const toggleStar = useMarkToggle()

  // Loose agents, then one section per group — the archive last.
  const sections = useMemo(() => {
    const isStar = (id: string) => has('agent', id)
    const loose = filtered.filter((a) => !a.agent_group)
    const groups = new Map<string, SnapshotAgent[]>()
    for (const a of filtered) if (a.agent_group) groups.set(a.agent_group, [...(groups.get(a.agent_group) ?? []), a])
    const latest = (xs: SnapshotAgent[]) => xs.reduce((m, a) => ((a.last_active || '') > m ? a.last_active || '' : m), '')
    const named = [...groups.entries()]
      .map(([name, members]) => ({ name, members, nodes: buildNodes(members, isStar), last: latest(members),
        stars: members.some((m) => isStar(m.agent_id)) }))
      .sort((x, y) => Number(x.name === 'archived') - Number(y.name === 'archived')
        || Number(y.stars) - Number(x.stars) || y.last.localeCompare(x.last))
    return { loose: buildNodes(loose, isStar), groups: named }
  }, [filtered, has])

  const foldKey = `sp-tree-folds:${project ?? ''}`
  const [folds, setFolds] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(readPref(foldKey) ?? '{}') ?? {} } catch { return {} }
  })
  const isOpen = (g: string) => folds[g] ?? g !== 'archived'
  const flip = (g: string) => setFolds((f) => {
    const next = { ...f, [g]: !isOpen(g) }
    persistPref(foldKey, JSON.stringify(next))
    return next
  })

  const nameColor = 'var(--text-primary)'
  const subColor = 'var(--text-secondary)'
  const mutedColor = 'var(--text-tertiary)'
  const guideColor = 'var(--border-default)'

  if (filtered.length === 0) {
    return (
      <div className={`px-8 py-12 text-11 font-mono ${className}`.trim()} style={{ color: mutedColor }}>
        No agents yet.
      </div>
    )
  }

  const row = ({ agent, depth }: Node, indent: number) => {
    const status = statusOf(agent, freshestByAgent.get(agent.agent_id))
    const on = has('agent', agent.agent_id)
    const dotColor =
      status === 'active'
        ? 'var(--brand)'
        : status === 'done'
          ? 'var(--status-green)'
          : mutedColor
    const dotGlow =
      status === 'active'
        ? '0 0 8px var(--brand-glow)'
        : status === 'done'
          ? '0 0 0 2px color-mix(in srgb, var(--status-green) 15%, transparent)'
          : 'none'
    const d = depth + indent
    return (
      <li key={agent.agent_id} role="treeitem" aria-level={d + 1}>
        <NavLink
          to={`/agent/${encodeURIComponent(agent.agent_id)}`}
          className={({ isActive }) =>
            `group block relative rounded-input transition-colors duration-fast ease-out ${
              isActive ? 'bg-hover' : 'hover:bg-hover'
            }`
          }
          style={{ marginLeft: d * 14, paddingLeft: 10, paddingRight: 10, paddingTop: 6, paddingBottom: 6 }}
        >
          {d > 0 && (
            <>
              <span aria-hidden style={{ position: 'absolute', left: -8, top: -2, bottom: '50%', width: 1, background: indent && !depth ? GROUP_COLOR : guideColor, opacity: indent && !depth ? 0.5 : 1 }} />
              <span aria-hidden style={{ position: 'absolute', left: -8, top: '50%', width: 6, height: 1, background: indent && !depth ? GROUP_COLOR : guideColor, opacity: indent && !depth ? 0.5 : 1 }} />
            </>
          )}
          <div className="flex items-center gap-8 min-w-0">
            <span aria-hidden className="inline-block w-8 h-8 rounded-pill shrink-0" style={{ background: dotColor, boxShadow: dotGlow }} />
            <span className="font-mono text-11 truncate flex-1" style={{ color: nameColor }} title={agent.agent_id}>
              {agentLabel(agent)}
            </span>
            {/* Its terminal: the state, and a click brings it forward. */}
            {(() => {
              const term = terminalOfAgent(terms, agent.agent_id)
              return term ? (
                <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); showTerminal(term.id) }}
                  title={t('Terminal: {state}. Click to show it', { state: STATE_WORD[term.state] })} aria-label={t('Show its terminal ({state})', { state: STATE_WORD[term.state] })}
                  className="shrink-0 inline-flex items-center gap-2 px-2 rounded-input hover:bg-elevated">
                  <SquareTerminal size={10} style={{ color: STATE_COLOR[term.state] }} aria-hidden />
                  <StateDot state={term.state} size={6} />
                </button>
              ) : null
            })()}
            {/* The star: always shown when on; on hover to put it on. */}
            <span className="shrink-0 inline-flex" onClick={(e) => { e.preventDefault(); e.stopPropagation() }}>
              <StarButton on={on} what="this agent" quiet={!on} size={11}
                onToggle={(next) => toggleStar(next, 'agent', agent.agent_id, { project: agent.project, agent_id: agent.agent_id })} />
            </span>
            {agent.message_count > 0 && (
              <span className="font-mono text-11 tabular shrink-0" style={{ color: mutedColor }}>
                {agent.message_count}
              </span>
            )}
          </div>
          {agent.l1_headline && (
            <div
              className="text-11 mt-4 leading-snug pl-16"
              style={{ color: subColor, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
              title={agent.l1_headline}
            >
              {agent.l1_headline}
            </div>
          )}
        </NavLink>
      </li>
    )
  }

  return (
    <ul role="tree" className={`flex flex-col gap-2 ${className}`.trim()}>
      {sections.loose.map((n) => row(n, 0))}
      {sections.groups.map((g) => {
        const open = isOpen(g.name)
        const msgs = g.members.reduce((n, a) => n + (a.message_count || 0), 0)
        return (
          <li key={`group:${g.name}`} role="treeitem" aria-level={1} aria-expanded={open}>
            <button type="button" onClick={() => flip(g.name)}
              title={`${g.name}: ${tn(g.members.length, '{n} agent', '{n} agents')}. ${open ? t('Click to collapse') : t('Click to expand')}`}
              className="w-full flex items-center gap-6 rounded-input hover:bg-hover px-8 py-6 text-left">
              <ChevronRight size={11} aria-hidden className={`shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} style={{ color: GROUP_COLOR }} />
              <span className="font-mono text-11 truncate flex-1" style={{ color: GROUP_COLOR }}>{g.name}</span>
              {g.stars && !open && <span role="img" aria-label={t('has a starred agent')} style={{ color: STAR_COLOR }} className="text-11 leading-none">★</span>}
              <span className="font-mono text-10 shrink-0" style={{ color: mutedColor }}>×{g.members.length}</span>
              {msgs > 0 && <span className="font-mono text-11 tabular shrink-0" style={{ color: mutedColor }}>{msgs}</span>}
            </button>
            {open && <ul role="group" className="flex flex-col gap-2">{g.nodes.map((n) => row(n, 1))}</ul>}
          </li>
        )
      })}
    </ul>
  )
}

