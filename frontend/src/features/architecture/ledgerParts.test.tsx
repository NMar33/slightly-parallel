/**
 * The owes strip — owed, but never a wall.
 *
 * 1. one or two items are listed; three or more is one sentence that opens
 * 2. actions come before debts, in the sentence and in the list
 * 3. one × puts one item away; the header's × puts away what is shown
 * 4. everything dismissed collapses to a quiet line that can bring it back
 * 5. a new item — an id nobody dismissed — reopens the strip by itself
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { OwesStrip, owesSummary } from './ledgerParts'
import type { Change } from './ledger'

function owe(n: number, type: 'debt' | 'action-needed' = 'debt'): Change {
  return {
    id: `ar_${String(n).padStart(6, '0')}`,
    created_date: '2609-02', created_time: '10:00', agent_id: 'cc-a',
    op: 'add', type, group: 'owes', name: `owed thing ${n}`,
    path: [], note: '', task: '', decision: '',
    fields: type === 'debt' ? { risk: `risk ${n}` } : { action: `do ${n}` },
    trigger_id: '',
  }
}

const rows10 = Array.from({ length: 10 }, (_, i) => owe(i + 1))

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })))
})

describe('owesSummary', () => {
  it('counts actions first, and names only what is there', () => {
    expect(owesSummary([owe(1)])).toBe('1 debt')
    expect(owesSummary([owe(1), owe(2)])).toBe('2 debts')
    expect(owesSummary([owe(1, 'action-needed')])).toBe('1 action')
    expect(owesSummary([owe(1), owe(2), owe(3, 'action-needed')])).toBe('1 action and 2 debts')
  })
})

describe('OwesStrip', () => {
  it('lists one or two items as they are', () => {
    render(<OwesStrip rows={[owe(1), owe(2)]} />)
    expect(screen.getByText(/standing — debt & actions · 2/)).toBeTruthy()
    expect(screen.getAllByText(/owed thing/)).toHaveLength(2)
    expect(screen.queryByText(/You have/)).toBeNull()
  })

  it('says three or more in one sentence, and opens on a word', () => {
    render(<OwesStrip rows={[...rows10.slice(0, 9), owe(11, 'action-needed')]} />)
    expect(screen.getByText('You have 1 action and 9 debts standing.')).toBeTruthy()
    expect(screen.queryByText(/owed thing/)).toBeNull()

    fireEvent.click(screen.getByText('show'))
    expect(screen.getAllByText(/owed thing/)).toHaveLength(10)
    // the action is first in the list too
    expect(screen.getAllByText(/owed thing/)[0]!.textContent).toBe('owed thing 11')

    fireEvent.click(screen.getByText('fold'))
    expect(screen.getByText('You have 1 action and 9 debts standing.')).toBeTruthy()
  })

  it('puts one away with its own ×, and the rest stay', () => {
    render(<OwesStrip rows={rows10} />)
    fireEvent.click(screen.getByText('show'))
    fireEvent.click(screen.getByLabelText('Dismiss: owed thing 1'))
    expect(screen.queryByText('owed thing 1')).toBeNull()
    expect(screen.getByText(/standing — debt & actions · 9/)).toBeTruthy()
    expect(screen.getByText('1 dismissed · show')).toBeTruthy()
    expect(JSON.parse(localStorage.getItem('sp-owes-dismissed')!)).toEqual(['ar_000001'])
  })

  it('the header × collapses the strip to a quiet line that restores it', () => {
    const { rerender } = render(<OwesStrip rows={rows10} />)
    fireEvent.click(screen.getByLabelText('Dismiss all'))
    expect(screen.queryByText(/standing — debt/)).toBeNull()
    expect(screen.queryByText(/You have/)).toBeNull()
    const quiet = screen.getByText('10 items dismissed · show')
    expect(JSON.parse(localStorage.getItem('sp-owes-dismissed')!)).toHaveLength(10)

    fireEvent.click(quiet)
    expect(screen.getAllByText(/owed thing/)).toHaveLength(10)

    // a debt paid off simply stops arriving; the strip stays quiet
    rerender(<OwesStrip rows={rows10.slice(0, 3)} />)
    expect(screen.getAllByText(/owed thing/)).toHaveLength(3)
  })

  it('a new item reopens the strip, on its own', () => {
    const { rerender } = render(<OwesStrip rows={rows10} />)
    fireEvent.click(screen.getByLabelText('Dismiss all'))
    expect(screen.queryByText(/standing — debt/)).toBeNull()

    rerender(<OwesStrip rows={[...rows10, owe(11, 'action-needed')]} />)
    expect(screen.getByText(/standing — debt & actions · 1$/)).toBeTruthy()
    expect(screen.getByText('owed thing 11')).toBeTruthy()
    expect(screen.getByText('10 dismissed · show')).toBeTruthy()
  })

  it('renders nothing when nothing is owed', () => {
    const { container } = render(<OwesStrip rows={[]} />)
    expect(container.firstChild).toBeNull()
  })
})
