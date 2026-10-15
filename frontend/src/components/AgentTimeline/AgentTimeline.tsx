/**
 * AgentTimeline — per-project swim-lane visualisation of agent lifecycles.
 *
 * Architecture §5 C10 — "Agent Branching Timeline".
 *
 * Layout
 * ------
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  name-col │ time-axis (top ticks)                                 │  ← margin.top
 *   │           │ · · · · · | week grid | · · · · · │ TODAY dashed     │
 *   │  agent-A  │ ▬▬▬▬▬▬▬▬▬▬▬▬                                        │
 *   │  agent-B  │             ╰─▬▬▬▬▬▬▬▬▬▬                             │  ← swim lane
 *   │  agent-C  │                       ╰─▬▬▬▬▬▬                        │
 *   │           │ date-axis (bottom ticks)                              │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 * Data contract
 * -------------
 *   Pure component: takes `agents: AgentMeta[]` and renders. Knows nothing
 *   about fetching. Parent-child edges are drawn only when the child's
 *   `parent_agent_id` resolves to another agent in the same list. Operator-
 *   drawn `links` are drawn the same way, in the style each link carries,
 *   with a dot in the middle that holds the note.
 *
 * Interactions
 * ------------
 *   • Hover a lane / bar → tooltip with name, project, headline, message count.
 *   • ✎ on a label → rename; 👁 → open the agent's page.
 *   • Brush across the x-axis → zooms the time domain (double-click to reset).
 *   • Connect mode (`connect.active`) → clicking a bar picks a lane; the
 *     parent turns the two picks into a link.
 *   • Everything is pure SVG — no canvas — so screen readers see structured
 *     <title>/<desc> and the SVG is inspectable in devtools.
 *
 * Groups
 * ------
 *   Agents with the same `agent_group` sit together, in the order the
 *   group first appeared, under a bracket that carries the group's name.
 *
 * Tokens
 * ------
 *   Every colour comes from tokens.css via `var(--…)`. The lane palette
 *   (`--lane-1`..`--lane-8`) is stable & PostHog-validated in both themes.
 *
 * Cyrillic
 * --------
 *   Names render as text nodes — the SVG inherits `--font-sans` which has
 *   Cyrillic-covering fallbacks. Tested against "рекогниция" fixtures.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import { brushX } from 'd3-brush'
import { scaleTime } from 'd3-scale'
import { select } from 'd3-selection'
import { timeFormat } from 'd3-time-format'

import { EmptyState } from '../states'
import { DateAxes, TodayMarker, WeekGrid } from './Axes'
import {
  bucketMarks,
  buildEdges,
  buildGroups,
  buildLanes,
  DEFAULT_WIDTH,
  fullDomainOf,
  LEFT_WITH_CONTROLS,
  MARGIN,
  MIN_INNER_HEIGHT,
  resolveLinks,
  ROW_HEIGHT,
  tickCountFor,
  weekTicksFor,
} from './layout'
import { GroupBrackets, LaneBars, LaneLabels, LaneRows } from './Lanes'
import { LinkDots, LinkHits, LinkLines, ParentEdges } from './Links'
import { TaskMarks } from './Marks'
import { TooltipLayer, useTipPlacement } from './Tooltip'
import type { AgentTimelineProps, LaneMark, TooltipState } from './types'
import { currentLang, locale, t, tn } from '../../i18n/scope/shell'

// Public surface — other modules import these from this path.
export type { AgentMeta, LaneMark, LaneMarkCluster, TimelineLink } from './types'
export { LINK_DASH } from './layout'

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgentTimeline({
  agents,
  marks,
  onMarkClick,
  renderMark,
  markSwatch,
  links,
  onLinkClick,
  height,
  className = '',
  onAgentClick,
  onRenameRequest,
  onOpenRequest,
  onGroupToggle,
  folded,
  connect,
  onConnectPick,
  onRendered,
}: AgentTimelineProps): JSX.Element {
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const brushLayerRef = useRef<SVGGElement | null>(null)

  const [width, setWidth] = useState<number>(DEFAULT_WIDTH)
  /** Tooltip CONTENT only — position lives in a ref so mouse moves never re-render. */
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  /** User-selected time window (null = full extent). */
  const [zoomDomain, setZoomDomain] = useState<[Date, Date] | null>(null)

  // Tooltip position: written straight to the DOM inside rAF, never state.
  const { tipRef, tipPosRef, placeTip } = useTipPlacement(wrapperRef)

  // Observe container width — SVG's viewBox handles proportional scale but
  // we still want to recompute the x-scale in real pixels for crisp ticks.
  useLayoutEffect(() => {
    const el = wrapperRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        const w = e.contentRect.width
        if (w > 0) setWidth(w)
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // ------- data derivations (pure, memoised) ------------------------------

  const lanes = useMemo(() => buildLanes(agents), [agents])
  const edges = useMemo(() => buildEdges(lanes), [lanes])
  const groups = useMemo(() => buildGroups(lanes), [lanes])
  const laneById = useMemo(() => new Map(lanes.map((l) => [l.agent.agent_id, l])), [lanes])

  const fullDomain: [Date, Date] | null = useMemo(() => fullDomainOf(lanes), [lanes])

  const activeDomain = zoomDomain ?? fullDomain

  const hasLabelControls = !!(onRenameRequest || onOpenRequest)
  const marginLeft = hasLabelControls ? LEFT_WITH_CONTROLS : MARGIN.left
  const innerHeight = Math.max(MIN_INNER_HEIGHT, lanes.length * ROW_HEIGHT)
  const totalHeight = height ?? innerHeight + MARGIN.top + MARGIN.bottom
  const innerWidth = Math.max(200, width - marginLeft - MARGIN.right)

  const xScale = useMemo(() => {
    if (!activeDomain) return null
    return scaleTime().domain(activeDomain).range([0, innerWidth]).nice()
  }, [activeDomain, innerWidth])

  const yFor = useCallback(
    (index: number) => index * ROW_HEIGHT + ROW_HEIGHT / 2,
    [],
  )

  // ------- tick / link / mark derivations (memoised on their real inputs) --

  const spanDays = activeDomain
    ? (activeDomain[1].getTime() - activeDomain[0].getTime()) / 86_400_000
    : 0

  // Auto-picked date ticks — d3.timeTicks chooses good round intervals.
  const dateTicks = useMemo(
    () =>
      xScale
        ? xScale.ticks(tickCountFor(innerWidth))
        : [],
    [xScale, innerWidth],
  )
  const tickFormat = useMemo(
    // English keeps d3's short months; Russian takes Intl's ("12 сент.").
    () => currentLang() === 'ru'
      ? (d: Date) => d.toLocaleDateString(locale(), spanDays > 120 ? { month: 'short', year: 'numeric' } : { day: 'numeric', month: 'short' })
      : timeFormat(spanDays > 120 ? '%b %Y' : '%b %d'),
    [spanDays],
  )

  // Week grid: every Monday between domain endpoints (only when span reasonable).
  const weekTicks = useMemo<Date[]>(
    () => weekTicksFor(activeDomain, spanDays),
    [activeDomain, spanDays],
  )

  /** Resolved geometry for every drawable link. */
  const drawnLinks = useMemo(() => {
    if (!xScale) return []
    return resolveLinks(links, laneById, xScale, yFor)
  }, [links, laneById, xScale, yFor])

  /** Per-lane hour buckets (merged under renderMark), keyed by agent id. */
  const markEntries = useMemo(() => {
    if (!marks || !xScale) return new Map<string, Array<[number, LaneMark[]]>>()
    return bucketMarks(marks, lanes, !!renderMark, xScale)
  }, [marks, lanes, renderMark, xScale])

  // ------- brush-to-zoom (P1 advanced) ------------------------------------

  useEffect(() => {
    if (!xScale) return
    const layer = brushLayerRef.current
    if (!layer) return

    const brush = brushX<unknown>()
      .extent([
        [0, 0],
        [innerWidth, innerHeight],
      ])
      .on('end', (event) => {
        // Ignore programmatic / empty clears — those are just resets.
        if (!event.sourceEvent) return
        if (!event.selection) return
        const [x0, x1] = event.selection as [number, number]
        if (Math.abs(x1 - x0) < 8) return // ignore accidental micro-drags
        const d0 = xScale.invert(x0)
        const d1 = xScale.invert(x1)
        setZoomDomain([d0, d1])
        // Clear the visual brush rectangle after committing.
        select(layer).call(brush.move, null)
      })

    const sel = select(layer)
    sel.call(brush)
    // Double-click resets zoom.
    sel.on('dblclick', () => setZoomDomain(null))

    return () => {
      // Remove listeners d3-brush attached to this group.
      sel.on('.brush', null).on('dblclick', null)
      sel.selectAll('*').remove()
    }
  }, [xScale, innerWidth, innerHeight])

  // ------- render-time perf callback --------------------------------------

  useEffect(() => {
    if (!onRendered) return
    const start =
      typeof performance !== 'undefined' ? performance.now() : Date.now()
    // Schedule after paint via double-rAF (works in test envs too).
    const raf =
      typeof requestAnimationFrame !== 'undefined'
        ? requestAnimationFrame(() => {
            const end =
              typeof performance !== 'undefined'
                ? performance.now()
                : Date.now()
            onRendered(end - start)
          })
        : 0
    return () => {
      if (raf) cancelAnimationFrame(raf)
    }
  }, [lanes, edges, width, onRendered])

  // ------- empty state ----------------------------------------------------

  if (lanes.length === 0 || !xScale || !activeDomain) {
    return (
      <div
        ref={wrapperRef}
        className={`w-full ${className}`}
        role="figure"
        aria-label={t('Agent branching timeline (empty)')}
      >
        <TimelineEmpty />
      </div>
    )
  }

  const today = new Date()
  const todayX = xScale(today)
  const todayVisible = todayX >= 0 && todayX <= innerWidth

  const connecting = !!connect?.active
  const connectFrom = connect?.from
  // With controls the name ends earlier so ✎ and 👁 have room.
  // …and a gutter of ~24px keeps the eye clear of the chart's first grid line.
  const labelEndX = hasLabelControls ? -60 : -14
  const nameMax = groups.length > 0 ? 18 : 20

  /** Date under a pointer event, in chart coordinates. */
  const dateAt = (evt: { clientX: number }): Date => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return new Date()
    const px = (evt.clientX - rect.left) * (width / rect.width) - marginLeft
    return xScale.invert(Math.min(Math.max(px, 0), innerWidth))
  }

  const hover = { placeTip, setTooltip }

  // ------- render ---------------------------------------------------------

  return (
    <div
      ref={wrapperRef}
      className={`relative w-full ${className}`}
      style={{ '--timeline-row-height': `${ROW_HEIGHT}px` } as CSSProperties}
    >
      {/* Sr-only controls / reset affordance */}
      {zoomDomain && (
        <button
          type="button"
          onClick={() => setZoomDomain(null)}
          className="absolute right-8 top-8 z-sticky rounded-input border border-border-default bg-elevated px-8 py-4 text-11 text-secondary shadow-sm transition-colors duration-fast ease-out hover:bg-hover hover:text-primary"
          aria-label={t('Reset timeline zoom')}
        >
          {t('Reset zoom')}
        </button>
      )}

      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${totalHeight}`}
        preserveAspectRatio="xMinYMin meet"
        width="100%"
        height={totalHeight}
        role="img"
        aria-label={tn(lanes.length, 'Agent branching timeline with {n} agent', 'Agent branching timeline with {n} agents')}
        style={{
          fontFamily: 'var(--font-sans)',
          fontVariantNumeric: 'tabular-nums',
          background: 'var(--bg-surface)',
          borderRadius: 'var(--radius-card)',
          border: connecting ? '1px dashed var(--brand)' : '1px solid var(--border-default)',
        }}
        onMouseLeave={() => setTooltip(null)}
      >
        <title>{t('Agent branching timeline')}</title>
        <desc>
          {t('Swim-lane chart, one row per agent. Bars run from created date to last-active date. Cubic-bezier curves connect parent agents to their child (spawned) agents; operator-drawn links are curves in their own style with a dot that holds the note. Vertical dashed line marks today.')}
        </desc>

        {/* --- Chart area origin --- */}
        <g transform={`translate(${marginLeft},${MARGIN.top})`}>
          <LaneRows
            lanes={lanes}
            marginLeft={marginLeft}
            innerWidth={innerWidth}
            connectFrom={connectFrom}
            connecting={connecting}
            onConnectPick={onConnectPick}
            dateAt={dateAt}
          />

          <WeekGrid weekTicks={weekTicks} xScale={xScale} innerHeight={innerHeight} />

          <GroupBrackets groups={groups} marginLeft={marginLeft} onGroupToggle={onGroupToggle} folded={folded} />

          <LaneLabels
            lanes={lanes}
            yFor={yFor}
            labelEndX={labelEndX}
            nameMax={nameMax}
            connectFrom={connectFrom}
            connecting={connecting}
            onConnectPick={onConnectPick}
            onGroupToggle={onGroupToggle}
            onRenameRequest={onRenameRequest}
            onOpenRequest={onOpenRequest}
          />

          <DateAxes dateTicks={dateTicks} tickFormat={tickFormat} xScale={xScale} innerHeight={innerHeight} todayX={todayVisible ? todayX : null} />

          <ParentEdges edges={edges} xScale={xScale} yFor={yFor} />

          <LinkLines drawnLinks={drawnLinks} />

          <LaneBars
            lanes={lanes}
            xScale={xScale}
            yFor={yFor}
            connectFrom={connectFrom}
            connecting={connecting}
            onConnectPick={onConnectPick}
            onAgentClick={onAgentClick}
            dateAt={dateAt}
            {...hover}
          />

          {todayVisible && <TodayMarker todayX={todayX} innerHeight={innerHeight} />}

          {/* Brush layer — sits on top, transparent, captures drags. Off in
              connect mode so the picks land on the bars. */}
          {!connecting && (
            <g
              ref={brushLayerRef}
              data-testid="brush-layer"
              className="agent-timeline-brush"
            />
          )}

          <LinkHits drawnLinks={drawnLinks} onLinkClick={onLinkClick} {...hover} />

          <LinkDots drawnLinks={drawnLinks} onLinkClick={onLinkClick} {...hover} />

          {marks && (
            <TaskMarks
              lanes={lanes}
              markEntries={markEntries}
              xScale={xScale}
              yFor={yFor}
              innerWidth={innerWidth}
              connecting={connecting}
              onConnectPick={onConnectPick}
              onMarkClick={onMarkClick}
              renderMark={renderMark}
              dateAt={dateAt}
              {...hover}
            />
          )}
        </g>
      </svg>

      {/* Hover tooltip — see TooltipLayer */}
      {tooltip && (
        <TooltipLayer tipRef={tipRef} pos={tipPosRef.current} state={tooltip} swatch={markSwatch} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TimelineEmpty(): JSX.Element {
  return (
    <EmptyState
      title={t('This project has no agents yet')}
      subtitle={
        <>
          {t("Start an agent in this project's folder and it appears here as a row. A row is linked to the agent that started it, when that is recorded.")}
        </>
      }
    />
  )
}
