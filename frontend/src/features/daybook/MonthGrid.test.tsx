import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MonthGrid } from './MonthGrid'
import { ZERO } from './data'

describe('MonthGrid', () => {
  it('renders one cell per day of the month and calls back with the day', () => {
    const onPick = vi.fn()
    render(<MonthGrid month="2026-02" days={{ '2602-10': { ...ZERO, messages_n: 8, commits_n: 2, standup_id: 'st_1' } }}
      onPick={onPick} onMonth={() => {}} />)
    const cells = screen.getAllByRole('gridcell')
    expect(cells).toHaveLength(28)
    const busy = cells.find((c) => c.getAttribute('data-day') === '2602-10')!
    expect(busy.getAttribute('data-level')).toBe('4')
    expect(busy.getAttribute('aria-label')).toBe('10 February · 8 messages · 2 commits · standup')
    expect(cells[0]!.getAttribute('data-level')).toBe('0')
    fireEvent.click(busy)
    expect(onPick).toHaveBeenCalledWith('2602-10')
  })
  it('steps the intensity against the busiest day', () => {
    render(<MonthGrid month="2026-03" days={{ '2603-01': { ...ZERO, messages_n: 100 }, '2603-02': { ...ZERO, messages_n: 10 } }}
      onPick={() => {}} onMonth={() => {}} />)
    const by = (d: string) => screen.getAllByRole('gridcell').find((c) => c.getAttribute('data-day') === d)!
    expect(by('2603-01').getAttribute('data-level')).toBe('4')
    expect(by('2603-02').getAttribute('data-level')).toBe('1')
    expect(screen.getAllByRole('gridcell')).toHaveLength(31)
  })
})
