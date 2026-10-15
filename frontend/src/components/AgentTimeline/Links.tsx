/**
 * Connections between lanes: parent → child bezier edges, operator-drawn
 * link lines (under the bars), their wide transparent hit paths and their
 * note dots (both above the brush so they stay hoverable and clickable).
 * Geometry comes pre-resolved from layout.ts (bezierPath, resolveLinks).
 */

import { bezierPath, LINK_DASH } from './layout'
import type { DrawnLink, Edge, PlaceTip, SetTooltip, TimelineLink, XScale } from './types'

/** Parent → child bezier edges (drawn under bars) */
export function ParentEdges({
  edges,
  xScale,
  yFor,
}: {
  edges: Edge[]
  xScale: XScale
  yFor: (index: number) => number
}): JSX.Element {
  return (
    <g fill="none" strokeWidth={1.5} opacity={0.7}>
      {edges.map((e, i) => {
        const x1 = xScale(e.fromDate)
        const y1 = yFor(e.fromIndex)
        const x2 = xScale(e.toDate)
        const y2 = yFor(e.toIndex)
        return (
          <g key={`edge-${i}`}>
            <path d={bezierPath(x1, y1, x2, y2)} stroke={e.color} />
            {/* Small target dot on the child side */}
            <circle cx={x2} cy={y2} r={2.5} fill={e.color} />
          </g>
        )
      })}
    </g>
  )
}

/** Operator links — the line, under the bars; the dot comes later */
export function LinkLines({ drawnLinks }: { drawnLinks: DrawnLink[] }): JSX.Element {
  return (
    <g fill="none" strokeWidth={1.5} opacity={0.85} data-testid="agent-links">
      {drawnLinks.map((d) => (
        <path
          key={`lk-${d.link.id}`}
          d={bezierPath(d.x1, d.y1, d.x2, d.y2)}
          stroke={d.from.color}
          strokeDasharray={LINK_DASH[d.link.style]}
          strokeLinecap="round"
          data-kind={d.link.kind}
          data-style={d.link.style}
        />
      ))}
    </g>
  )
}

interface LinkHoverProps {
  drawnLinks: DrawnLink[]
  onLinkClick?: (link: TimelineLink) => void
  placeTip: PlaceTip
  setTooltip: SetTooltip
}

/** Link hit areas — the visible line is under the bars; this wide
 *  transparent twin sits above the brush so the line itself can
 *  be hovered and clicked, not only its dot. */
export function LinkHits({ drawnLinks, onLinkClick, placeTip, setTooltip }: LinkHoverProps): JSX.Element {
  return (
    <>
      {drawnLinks.map((d) => (
        <path
          key={`lkhit-${d.link.id}`}
          d={bezierPath(d.x1, d.y1, d.x2, d.y2)}
          fill="none"
          stroke="transparent"
          strokeWidth={14}
          pointerEvents="stroke"
          data-testid="link-hit"
          style={{ cursor: onLinkClick ? 'pointer' : 'default' }}
          onClick={() => onLinkClick?.(d.link)}
          onMouseEnter={(evt) => {
            placeTip(evt)
            setTooltip({
              agent: d.from.agent,
              link: { link: d.link, from: d.from.agent, to: d.to.agent },
            })
          }}
          onMouseLeave={() => setTooltip(null)}
        />
      ))}
    </>
  )
}

/** Link dots — after the brush so they stay hoverable/clickable.
 *  The dot is where the note lives. */
export function LinkDots({ drawnLinks, onLinkClick, placeTip, setTooltip }: LinkHoverProps): JSX.Element {
  return (
    <>
      {drawnLinks.map((d) => (
        <g
          key={`lkdot-${d.link.id}`}
          transform={`translate(${d.mx},${d.my})`}
          data-testid="link-dot"
          role={onLinkClick ? 'button' : 'img'}
          aria-label={`${d.from.agent.agent_name || d.from.agent.agent_id} ${d.link.kind} ${d.to.agent.agent_name || d.to.agent.agent_id}${d.link.note ? `: ${d.link.note}` : ''}`}
          style={{ cursor: onLinkClick ? 'pointer' : 'default' }}
          onClick={() => onLinkClick?.(d.link)}
          onMouseEnter={(evt) => {
            placeTip(evt)
            setTooltip({
              agent: d.from.agent,
              link: { link: d.link, from: d.from.agent, to: d.to.agent },
            })
          }}
          onMouseLeave={() => setTooltip(null)}
        >
          <circle r={9} fill="transparent" />
          <circle r={4.5} fill="var(--bg-surface)" stroke={d.from.color} strokeWidth={1.75} />
          {d.link.note && <circle r={1.6} fill={d.from.color} />}
        </g>
      ))}
    </>
  )
}
