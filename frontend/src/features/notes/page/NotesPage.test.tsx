import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { HIDE_KEY, BY_KEY } from '../render/state'
import { hashOf } from '../render/model'
import type { NoteComment } from '../render/env'
import type { Feed, WireNote } from './data'
import { NotesPage } from './NotesPage'
import { TaskNotesSection } from './TaskNotesSection'

/** Invented notes of an invented project, as the server's feed sends them. */
const PLAN: WireNote = {
  id: 'nt_0a1b2c3d', project: 'harbor-app', kind: 'actions', title: 'Release steps', task: 'tk_11112222', entrypoint: '',
  chat: 'cc-aaaa0001', agent_id: 'cc-aaaa0001', created: '2026-11-16T09:00:00', updated: '2026-11-16T10:00:00', versions: 2,
  archived_at: '', replaces: [], replaced_by: '', words: 40,
  body: '# Release steps\n\nWhat is left before the release of tk_11112222.\n\n## By hand\n\n- [ ] Rotate the signing key\n- [ ] Upload the build\n\n## Pick one\n\n```choice Which icon?\n1. The wave\n2. The moon\n```\n',
  images: [],
}
const REVIEW: WireNote = {
  ...PLAN, id: 'nt_4e5f6a7b', kind: 'review', title: 'Home page review', task: '', versions: 1, updated: '2026-11-15T10:00:00',
  body: '# Home page review\n\nTwo layouts.\n\n```gallery\n![The wide layout](ni_00112233aa)\n```\n',
  images: [{ id: 'ni_00112233aa', caption: 'The wide layout', width: 1440, height: 900, src: '/api/notes/images/ni_00112233aa/file' }],
}
const FEED: Feed = {
  notes: [PLAN, REVIEW], marks: { ticks: {}, answers: {}, copied: {} },
  entities: { tk_11112222: { title: 'Ship the harbor app', status: 'doing', project: 'harbor-app' } }, projects: ['harbor-app'],
}

let posts: Array<{ url: string; body: Record<string, unknown> }> = []
function serve(feed: Feed, options: { failFirstComment?: boolean } = {}) {
  posts = []
  const comments = [...(feed.comments ?? [])]
  let failComment = options.failFirstComment
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      posts.push({ url, body })
      if (url.endsWith('/comments')) {
        if (failComment) {
          failComment = false
          return new Response(JSON.stringify({ detail: 'Connection interrupted' }), { status: 503 })
        }
        const comment: NoteComment = {
          id: `nc_${comments.length}`, note_id: PLAN.id, item: body.item, text: body.text,
          section: body.section ?? '', label: '', version: PLAN.versions, at: '2026-11-16T10:05:00',
        }
        comments.push(comment)
        return json({ comment })
      }
      return json({ ok: true })
    }
    if (url.startsWith('/api/notes/feed')) {
      const task = new URL(url, 'http://x').searchParams.get('task')
      const notes = task ? feed.notes.filter((n) => n.task === task || n.body.includes(task)) : feed.notes
      return json({ ...feed, notes, comments: comments.filter((c) => notes.some((n) => n.id === c.note_id)) })
    }
    return new Response('{}', { status: 404 })
  }))
}

function wrap(ui: ReactNode, url = '/notes') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter></QueryClientProvider>
}

const media = window.matchMedia
beforeEach(() => {
  window.matchMedia = ((query: string) => ({
    matches: /min-width/.test(query), media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as typeof window.matchMedia
  for (const k of [HIDE_KEY, BY_KEY]) localStorage.removeItem(k)
  serve(FEED)
})
afterEach(() => { window.matchMedia = media; vi.unstubAllGlobals() })

describe('the Notes page on the server\'s notes', () => {
  it('reads the notes whole, with live chips, and flips reading and tiles with one switch that stays in place', async () => {
    render(wrap(<NotesPage />))
    const feed = await screen.findByTestId('note-feed')
    expect(within(feed).getAllByText('Release steps').length).toBeGreaterThan(0)
    expect(document.querySelector('[data-chip="tk_11112222"]')?.textContent).toContain('Ship the harbor app')
    const sw = screen.getByTestId('view-switch')
    const toolbar = screen.getByTestId('toolbar')
    expect(toolbar.firstElementChild).toBe(sw)
    expect(within(sw).getByRole('button', { name: /Reading/ }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.queryByText('Back to reading')).toBeNull()
    expect(document.querySelector('[data-testid="zoom-out"]')).toBeNull()
    fireEvent.click(within(sw).getByRole('button', { name: /Tiles/ }))
    await waitFor(() => expect(document.querySelectorAll('[data-testid="note-tile"]')).toHaveLength(2))
    const sw2 = screen.getByTestId('view-switch')
    expect(screen.getByTestId('toolbar').firstElementChild).toBe(sw2)
    expect(within(sw2).getByRole('button', { name: /Tiles/ }).getAttribute('aria-pressed')).toBe('true')
    // The note that waits on an answer stands on the first shelf.
    expect(screen.getByRole('region', { name: 'answer' })).toBeTruthy()
    fireEvent.click(within(sw2).getByRole('button', { name: /Reading/ }))
    await screen.findByTestId('note-feed')
  })

  it('sends a tick and an answer to the server, keyed by the item text', async () => {
    render(wrap(<NotesPage />))
    const box = await screen.findByRole('checkbox', { name: 'Rotate the signing key' })
    fireEvent.click(box)
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toEqual({ url: '/api/notes/nt_0a1b2c3d/marks', body: { item: `nt_0a1b2c3d:k:${hashOf('Rotate the signing key')}`, kind: 'tick', value: true } })
    expect((box as HTMLInputElement).checked).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: /The moon/ }))
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1]!.body).toMatchObject({ kind: 'answer', value: 1 })
  })

  it('keeps an item comment draft after a failed write and scopes replies to their section or note', async () => {
    const note = { ...PLAN, body: PLAN.body + '\n## Later\n\n- [ ] Rotate the signing key\n' }
    serve({ ...FEED, notes: [note] }, { failFirstComment: true })
    render(wrap(<NotesPage />, `/notes?note=${note.id}`))
    const section = await screen.findByRole('region', { name: 'By hand' })
    const item = within(section).getByRole('button', { name: 'Comment on: Rotate the signing key' })
    fireEvent.click(item)
    const editor = within(section).getByRole('textbox', { name: 'Comment' })
    expect(editor).toHaveFocus()
    fireEvent.change(editor, { target: { value: 'Before the release\n<a>waiting</a>' } })
    const send = within(section).getByRole('button', { name: 'Send comment' })
    fireEvent.click(send)
    expect(await within(section).findByRole('alert')).toHaveTextContent('Connection interrupted')
    expect(editor).toHaveValue('Before the release\n<a>waiting</a>')
    fireEvent.click(send)
    const saved = await within(section).findByText(/<a>waiting<\/a>/)
    expect(saved.querySelector('a')).toBeNull()
    expect(posts[1]).toEqual(posts[0])
    expect(posts[1].body).toMatchObject({
      item: `${note.id}:k:${hashOf('Rotate the signing key')}`, section: 'By hand',
    })
    await waitFor(() => expect(item).toHaveFocus())
    const later = screen.getByRole('region', { name: 'Later' })
    fireEvent.click(within(later).getByRole('button', { name: 'Comment on: Rotate the signing key' }))
    expect(within(later).queryByText(/waiting/)).toBeNull()
    fireEvent.click(within(later).getByRole('button', { name: 'Cancel' }))
    fireEvent.click(item)

    fireEvent.click(screen.getByRole('button', { name: 'Comment on the note' }))
    const field = screen.getByRole('textbox', { name: 'Comment' })
    fireEvent.change(field, { target: { value: 'Whole note feedback' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send comment' }))
    expect(await screen.findByText('Whole note feedback')).toBeTruthy()
    expect(posts[2].body).toMatchObject({ item: null, text: 'Whole note feedback' })
  })

  it('draws a note\'s pictures from the server by id', async () => {
    render(wrap(<NotesPage />, '/notes?note=nt_4e5f6a7b'))
    await waitFor(() => expect(document.querySelector('img[src="/api/notes/images/ni_00112233aa/file"]')).toBeTruthy())
  })

  it('opens a gallery picture large, steps through the series with the keys and the buttons, shows it at its own size, and closes', async () => {
    const two: WireNote = {
      ...REVIEW, id: 'nt_5a5a5a5a', title: 'Two sheets',
      body: '# Two sheets\n\n```gallery\n![Sheet one](ni_aaaaaaaaaa)\n![Sheet two](ni_bbbbbbbbbb)\n```\n',
      images: [
        { id: 'ni_aaaaaaaaaa', caption: 'Sheet one', width: 3120, height: 3000, src: '/api/notes/images/ni_aaaaaaaaaa/file' },
        { id: 'ni_bbbbbbbbbb', caption: 'Sheet two', width: 3120, height: 3000, src: '/api/notes/images/ni_bbbbbbbbbb/file' },
      ],
    }
    serve({ ...FEED, notes: [two] })
    render(wrap(<NotesPage />, '/notes?note=nt_5a5a5a5a'))
    const open = (await screen.findAllByRole('button', { name: 'Open the picture large' }))[0]
    fireEvent.click(open)
    const dialog = await screen.findByRole('dialog', { name: 'Sheet one' })
    expect(within(dialog).getByText('1 / 2')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(await screen.findByRole('dialog', { name: 'Sheet two' })).toBeTruthy()
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Previous picture' }))
    const back = await screen.findByRole('dialog', { name: 'Sheet one' })
    const img = within(back).getByRole('img', { name: 'Sheet one' })
    expect(img.className).toContain('cursor-zoom-in')
    fireEvent.click(img)
    expect(within(back).getByRole('img', { name: 'Sheet one' }).className).toContain('max-w-none')
    expect(screen.getByRole('dialog')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('says how notes get written when there are none', async () => {
    serve({ ...FEED, notes: [] })
    render(wrap(<NotesPage />))
    expect(await screen.findByText('No notes yet.')).toBeTruthy()
    expect(screen.getByText(/It calls the Slightly Parallel tool note_write/)).toBeTruthy()
  })

  it('keeps the hash the server keys marks by', () => {
    // The same vectors as the backend's test_notes.py.
    expect(hashOf('hello')).toBe('4f9f2cab')
    expect(hashOf('Привет 👋')).toBe('eb9ef6cd')
  })
})

describe('a task\'s notes in its window', () => {
  it('lists the task\'s notes with what waits, and works in place', async () => {
    render(wrap(<TaskNotesSection taskId="tk_11112222" />))
    const section = await screen.findByTestId('task-notes')
    expect(within(section).getByText('Release steps')).toBeTruthy()
    expect(within(section).getByText('this task\'s note')).toBeTruthy()
    expect(within(section).getByRole('link', { name: 'Open on the Notes page' }).getAttribute('href')).toBe('/notes?note=nt_0a1b2c3d')
    await act(async () => { fireEvent.click(within(section).getByRole('button', { name: /The wave/ })) })
    await waitFor(() => expect(posts.at(-1)?.body).toMatchObject({ kind: 'answer', value: 0 }))
  })

  it('draws nothing for a task with no notes', async () => {
    const { container } = render(wrap(<TaskNotesSection taskId="tk_99998888" />))
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(container.querySelector('[data-testid="task-notes"]')).toBeNull()
  })
})
