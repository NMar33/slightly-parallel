import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MonthBand } from './MonthBand'
import { ZERO } from './data'

const DAYS = {
  '2609-01': { ...ZERO, messages_n: 10 },
  '2609-02': { ...ZERO, messages_n: 4, commits_n: 2 },
}

describe('the month band', () => {
  it('marks the days that have an entry of this kind, and says what it is', () => {
    render(<MonthBand month="2026-09" days={DAYS} marked={new Set(['2609-02'])} markWord="scan"
      totals={<span>1 scan</span>} onPick={() => {}} onMonth={() => {}} emptyWord="No scan this month." />)
    expect(screen.getByRole('gridcell', { name: /^2 September .*· scan$/ })).toBeInTheDocument()
    expect(screen.getByRole('gridcell', { name: '1 September · 10 messages' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Days with a scan' })).toBeInTheDocument()
    expect(screen.getByText('1 scan')).toBeInTheDocument()
  })
  it('says when the month has none', () => {
    render(<MonthBand month="2026-09" days={DAYS} marked={new Set()} markWord="decision"
      totals={null} onPick={() => {}} onMonth={() => {}} emptyWord="No decision this month." />)
    expect(screen.getByText('No decision this month.')).toBeInTheDocument()
  })
  it('gives the month before and after when the arrows are pressed', () => {
    const onMonth = vi.fn()
    render(<MonthBand month="2026-09" days={DAYS} marked={new Set()} markWord="scan"
      totals={null} onPick={() => {}} onMonth={onMonth} emptyWord="none" />)
    screen.getByRole('button', { name: 'Previous month' }).click()
    screen.getByRole('button', { name: 'Next month' }).click()
    expect(onMonth.mock.calls.map((c) => c[0])).toEqual(['2026-08', '2026-10'])
  })
})
