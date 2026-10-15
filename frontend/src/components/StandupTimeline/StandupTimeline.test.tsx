import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { StandupTimeline } from './StandupTimeline'
import type { StandupRow, StandupsListResponse } from './types'

afterEach(cleanup)

const row = (id: string, l1: string): StandupRow => ({
  id, created_date: '2610-05', project: 'p', agent_id: 'cc-a', l1, goals_open_n: 1, goals_closed_n: 0, blockers_n: 0, hours_today: 1,
})

describe('StandupTimeline', () => {
  it('an open row keeps its detail when a new standup lands in the list', async () => {
    let list: StandupsListResponse = { total: 1, standups: [row('su_1', 'first day')] }
    const fetchList = vi.fn(async () => list)
    const fetchDetail = vi.fn(async (id: string) => ({ metadata: row(id, ''), l2: `since last for ${id}`, l3: [], l4: '' }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><StandupTimeline fetchList={fetchList} fetchDetail={fetchDetail} /></QueryClientProvider>)
    fireEvent.click(await screen.findByText('first day'))
    expect(await screen.findByText('since last for su_1')).toBeInTheDocument()
    list = { total: 2, standups: [row('su_2', 'second day'), row('su_1', 'first day')] }
    await act(async () => { await qc.refetchQueries({ queryKey: ['standups'], exact: true }) })
    expect(await screen.findByText('second day')).toBeInTheDocument()
    expect(screen.getByText('since last for su_1')).toBeInTheDocument()
  })

  it('a failed detail says so and reads again on retry', async () => {
    const fetchList = vi.fn(async () => ({ total: 1, standups: [row('su_1', 'first day')] }))
    let fail = true
    const fetchDetail = vi.fn(async (id: string) => {
      if (fail) throw new Error('the server is busy')
      return { metadata: row(id, ''), l2: 'it worked', l3: [], l4: '' }
    })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><StandupTimeline fetchList={fetchList} fetchDetail={fetchDetail} /></QueryClientProvider>)
    fireEvent.click(await screen.findByText('first day'))
    expect(await screen.findByText(/the server is busy/)).toBeInTheDocument()
    fail = false
    fireEvent.click(screen.getByText(/Retry/))
    expect(await screen.findByText('it worked')).toBeInTheDocument()
  })
})
