import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { NOTES, SEED } from '../mock'
import { NotesDesign } from '../NotesDesign'
import { resetMarks } from '../store'
import { PAGE, PAGE_DELAY } from './feed'

let where = ''
function Where() { where = useLocation().search; return null }
function wrap(ui: ReactNode, url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}>{ui}<Where /></MemoryRouter></QueryClientProvider>
}
const fed = () => [...document.querySelectorAll('[data-feed-note]')].map((e) => e.getAttribute('data-feed-note'))
const press = (key: string, code = '') => act(() => { fireEvent.keyDown(window, { key, code }) })

beforeEach(() => { resetMarks(SEED); vi.useFakeTimers({ shouldAdvanceTime: true }) })
afterEach(() => { vi.useRealTimers() })

describe('round 2: the endless feed', () => {
  it('shows a page of whole notes and loads the next page after the pause, until every note is there', async () => {
    render(wrap(<NotesDesign />, '/notes?v=f'))
    expect(fed()).toHaveLength(PAGE)
    for (let shown = PAGE; shown < NOTES.length; shown += PAGE) {
      fireEvent.click(screen.getByRole('button', { name: /Show more/ }))
      expect(screen.getByLabelText('Loading the next notes')).toBeTruthy()
      await act(async () => { vi.advanceTimersByTime(PAGE_DELAY + 10) })
      expect(fed()).toHaveLength(Math.min(NOTES.length, shown + PAGE))
    }
    expect(screen.getByText(`That is every note: ${NOTES.length}.`)).toBeTruthy()
  })

  it('a click in the list loads the feed through that note at once', () => {
    render(wrap(<NotesDesign />, '/notes?v=f'))
    const nav = screen.getByRole('navigation', { name: 'Notes' })
    const last = nav.querySelectorAll('[data-row]')
    const id = last[last.length - 1]!.getAttribute('data-row')!
    fireEvent.click(last[last.length - 1]!)
    expect(fed()).toContain(id)
    expect(fed()).toHaveLength(NOTES.length)
  })

  it('says which newer note replaces an older one, and which older one a note replaces', async () => {
    render(wrap(<NotesDesign />, '/notes?v=f'))
    for (let i = 0; i < 4; i++) {
      const more = screen.queryByRole('button', { name: /Show more/ })
      if (more) { fireEvent.click(more); await act(async () => { vi.advanceTimersByTime(PAGE_DELAY + 10) }) }
    }
    const old = document.querySelector('[data-feed-note="nt_70c2a4e8"]') as HTMLElement
    expect(within(old).getByText(/Replaced by a newer note/)).toBeTruthy()
    const newer = document.querySelector('[data-feed-note="nt_b3e1a0c4"]') as HTMLElement
    expect(within(newer).getByText(/Replaces an older note/)).toBeTruthy()
  })
})

describe('round 2: hiding the columns', () => {
  it('l hides the list, f hides the feed and leaves tiles, and the address keeps it', () => {
    render(wrap(<NotesDesign />, '/notes?v=f'))
    expect(document.querySelector('[data-col="list"]')).toBeTruthy()
    press('l', 'KeyL')
    expect(document.querySelector('[data-col="list"]')).toBeNull()
    expect(where).toContain('hide=list')
    press('f', 'KeyF')
    expect(document.querySelector('[data-col="feed"]')).toBeNull()
    expect(document.querySelectorAll('[data-testid="note-tile"]')).toHaveLength(NOTES.length)
    expect(where).toContain('hide=feed%2Clist')
    press('l', 'KeyL')
    expect(document.querySelector('[data-col="list"]')).toBeTruthy()
  })

  it('takes the keys by their place: the Russian layout\'s д hides the list', () => {
    render(wrap(<NotesDesign />, '/notes?v=f'))
    press('д', 'KeyL')
    expect(document.querySelector('[data-col="list"]')).toBeNull()
  })

  it('leaves the keys alone while typing in the find box', () => {
    render(wrap(<NotesDesign />, '/notes?v=f'))
    const box = screen.getByLabelText('Find in notes')
    act(() => { fireEvent.keyDown(box, { key: 'l', code: 'KeyL' }) })
    expect(document.querySelector('[data-col="list"]')).toBeTruthy()
  })

  it('a tile opens its note back in the reading layout, loaded and in the feed', () => {
    render(wrap(<NotesDesign />, '/notes?v=f&hide=feed'))
    const tiles = screen.getAllByTestId('note-tile')
    const lastId = tiles[tiles.length - 1]!.getAttribute('data-note')!
    fireEvent.click(within(tiles[tiles.length - 1]!).getAllByRole('button')[0]!)
    expect(screen.queryAllByTestId('note-tile')).toHaveLength(0)
    expect(fed()).toContain(lastId)
  })

  it('G has a hide button on each column and a strip that brings a hidden one back', () => {
    render(wrap(<NotesDesign />, '/notes?v=g'))
    fireEvent.click(screen.getAllByRole('button', { name: 'Hide the list' })[0]!)
    expect(document.querySelector('[data-col="list"]')).toBeNull()
    fireEvent.click(document.querySelector('[data-strip="list"]')!)
    expect(document.querySelector('[data-col="list"]')).toBeTruthy()
  })

  it('I switches by one control with four modes', () => {
    render(wrap(<NotesDesign />, '/notes?v=i'))
    fireEvent.click(screen.getByRole('radio', { name: /^Tiles/ }))
    expect(document.querySelector('[data-columns="tiles"]')).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: /^Reading/ }))
    expect(document.querySelector('[data-columns="read"]')).toBeTruthy()
  })
})

describe('round 2: the tiles', () => {
  it('F shelves the tiles by project, G by what you do', () => {
    const { unmount } = render(wrap(<NotesDesign />, '/notes?v=f&hide=feed'))
    expect(screen.getByRole('region', { name: 'merkhet' })).toBeTruthy()
    unmount()
    render(wrap(<NotesDesign />, '/notes?v=g&hide=feed'))
    const answer = screen.getByRole('region', { name: 'answer' })
    expect(within(answer).getAllByTestId('note-tile').map((e) => e.getAttribute('data-note'))).toContain('nt_8c02d5e3')
    expect(within(screen.getByRole('region', { name: 'replaced' })).getAllByTestId('note-tile')[0]!.getAttribute('data-note')).toBe('nt_70c2a4e8')
  })
})

describe('round 2: the task window in the page', () => {
  it('G opens the feed with what waits on you, task by task, in the task window\'s form', () => {
    render(wrap(<NotesDesign />, '/notes?v=g'))
    const band = screen.getByTestId('waits-band')
    expect(within(band).getAllByTestId('task-notes').length).toBeGreaterThan(1)
    expect(within(band).getAllByText('your answer is needed').length).toBe(2)
  })

  it('H puts a task band over the first note of each task, and a task tile opens the task\'s notes in place; Escape closes them', () => {
    const { unmount } = render(wrap(<NotesDesign />, '/notes?v=h'))
    expect(screen.getAllByTestId('task-band').length).toBeGreaterThan(0)
    unmount()
    render(wrap(<NotesDesign />, '/notes?v=h&hide=feed'))
    fireEvent.click(within(screen.getAllByTestId('task-tile')[0]!).getByRole('button', { name: 'Open its notes here' }))
    const card = screen.getByTestId('task-card')
    expect(within(card).getByTestId('task-notes')).toBeTruthy()
    press('Escape')
    expect(screen.queryByTestId('task-card')).toBeNull()
  })

  it('I filters by task and puts the task window\'s notes over the feed', () => {
    render(wrap(<NotesDesign />, '/notes?v=i'))
    fireEvent.click(within(screen.getByRole('group', { name: 'By task' })).getByRole('button', { name: /tk_51b87348/ }))
    expect(screen.getByTestId('task-opening')).toBeTruthy()
    expect(where).toContain('task=tk_51b87348')
    expect(fed().every((id) => { const n = NOTES.find((x) => x.id === id)!; return n.task === 'tk_51b87348' || n.refs.includes('tk_51b87348') })).toBe(true)
  })

  it('F\'s rail names the task of the note in view and its other notes', () => {
    render(wrap(<NotesDesign />, '/notes?v=f'))
    const rail = screen.getByRole('complementary', { name: 'Outline and links' })
    expect(within(rail).getByText('Its task')).toBeTruthy()
    expect(within(rail).getByText('this task\'s note')).toBeTruthy()
  })
})
