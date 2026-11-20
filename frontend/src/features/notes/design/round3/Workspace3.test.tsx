import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { NOTES, SEED } from '../mock'
import { NotesDesign } from '../NotesDesign'
import { resetMarks } from '../store'
import { BY_KEY, HIDE_KEY } from './state'
import { VIEW_KEY } from './Workspace3'

let where = ''
function Where() { where = useLocation().search; return null }
function wrap(ui: ReactNode, url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}>{ui}<Where /></MemoryRouter></QueryClientProvider>
}
const fed = () => [...document.querySelectorAll('[data-feed-note]')].map((e) => e.getAttribute('data-feed-note'))
const tiles = () => document.querySelectorAll('[data-testid="note-tile"]')
const press = (key: string, code = '') => act(() => { fireEvent.keyDown(window, { key, code }) })
const view = () => document.querySelector('[data-view]')?.getAttribute('data-view')

// A wide screen: the test setup's matchMedia matches nothing, which would be a phone.
const media = window.matchMedia
beforeEach(() => {
  window.matchMedia = ((query: string) => ({
    matches: /min-width/.test(query), media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as typeof window.matchMedia
  resetMarks(SEED)
  for (const k of [HIDE_KEY, BY_KEY, VIEW_KEY]) localStorage.removeItem(k)
  vi.useFakeTimers({ shouldAdvanceTime: true })
})
afterEach(() => { vi.useRealTimers(); window.matchMedia = media })

describe('round 3: the dividers fold the side columns', () => {
  it('a click on the line folds the list and the address and this browser keep it; the line brings it back', () => {
    render(wrap(<NotesDesign />, '/notes?v=j'))
    const line = document.querySelector('[data-divider="list"]') as HTMLElement
    expect(line.getAttribute('aria-expanded')).toBe('true')
    expect(line.getAttribute('aria-label')).toBe('Hide the list')
    fireEvent.click(line)
    expect(document.querySelector('[data-col="list"]')).toBeNull()
    expect(where).toContain('hide=list')
    expect(localStorage.getItem(HIDE_KEY)).toBe('list')
    const back = document.querySelector('[data-divider="list"]') as HTMLElement
    expect(back.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(back)
    expect(document.querySelector('[data-col="list"]')).toBeTruthy()
  })

  it('l folds the list and r the outline rail, by the key\'s place too', () => {
    render(wrap(<NotesDesign />, '/notes?v=k'))
    press('д', 'KeyL')
    expect(document.querySelector('[data-col="list"]')).toBeNull()
    press('r', 'KeyR')
    expect(document.querySelector('[data-col="rail"]')).toBeNull()
    expect(where).toContain('hide=list%2Crail')
  })

  it('a folded column stays folded on the next visit, unless the address says otherwise', () => {
    localStorage.setItem(HIDE_KEY, 'rail')
    const { unmount } = render(wrap(<NotesDesign />, '/notes?v=j'))
    expect(document.querySelector('[data-col="rail"]')).toBeNull()
    unmount()
    render(wrap(<NotesDesign />, '/notes?v=j&hide='))
    expect(document.querySelector('[data-col="rail"]')).toBeTruthy()
  })
})

describe('round 3: group by task', () => {
  it('the switch groups the feed under task bands and names each task once', () => {
    render(wrap(<NotesDesign />, '/notes?v=j'))
    expect(screen.queryAllByTestId('task-band')).toHaveLength(0)
    fireEvent.click(screen.getByRole('switch', { name: 'Group by task' }))
    expect(where).toContain('by=task')
    const bands = screen.getAllByTestId('task-band')
    expect(bands.length).toBeGreaterThan(0)
    // The first note of the first band: its head does not repeat the band's chip.
    const first = document.querySelector('[data-feed-note]') as HTMLElement
    const task = NOTES.find((n) => n.id === first.getAttribute('data-feed-note'))!.task
    expect(within(bands[0]!).getAllByText(task).length).toBe(1)
    expect(first.querySelector(`header [data-chip="${task}"]`)).toBeNull()
  })

  it('grouped, the tiles stand on one shelf per task without the task on each tile', () => {
    render(wrap(<NotesDesign />, '/notes?v=j&by=task&view=tiles'))
    const shelf = screen.getByRole('region', { name: 'tk_51b87348' })
    expect(within(shelf).getAllByTestId('note-tile').length).toBe(3)
    expect(within(shelf).queryByText('tk_51b87348', { selector: 'span.text-10' })).toBeNull()
  })
})

describe('round 3: reading and the tiles', () => {
  it('J: the switch shows the tiles shelved by what you do, rings the note left, and remembers the view', () => {
    render(wrap(<NotesDesign />, '/notes?v=j'))
    fireEvent.click(screen.getByRole('button', { name: 'The notes as tiles' }))
    expect(view()).toBe('tiles')
    expect(where).toContain('view=tiles')
    expect(localStorage.getItem(VIEW_KEY)).toBe('tiles')
    expect(tiles()).toHaveLength(NOTES.length)
    expect(screen.getByRole('region', { name: 'answer' })).toBeTruthy()
    expect(screen.getByText('You were reading this note')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Read the notes' }))
    expect(view()).toBe('read')
    expect(localStorage.getItem(VIEW_KEY)).toBe('read')
  })

  it('K: o zooms out, Escape zooms back in on the note left', () => {
    render(wrap(<NotesDesign />, '/notes?v=k'))
    const first = fed()[0]
    press('o', 'KeyO')
    expect(view()).toBe('tiles')
    expect(where).toContain(`note=${first}`)
    press('Escape')
    expect(view()).toBe('read')
    expect(fed()).toContain(first)
  })

  it('K: a tile zooms in on its note, loaded into the feed', () => {
    render(wrap(<NotesDesign />, '/notes?v=k&view=tiles'))
    const last = tiles()[tiles().length - 1]!
    const id = last.getAttribute('data-note')!
    fireEvent.click(within(last as HTMLElement).getAllByRole('button')[0]!)
    expect(view()).toBe('read')
    expect(fed()).toContain(id)
  })

  it('L: opens on the shelves; a tile drills into reading under a breadcrumb; Escape goes back with a way to continue', () => {
    render(wrap(<NotesDesign />, '/notes?v=l'))
    expect(view()).toBe('tiles')
    const tile = tiles()[2]! as HTMLElement
    const id = tile.getAttribute('data-note')!
    fireEvent.click(within(tile).getAllByRole('button')[0]!)
    expect(view()).toBe('read')
    expect(where).toContain('view=read')
    expect(screen.getByTestId('crumbs')).toBeTruthy()
    press('Escape')
    expect(view()).toBe('tiles')
    expect(screen.getByTestId('continue').textContent).toContain(NOTES.find((n) => n.id === id)!.title)
    fireEvent.click(screen.getByTestId('continue'))
    expect(view()).toBe('read')
    expect(fed()).toContain(id)
  })

  it('L: a link to a note opens straight in reading', () => {
    render(wrap(<NotesDesign />, '/notes?v=l&note=nt_2a6f0e91'))
    expect(view()).toBe('read')
    expect(fed()).toContain('nt_2a6f0e91')
  })

  it('the view keys stay away from the find box', () => {
    render(wrap(<NotesDesign />, '/notes?v=k'))
    act(() => { fireEvent.keyDown(screen.getByLabelText('Find in notes'), { key: 'o', code: 'KeyO' }) })
    expect(view()).toBe('read')
  })
})
