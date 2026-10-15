import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, within, fireEvent, cleanup } from '@testing-library/react'
import { DecisionLog } from './DecisionLog'
import type { Decision } from './types'

const decisions: Decision[] = [
  {
    id: 'd-1',
    decision_text: 'Adopt jade #4FB39A as brand accent',
    rationale: 'Distinct from Linear indigo and PostHog orange; signals calibration.',
    source: 'explicit',
    agent_id: 'aesthetic-critic',
    related_goal_id: 'g-brand',
    tags: ['design', 'brand'],
    created_date: '2608-06',
    project: 'PDR',
  },
  {
    id: 'd-2',
    decision_text: 'Отказаться от Framer Motion в MVP',
    rationale: 'CSS transitions покрывают все требования; экономия 20кб бандла.',
    source: 'auto',
    agent_id: 'eng-critic',
    tags: ['frontend'],
    created_date: '2608-05',
    project: 'PDR',
  },
  {
    id: 'd-3',
    decision_text: 'Cut Docker from MVP deploy',
    rationale: './run.sh is simpler on Ubuntu; add Dockerfile as appendix only.',
    source: 'explicit',
    agent_id: 'product-critic',
    tags: ['deploy'],
    created_date: '2608-04',
    project: 'quizforge',
  },
]

describe('DecisionLog', () => {
  beforeEach(() => cleanup())

  it('renders every decision row by default', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn />)
    expect(screen.getByText(/Adopt jade/)).toBeTruthy()
    expect(screen.getByText(/Отказаться от Framer Motion/)).toBeTruthy()
    expect(screen.getByText(/Cut Docker/)).toBeTruthy()
    expect(screen.getByText('Showing 3 of 3')).toBeTruthy()
  })

  it('filters by source chip (explicit / auto)', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn />)
    fireEvent.click(screen.getByRole('button', { name: 'Auto' }))
    expect(screen.getByText('Showing 1 of 3')).toBeTruthy()
    expect(screen.getByText(/Отказаться от Framer Motion/)).toBeTruthy()
    expect(screen.queryByText(/Adopt jade/)).toBeNull()
  })

  it('filters by project chip', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn />)
    fireEvent.click(screen.getByRole('button', { name: 'quizforge' }))
    expect(screen.getByText('Showing 1 of 3')).toBeTruthy()
    expect(screen.getByText(/Cut Docker/)).toBeTruthy()
  })

  it('searches Cyrillic text case-insensitively', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn />)
    const search = screen.getByLabelText('Search decisions') as HTMLInputElement
    // "ОТКАЗАТЬСЯ" (upper-case) must match "Отказаться…" in d-2's decision_text.
    fireEvent.change(search, { target: { value: 'ОТКАЗАТЬСЯ' } })
    expect(screen.getByText('Showing 1 of 3')).toBeTruthy()
    expect(screen.getByText(/Отказаться от Framer Motion/)).toBeTruthy()
  })

  it('shows empty state with filter hint when no matches', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn />)
    const search = screen.getByLabelText('Search decisions') as HTMLInputElement
    fireEvent.change(search, { target: { value: 'zzzzzz-no-match' } })
    expect(screen.getByText(/No decisions match these filters/)).toBeTruthy()
  })

  it('shows empty state (no filters) when list is empty', () => {
    render(<DecisionLog decisions={[]} showProjectColumn />)
    expect(screen.getByText(/No decisions yet/)).toBeTruthy()
  })

  it('expands a row to reveal detail metadata', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn />)
    const rowButton = screen.getByRole('button', { name: /Adopt jade/ })
    expect(rowButton.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(rowButton)
    expect(rowButton.getAttribute('aria-expanded')).toBe('true')
    const detail = document.getElementById('decision-detail-d-1')!
    expect(detail).toBeTruthy()
    expect(within(detail).getByText('Rationale')).toBeTruthy()
    expect(within(detail).getByText('#design')).toBeTruthy()
  })

  it('filters by date range (inclusive, lex-sorted YYMM-DD)', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn />)
    const from = screen.getByLabelText('From date YYMM-DD') as HTMLInputElement
    fireEvent.change(from, { target: { value: '2608-05' } })
    // 2608-05 and 2608-06 remain; 2608-04 excluded.
    expect(screen.getByText('Showing 2 of 3')).toBeTruthy()
  })

  it('hides the project column when showProjectColumn=false', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn={false} />)
    // Project filter group label should not appear.
    expect(screen.queryByText('Project')).toBeNull()
  })

  it('clears all filters via the Clear button', () => {
    render(<DecisionLog decisions={decisions} showProjectColumn />)
    fireEvent.click(screen.getByRole('button', { name: 'Auto' }))
    expect(screen.getByText('Showing 1 of 3')).toBeTruthy()
    const clear = screen.getByRole('button', { name: /Clear \(1\)/ })
    fireEvent.click(clear)
    expect(screen.getByText('Showing 3 of 3')).toBeTruthy()
  })
})
