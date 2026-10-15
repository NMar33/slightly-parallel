/**
 * Vitest tests for AgentTimeline.
 *
 * We prefer structural assertions + a snapshot over pixel diffs — snapshots
 * are stable because the layout math is deterministic from the fixture data
 * and MARGIN/ROW_HEIGHT constants.
 */

import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

import { AgentTimeline, type AgentMeta } from './AgentTimeline'

// ---------------------------------------------------------------------------
// Setup: jsdom lacks ResizeObserver; freeze time so the TODAY marker's
// x-coordinate is deterministic across CI runs (snapshot stability).
// ---------------------------------------------------------------------------

beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  ;(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver =
    (globalThis as unknown as { ResizeObserver?: typeof RO }).ResizeObserver ??
    RO
  // Freeze "now" to a value inside the fixture's domain so TODAY renders
  // consistently. Any date between the earliest created_date and latest
  // last_active in FIXTURE works — pick 2608-05. Local noon, not a UTC
  // instant: the chart reads the fixture's days as local midnights, so a
  // UTC "now" would move the marker with the machine's time zone.
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 7, 5, 12, 0, 0))
})

afterAll(() => {
  vi.useRealTimers()
})

afterEach(() => {
  cleanup()
})

// ---------------------------------------------------------------------------
// Fixture — three-agent lineage that exercises every code path.
// ---------------------------------------------------------------------------

const FIXTURE: AgentMeta[] = [
  {
    agent_id: 'agent-alpha',
    agent_name: 'alpha-planner',
    project: 'quizforge',
    parent_agent_id: null,
    created_date: '2607-15',
    last_active: '2607-28',
    message_count: 42,
    l1_headline: 'Seeded first-pass рекогниция strategy.',
  },
  {
    agent_id: 'agent-beta',
    agent_name: 'beta-builder',
    project: 'quizforge',
    parent_agent_id: 'agent-alpha',
    created_date: '2607-22',
    last_active: '2608-04',
    message_count: 118,
    l1_headline: 'Implemented CSV ingest with файловый locks.',
  },
  {
    agent_id: 'agent-gamma',
    agent_name: 'gamma-verifier',
    project: 'quizforge',
    parent_agent_id: 'agent-beta',
    created_date: '2608-01',
    last_active: '2608-06',
    message_count: 33,
    l1_headline: 'Verified end-to-end fixture bootstrap.',
  },
]

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('<AgentTimeline />', () => {
  it('renders the empty state when given no agents', () => {
    const { getByRole, container } = render(<AgentTimeline agents={[]} />)
    expect(getByRole('status')).toHaveTextContent(
      /this project has no agents yet/i,
    )
    expect(container.querySelector('svg')).toBeNull()
  })

  it('renders the empty state when all rows have unparseable dates', () => {
    const bad: AgentMeta[] = [
      {
        agent_id: 'x',
        created_date: 'not-a-date',
        last_active: 'nope',
      },
    ]
    const { getByRole } = render(<AgentTimeline agents={bad} />)
    expect(getByRole('status')).toBeInTheDocument()
  })

  it('renders one lane per agent with Cyrillic-safe labels', () => {
    const { container, getByText } = render(<AgentTimeline agents={FIXTURE} />)
    expect(container.querySelector('svg')).not.toBeNull()

    // Each agent name appears as a label text node.
    expect(getByText('alpha-planner')).toBeInTheDocument()
    expect(getByText('beta-builder')).toBeInTheDocument()
    expect(getByText('gamma-verifier')).toBeInTheDocument()

    // One bar per lane (bar rects use rx=4 by design).
    const bars = container.querySelectorAll('rect[rx="4"]')
    expect(bars.length).toBe(FIXTURE.length)
  })

  it('draws one parent→child bezier per resolvable parent link', () => {
    const { container } = render(<AgentTimeline agents={FIXTURE} />)
    // Bezier paths start with "M" and contain "C" (cubic).
    const paths = Array.from(container.querySelectorAll('path')).filter((p) =>
      /^M .* C /.test(p.getAttribute('d') ?? ''),
    )
    // Fixture has 2 parent links: alpha→beta and beta→gamma.
    expect(paths.length).toBe(2)
  })

  it('skips edges when the parent is not in the visible set', () => {
    const orphaned: AgentMeta[] = [
      {
        agent_id: 'lonely',
        agent_name: 'lonely-child',
        parent_agent_id: 'ghost-parent-not-in-list',
        created_date: '2608-01',
        last_active: '2608-05',
      },
    ]
    const { container } = render(<AgentTimeline agents={orphaned} />)
    const paths = Array.from(container.querySelectorAll('path')).filter((p) =>
      /^M .* C /.test(p.getAttribute('d') ?? ''),
    )
    expect(paths.length).toBe(0)
  })

  it('renders a TODAY marker inside the chart', () => {
    const { getByText } = render(<AgentTimeline agents={FIXTURE} />)
    expect(getByText('TODAY')).toBeInTheDocument()
  })

  it('fires onAgentClick with the clicked agent', () => {
    const spy = vi.fn()
    const { container } = render(
      <AgentTimeline agents={FIXTURE} onAgentClick={spy} />,
    )
    const bars = container.querySelectorAll('rect[rx="4"]')
    expect(bars.length).toBeGreaterThan(0)
    // Bars are wrapped in <g>; the click handler is on the group.
    fireEvent.click(bars[0].parentElement as Element)
    expect(spy).toHaveBeenCalledTimes(1)
    // First lane (post-sort) is chronologically earliest: agent-alpha.
    expect(spy.mock.calls[0][0].agent_id).toBe('agent-alpha')
  })

  it('shows a tooltip on hover with headline and message count', () => {
    const { container, getByRole } = render(
      <AgentTimeline agents={FIXTURE} />,
    )
    const bars = container.querySelectorAll('rect[rx="4"]')
    fireEvent.mouseEnter(bars[1].parentElement as Element, {
      clientX: 100,
      clientY: 100,
    })
    const tip = getByRole('tooltip')
    expect(tip).toHaveTextContent('beta-builder')
    expect(tip).toHaveTextContent(/файловый/) // Cyrillic passes through
    expect(tip).toHaveTextContent('118')
  })

  it('exposes an accessible SVG role and label', () => {
    const { getByRole } = render(<AgentTimeline agents={FIXTURE} />)
    const svg = getByRole('img')
    expect(svg.getAttribute('aria-label')).toMatch(
      /agent branching timeline with 3 agents/i,
    )
  })

  it('produces a stable snapshot for the fixture', () => {
    const { container } = render(<AgentTimeline agents={FIXTURE} />)
    // Snapshot the SVG only — the wrapper div contains a Math.random-free
    // deterministic structure. If layout constants change intentionally the
    // snapshot updates in one place.
    expect(container.querySelector('svg')).toMatchSnapshot()
  })
})
