/**
 * The timeline's time furniture: the Monday week grid, the mirrored top and
 * bottom date axes, and the dashed TODAY marker. Pure SVG fragments fed the
 * memoised ticks from AgentTimeline — no state, no handlers.
 */

import type { XScale } from './types'

/** Week grid */
export function WeekGrid({
  weekTicks,
  xScale,
  innerHeight,
}: {
  weekTicks: Date[]
  xScale: XScale
  innerHeight: number
}): JSX.Element {
  return (
    <>
      {weekTicks.filter((t) => xScale(t) > 2).map((t, i) => (
        <line
          key={`wk-${i}`}
          x1={xScale(t)}
          x2={xScale(t)}
          y1={0}
          y2={innerHeight}
          stroke="var(--border-subtle)"
          strokeWidth={1}
          shapeRendering="crispEdges"
        />
      ))}
    </>
  )
}

/** How near the TODAY marker a top label may stand before it is left out. */
const TODAY_CLEAR_PX = 30

/** Top axis (with its dotted grid lines) and the bottom mirror. A top
 *  label under the TODAY marker is left out; its grid line stays. */
export function DateAxes({
  dateTicks,
  tickFormat,
  xScale,
  innerHeight,
  todayX = null,
}: {
  dateTicks: Date[]
  tickFormat: (d: Date) => string
  xScale: XScale
  innerHeight: number
  /** Where TODAY is drawn, when it is. */
  todayX?: number | null
}): JSX.Element {
  return (
    <>
      {/* Top axis: date ticks */}
      <g transform={`translate(0,${-8})`}>
        {dateTicks.map((t, i) => (
          <g key={`tt-${i}`} transform={`translate(${xScale(t)},0)`}>
            <line
              y1={8}
              y2={innerHeight + 8}
              stroke="var(--border-default)"
              strokeWidth={1}
              strokeDasharray="1 3"
              shapeRendering="crispEdges"
            />
            {(todayX == null || Math.abs(xScale(t) - todayX) >= TODAY_CLEAR_PX) && (
              <text
                y={0}
                textAnchor="middle"
                fontSize={11}
                fill="var(--text-tertiary)"
              >
                {tickFormat(t)}
              </text>
            )}
          </g>
        ))}
      </g>

      {/* Bottom axis: date ticks (mirror) */}
      <g transform={`translate(0,${innerHeight + 18})`}>
        {dateTicks.map((t, i) => (
          <text
            key={`bt-${i}`}
            x={xScale(t)}
            textAnchor="middle"
            fontSize={11}
            fill="var(--text-tertiary)"
          >
            {tickFormat(t)}
          </text>
        ))}
      </g>
    </>
  )
}

/** TODAY marker — dashed brand line */
export function TodayMarker({ todayX, innerHeight }: { todayX: number; innerHeight: number }): JSX.Element {
  return (
    <g>
      <line
        x1={todayX}
        x2={todayX}
        y1={-12}
        y2={innerHeight + 4}
        stroke="var(--brand)"
        strokeWidth={1.5}
        strokeDasharray="4 3"
      />
      <rect
        x={todayX - 20}
        y={-24}
        width={40}
        height={14}
        rx={7}
        fill="var(--brand)"
      />
      <text
        x={todayX}
        y={-14}
        textAnchor="middle"
        fontSize={10}
        fontWeight={600}
        fill="var(--bg-base)"
      >
        TODAY
      </text>
    </g>
  )
}
