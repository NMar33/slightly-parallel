/**
 * Task marks on the lanes: ◆ for a captured user turn handing a task over,
 * ◇ for the agent's reply naming one; same-hour marks cluster with a count,
 * or draw through `renderMark`. Buckets come memoised from layout.ts
 * (bucketMarks); this file only draws and wires hover/click.
 */

import type { AgentMeta, Lane, LaneMark, LaneMarkCluster, PlaceTip, SetTooltip, XScale } from './types'
import { t } from '../../i18n/scope/shell'

/** Task marks — after the brush so they stay clickable. ◆ = a
 *  captured user turn handing a task over, ◇ = the agent's reply
 *  naming one; same-hour marks on a lane cluster with a count. */
export function TaskMarks({
  lanes,
  markEntries,
  xScale,
  yFor,
  innerWidth,
  connecting,
  onConnectPick,
  onMarkClick,
  renderMark,
  dateAt,
  placeTip,
  setTooltip,
}: {
  lanes: Lane[]
  markEntries: Map<string, Array<[number, LaneMark[]]>>
  xScale: XScale
  yFor: (index: number) => number
  innerWidth: number
  connecting: boolean
  onConnectPick?: (agent: AgentMeta, at: Date) => void
  onMarkClick?: (cluster: LaneMarkCluster) => void
  renderMark?: (group: LaneMark[], laneColor: string) => React.ReactNode
  dateAt: (evt: { clientX: number }) => Date
  placeTip: PlaceTip
  setTooltip: SetTooltip
}): JSX.Element {
  return (
    <>
      {lanes.map((l) => {
        const entries = markEntries.get(l.agent.agent_id)
        if (!entries || entries.length === 0) return null
        const cy = yFor(l.index)
        return (
          <g key={`marks-${l.agent.agent_id}`}>
            {entries.map(([key, group]) => {
              const at = new Date(Date.parse(group[0]!.at))
              const cx = xScale(at)
              if (cx < -6 || cx > innerWidth + 6) return null
              const handed = group.some((g) => g.role === 'user')
              const titles = [...new Set(group.map((g) => g.title || g.task_id))]
              const label = titles.slice(0, 3).join(' · ') + (titles.length > 3 ? ` +${titles.length - 3}` : '')
              return (
                <g
                  key={key}
                  transform={`translate(${cx},${cy})`}
                  onClick={(evt) => {
                    if (connecting) { onConnectPick?.(l.agent, dateAt(evt)); return }
                    onMarkClick?.({ agent: l.agent, at, marks: group })
                  }}
                  onMouseEnter={(evt) => {
                    placeTip(evt)
                    setTooltip({
                      agent: l.agent,
                      cluster: { agent: l.agent, at, marks: group },
                    })
                  }}
                  onMouseLeave={() => setTooltip(null)}
                  style={{ cursor: connecting ? 'crosshair' : onMarkClick ? 'pointer' : 'default' }}
                  role="img"
                  aria-label={`${handed ? t('Handed') : t('Worked on')}: ${label}`}
                >
                  {renderMark ? renderMark(group, l.color) : (
                  <rect
                    x={-5} y={-5} width={10} height={10}
                    transform="rotate(45)"
                    fill={handed ? 'var(--status-amber)' : 'var(--bg-surface)'}
                    stroke={handed ? 'var(--status-amber)' : l.color}
                    strokeWidth={1.5}
                  />
                  )}
                  {!renderMark && group.length > 1 && (
                    <text x={7} y={4} fontSize={9} fontWeight={600} fill="var(--text-secondary)">
                      {group.length}
                    </text>
                  )}
                </g>
              )
            })}
          </g>
        )
      })}
    </>
  )
}
