/**
 * The timeline's lanes: alternating row backgrounds (the connect-mode pick
 * target), group brackets, the left-axis name labels with their ✎ / 👁
 * controls, and the agent bars. Each renders a fragment that drops into
 * the chart's origin <g> in the order AgentTimeline composes them.
 */

import { GROUP_COLOR } from '../../lib/groups'
import { BAR_HEIGHT, BAR_RADIUS, MARGIN, ROW_HEIGHT, safeParseDate, truncate } from './layout'
import type { AgentMeta, GroupBand, Lane, PlaceTip, SetTooltip, XScale } from './types'
import { t } from '../../i18n/scope/shell'

type Pick = ((agent: AgentMeta, at: Date) => void) | undefined

/** Row backgrounds — alternating for readability */
export function LaneRows({
  lanes,
  marginLeft,
  innerWidth,
  connectFrom,
  connecting,
  onConnectPick,
  dateAt,
}: {
  lanes: Lane[]
  marginLeft: number
  innerWidth: number
  connectFrom: string | null | undefined
  connecting: boolean
  onConnectPick: Pick
  dateAt: (evt: { clientX: number }) => Date
}): JSX.Element {
  return (
    <>
      {lanes.map((l) => (
        <rect
          key={`bg-${l.agent.agent_id}`}
          x={-marginLeft}
          y={l.index * ROW_HEIGHT}
          width={innerWidth + marginLeft + MARGIN.right}
          height={ROW_HEIGHT}
          fill={connectFrom === l.agent.agent_id ? 'var(--brand-glow)' : l.index % 2 === 0 ? 'transparent' : 'var(--bg-base)'}
          opacity={connectFrom === l.agent.agent_id ? 1 : l.index % 2 === 0 ? 0 : 0.5}
          data-testid="lane-row"
          // In connect mode the whole row is the pick target — the
          // name, the empty space, not only the bar.
          pointerEvents={connecting ? 'all' : 'none'}
          style={connecting ? { cursor: 'crosshair' } : undefined}
          onClick={connecting ? (evt) => onConnectPick?.(l.agent, dateAt(evt)) : undefined}
        />
      ))}
    </>
  )
}

/** Group brackets — a bar down the far left with the name along it */
export function GroupBrackets({
  groups,
  marginLeft,
  onGroupToggle,
  folded,
}: {
  groups: GroupBand[]
  marginLeft: number
  onGroupToggle?: (name: string) => void
  folded?: Set<string>
}): JSX.Element {
  return (
    <>
      {groups.map((g) => {
        const top = g.first * ROW_HEIGHT + 3
        const bottom = (g.last + 1) * ROW_HEIGHT - 3
        const mid = (top + bottom) / 2
        const x = -marginLeft + 18
        return (
          <g key={`grp-${g.name}-${g.first}`} data-testid="group-bracket"
            onClick={onGroupToggle ? () => onGroupToggle(g.name) : undefined}
            style={onGroupToggle ? { cursor: 'pointer' } : undefined}
            role={onGroupToggle ? 'button' : undefined}
            aria-label={onGroupToggle ? (folded?.has(g.name) ? t('Unfold the group {name}', { name: g.name }) : t('Fold the group {name}', { name: g.name })) : undefined}>
            <title>{`${t('group: {name}', { name: g.name })}${onGroupToggle ? (folded?.has(g.name) ? ` — ${t('click to show every lane')}` : ` — ${t('click to fold into one lane')}`) : ''}`}</title>
            {onGroupToggle && <rect x={x - 14} y={top} width={20} height={bottom - top} fill="transparent" />}
            <line x1={x} x2={x} y1={top} y2={bottom} stroke={g.color} strokeWidth={2.5} strokeLinecap="round" />
            <text
              transform={`translate(${x - 7},${mid}) rotate(-90)`}
              textAnchor="middle"
              fontSize={9}
              fontWeight={600}
              letterSpacing="0.06em"
              fill="var(--text-tertiary)"
              style={{ textTransform: 'uppercase' }}
            >
              {truncate(g.name, Math.max(4, Math.floor((bottom - top) / 5.5)))}
            </text>
          </g>
        )
      })}
    </>
  )
}

/** Left axis: agent name labels (+ rename pencil / open eye) */
export function LaneLabels({
  lanes,
  yFor,
  labelEndX,
  nameMax,
  connectFrom,
  connecting,
  onConnectPick,
  onGroupToggle,
  onRenameRequest,
  onOpenRequest,
}: {
  lanes: Lane[]
  yFor: (index: number) => number
  labelEndX: number
  nameMax: number
  connectFrom: string | null | undefined
  connecting: boolean
  onConnectPick: Pick
  onGroupToggle?: (name: string) => void
  onRenameRequest?: (agent: AgentMeta) => void
  onOpenRequest?: (agent: AgentMeta) => void
}): JSX.Element {
  return (
    <>
      {lanes.map((l) => {
        const isGroup = !!l.agent.members
        const label = isGroup
          ? `${truncate(l.agent.agent_name || '', nameMax - 4)} · ${l.agent.members!.length}`
          : truncate(l.agent.agent_name || l.agent.agent_id, nameMax)
        const cy = yFor(l.index)
        return (
          <g key={`lbl-${l.agent.agent_id}`}>
            <text
              x={labelEndX}
              y={cy}
              dy="0.32em"
              textAnchor="end"
              fontSize={12}
              fill={connectFrom === l.agent.agent_id ? 'var(--brand)' : isGroup ? GROUP_COLOR : 'var(--text-secondary)'}
              fontWeight={isGroup ? 600 : undefined}
              style={connecting ? { cursor: 'crosshair' } : (isGroup ? onGroupToggle : onRenameRequest) ? { cursor: 'pointer' } : undefined}
              data-testid="lane-label"
              onClick={connecting
                ? () => onConnectPick?.(l.agent, l.created)
                : isGroup ? (onGroupToggle ? () => onGroupToggle(l.agent.agent_group || '') : undefined)
                : onRenameRequest ? () => onRenameRequest(l.agent) : undefined}
            >
              {isGroup ? <title>{`${t('Group {name}', { name: l.agent.agent_name ?? '' })}: ${l.agent.members!.join(', ')} — ${t('click to show every lane')}`}</title>
                : connecting ? <title>{t('Pick {name} for the link', { name: l.agent.agent_name || l.agent.agent_id })}</title> : onRenameRequest && (
                <title>Rename {l.agent.agent_id}</title>
              )}
              {label}
            </text>
            {onRenameRequest && !isGroup && (
              <text
                x={labelEndX + 6}
                y={cy}
                dy="0.32em"
                fontSize={10}
                fill="var(--text-tertiary)"
                style={{ cursor: connecting ? 'crosshair' : 'pointer' }}
                onClick={() => (connecting ? onConnectPick?.(l.agent, l.created) : onRenameRequest(l.agent))}
                role="button"
                aria-label={t('Rename {name}', { name: l.agent.agent_name || l.agent.agent_id })}
              >
                <title>{t('Rename')}</title>
                ✎
              </text>
            )}
            {onOpenRequest && !isGroup && (
              <g
                transform={`translate(${labelEndX + 20},${cy - 6})`}
                role="button"
                tabIndex={0}
                aria-label={t('Open {name}', { name: l.agent.agent_name || l.agent.agent_id })}
                data-testid="lane-eye"
                style={{ cursor: connecting ? 'crosshair' : 'pointer' }}
                onClick={() => (connecting ? onConnectPick?.(l.agent, l.created) : onOpenRequest(l.agent))}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (connecting) onConnectPick?.(l.agent, l.created); else onOpenRequest(l.agent) } }}
              >
                <title>{t('Open the agent\'s page')}</title>
                <rect x={-2} y={-1} width={16} height={14} fill="transparent" />
                <g transform="scale(0.5)" fill="none" stroke="var(--text-tertiary)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                  <circle cx="12" cy="12" r="3" />
                </g>
              </g>
            )}
          </g>
        )
      })}
    </>
  )
}

/** Agent bars */
export function LaneBars({
  lanes,
  xScale,
  yFor,
  connectFrom,
  connecting,
  onConnectPick,
  onAgentClick,
  dateAt,
  placeTip,
  setTooltip,
}: {
  lanes: Lane[]
  xScale: XScale
  yFor: (index: number) => number
  connectFrom: string | null | undefined
  connecting: boolean
  onConnectPick: Pick
  onAgentClick?: (agent: AgentMeta) => void
  dateAt: (evt: { clientX: number }) => Date
  placeTip: PlaceTip
  setTooltip: SetTooltip
}): JSX.Element {
  return (
    <>
      {lanes.map((l) => {
        const x = xScale(l.created)
        const w = Math.max(3, xScale(l.lastActive) - x)
        const y = yFor(l.index) - BAR_HEIGHT / 2
        const gradId = `grad-${l.index}`
        const picked = connectFrom === l.agent.agent_id
        return (
          <g
            key={`bar-${l.agent.agent_id}`}
            onMouseEnter={(evt) => {
              placeTip(evt)
              setTooltip({ agent: l.agent })
            }}
            onMouseMove={placeTip}
            onClick={(evt) => {
              if (connecting) onConnectPick?.(l.agent, dateAt(evt))
              else onAgentClick?.(l.agent)
            }}
            style={{ cursor: connecting ? 'crosshair' : onAgentClick ? 'pointer' : 'default' }}
            data-testid="lane-bar"
          >
            <defs>
              <linearGradient id={gradId} x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stopColor={l.color} stopOpacity={0.9} />
                <stop offset="100%" stopColor={l.color} stopOpacity={0.6} />
              </linearGradient>
            </defs>
            {picked && (
              <rect
                x={x - 3}
                y={y - 3}
                width={w + 6}
                height={BAR_HEIGHT + 6}
                rx={BAR_RADIUS + 2}
                fill="none"
                stroke="var(--brand)"
                strokeWidth={1.5}
                strokeDasharray="3 2"
              />
            )}
            {l.agent.spans ? l.agent.spans.map((sp, i) => {
              const a = safeParseDate(sp.from), b = safeParseDate(sp.to)
              if (!a) return null
              const sx = xScale(a), sw = Math.max(3, xScale(b && b > a ? b : a) - sx)
              return (
                <rect key={i} x={sx} y={y} width={sw} height={BAR_HEIGHT} rx={BAR_RADIUS} ry={BAR_RADIUS}
                  fill={`url(#${gradId})`} stroke={l.color} strokeWidth={0.5} />
              )
            }) : (
            <rect
              x={x}
              y={y}
              width={w}
              height={BAR_HEIGHT}
              rx={BAR_RADIUS}
              ry={BAR_RADIUS}
              fill={`url(#${gradId})`}
              stroke={l.color}
              strokeWidth={0.5}
            />
            )}
            {/* Accessible label — screen readers announce this. */}
            <title>
              {`${l.agent.agent_name || l.agent.agent_id}`}
              {l.agent.l1_headline ? ` — ${l.agent.l1_headline}` : ''}
              {connecting ? ` — ${t('click to pick for a link')}` : ''}
            </title>
          </g>
        )
      })}
    </>
  )
}
