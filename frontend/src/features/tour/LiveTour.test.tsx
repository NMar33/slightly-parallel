/**
 * The live tour over the router.
 *
 * What is held here: a tour is one entry in the browser's history, the
 * page's own hash survives it, keys typed into a field stay in the field,
 * and a step whose example entry was removed offers to put it back.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation, useNavigate, useNavigationType } from 'react-router-dom'

import { LiveTour, tourHref } from './LiveTour'
import { PRESETS, walkable } from './script'

const skills = PRESETS.find((s) => s.id === 'skills')!
const steps = walkable(skills).length

type Seen = { pathname: string; search: string; hash: string; type: string; back: () => void }
let seen: Seen

function Probe() {
  const loc = useLocation()
  const type = useNavigationType()
  const navigate = useNavigate()
  seen = { pathname: loc.pathname, search: loc.search, hash: loc.hash, type, back: () => navigate(-1) }
  return <input aria-label="Find in skills" />
}

function mount(entries: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={entries}>
        <Probe />
        <LiveTour />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/api/examples/state')) {
      return { ok: true, json: async () => ({ present: [], removed: ['sk_e0000001'], all: ['sk_e0000001'] }) }
    }
    if (url.endsWith('/api/examples/restore')) {
      return { ok: true, json: async () => ({ added: ['sk_e0000001'] }) }
    }
    return { ok: true, json: async () => ({}) }
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

describe('the address of a step', () => {
  it('carries the page hash when the beat has none of its own', () => {
    expect(tourHref(skills, 0, '#skill=sk_x')).toBe('/skills?tour=skills&step=0#skill=sk_x')
    expect(tourHref(skills, 1)).toBe('/skills?tour=skills&step=1')
  })

  it('lets a beat with a hash keep it', () => {
    const full = PRESETS.find((s) => s.id === 'full')!
    const at = walkable(full).findIndex((b) => b.page.includes('#'))
    expect(tourHref(full, at, '#other')).not.toContain('other')
  })

  it('keeps a beat\u2019s own query beside the tour\u2019s', () => {
    const full = PRESETS.find((s) => s.id === 'full')!
    const at = walkable(full).findIndex((b) => b.page.startsWith('/search?'))
    expect(tourHref(full, at)).toBe(`/search?q=refund&tour=full&step=${at}`)
  })
})

describe('walking', () => {
  it('replaces the history entry on Next and keeps the open skill', () => {
    mount(['/skills#skill=sk_x', '/skills?tour=skills&step=0#skill=sk_x'])
    expect(screen.getByRole('dialog', { name: 'Product tour' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(seen.search).toBe('?tour=skills&step=1')
    expect(seen.hash).toBe('#skill=sk_x')
    expect(seen.type).toBe('REPLACE')
  })

  it('Done restores the page and Back leaves the tour behind', () => {
    mount(['/skills#skill=sk_x', `/skills?tour=skills&step=${steps - 1}#skill=sk_x`])
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(seen.pathname).toBe('/skills')
    expect(seen.search).toBe('')
    expect(seen.hash).toBe('#skill=sk_x')
    expect(screen.queryByRole('dialog')).toBeNull()
    act(() => seen.back())
    expect(seen.search).not.toContain('tour=')
  })

  it('leaves the hash alone while the beat names none', () => {
    mount(['/skills?tour=skills&step=0#skill=sk_x'])
    expect(seen.hash).toBe('#skill=sk_x')
    expect(seen.search).toBe('?tour=skills&step=0')
  })
})

describe('keys', () => {
  it('move the tour from the page, and stay in a field', () => {
    mount(['/skills?tour=skills&step=0'])
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(seen.search).toBe('?tour=skills&step=1')
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Find in skills' }), { key: 'ArrowRight' })
    expect(seen.search).toBe('?tour=skills&step=1')
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Find in skills' }), { key: 'Enter' })
    expect(seen.search).toBe('?tour=skills&step=1')
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(seen.search).toBe('?tour=skills&step=0')
  })

  it('Escape ends the tour, from anywhere', () => {
    mount(['/skills?tour=skills&step=0'])
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Find in skills' }), { key: 'Escape' })
    expect(seen.search).toBe('')
  })
})

describe('a missing subject', () => {
  it('offers to put the examples back when they were removed', async () => {
    // Step 1 points at the skills list, which this page does not render.
    mount(['/skills?tour=skills&step=1'])
    const button = await screen.findByRole('button', { name: 'Put the examples back' }, { timeout: 4000 })
    fireEvent.click(button)
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/examples/restore', expect.objectContaining({ method: 'POST' }))
    })
  })

  it('says so, without the offer, when nothing was removed', async () => {
    fetchMock.mockImplementation(async () => ({
      ok: true, json: async () => ({ present: ['sk_e0000001'], removed: [], all: ['sk_e0000001'] }),
    }))
    mount(['/skills?tour=skills&step=1'])
    await screen.findByText('item not on screen', {}, { timeout: 4000 })
    expect(screen.queryByRole('button', { name: 'Put the examples back' })).toBeNull()
  })
})
