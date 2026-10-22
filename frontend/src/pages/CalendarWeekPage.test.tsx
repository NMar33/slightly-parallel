import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { CalendarTab } from '../features/calendar/CalendarTab'
import { addDays, isoToday, startOfWeek } from '../features/calendar/model'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.history.replaceState(null, '', '/') })

const payload = (from: string, to: string) => ({
  project: 'p', projects: ['p'], from, to, today: isoToday(), days: {}, tasks: [], entries: [], milestones: [], sprints: [], sessions: [],
})

describe('CalendarWeekPage', () => {
  it('moves the picked day with the week, so the pane reads a day the range holds', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = new URL(url, 'http://x')
      const body = u.pathname === '/api/calendar' ? payload(u.searchParams.get('from')!, u.searchParams.get('to')!)
        : u.pathname === '/api/boards' ? { boards: [] } : { projects: [{ code: 'p' }] }
      return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => JSON.stringify(body) }
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    // The product path: the project's calendar tab, on its week view.
    window.history.replaceState(null, '', '/#view=week')
    render(<QueryClientProvider client={qc}><MemoryRouter><CalendarTab projectCode="p" /></MemoryRouter></QueryClientProvider>)
    await screen.findByLabelText('Picked day', undefined, { timeout: 10000 })
    const today = isoToday()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Previous week' })) })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Previous week' })) })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Previous week' })) })
    const hash = new URLSearchParams(window.location.hash.slice(1))
    expect(hash.get('week')).toBe(addDays(startOfWeek(today), -21))
    expect(hash.get('sel')).toBe(addDays(today, -21))
    // The first render loads the lazy calendar views: under a full parallel
    // run it outlasts the default 5 s, as the 10 s wait above allows for.
  }, 20_000)
})
