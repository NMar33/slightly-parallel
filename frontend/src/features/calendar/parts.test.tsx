import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MonthPicker, QuickAdd } from './parts'

function wrap(node: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>
}

describe('QuickAdd under a scope', () => {
  beforeEach(() => localStorage.clear())

  it('starts over with the new scope\'s projects when keyed by the scope', () => {
    localStorage.setItem('sp-calendar-project', 'b')
    const { rerender } = render(wrap(<QuickAdd key="a,b" project="a,b" projects={['a', 'b']} date="2026-09-17" onTask={vi.fn()} />))
    expect((screen.getByLabelText('project for the line') as HTMLSelectElement).value).toBe('b')
    rerender(wrap(<QuickAdd key="c,d" project="c,d" projects={['c', 'd']} date="2026-09-17" onTask={vi.fn()} />))
    expect((screen.getByLabelText('project for the line') as HTMLSelectElement).value).toBe('c')
  })
})

describe('the month picker\'s year field', () => {
  it('follows a whole year only, and goes back to the shown year when left half-typed', () => {
    render(<MonthPicker month="2026-09" label="Sep 2026" today="2026-09" onPick={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Sep 2026' }))
    const year = screen.getByLabelText('Year') as HTMLInputElement
    expect(year.value).toBe('2026')

    fireEvent.change(year, { target: { value: '20' } })
    expect(year.value).toBe('20')
    expect(screen.getByRole('button', { name: 'Jan 2026' })).toBeInTheDocument()

    fireEvent.change(year, { target: { value: '2031' } })
    expect(screen.getByRole('button', { name: 'Jan 2031' })).toBeInTheDocument()

    fireEvent.change(year, { target: { value: '2' } })
    fireEvent.blur(year)
    expect(year.value).toBe('2031')
    expect(screen.getByRole('button', { name: 'Jan 2031' })).toBeInTheDocument()
  })
})
