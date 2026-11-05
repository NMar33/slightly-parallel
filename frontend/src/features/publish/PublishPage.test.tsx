import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PublishPage } from './PublishPage'
import type { Card, Doc, PublishBoard } from './data'

const base = { project: 'alpha', agent_id: 'cc-1', session_id: 'sess-1234567', source_turn: 4, tasks: [], cores: [], commits: [], images: [], archived_at: '' }
const CARDS: Card[] = [
  { ...base, id: 'pu_new', at: '2026-11-03T10:00:00', message: 'the board drops a card on a hidden column', text: 'The board keeps a card dropped on a hidden column.',
    versions: [{ n: 1, at: '2026-11-03T11:00:00', text: 'The board keeps a card dropped on a hidden column.', note: '' }],
    commits: [{ sha: 'abc1234def', subject: 'Board: hold the drop', at: '2026-11-03T09:00:00' }],
    placements: [{ doc_id: 'pd_rel', doc_name: 'Release note', version_n: 1, item_id: 'pi_1', text: 'The board keeps a card dropped on a hidden column.', changed: false }] },
  { ...base, id: 'pu_old', images: [
    { url: '/api/publishing/attachments/pa_1/file', label: 'board', from: 'attached', id: 'pa_1', by: 'cc-9' },
    { url: '/evidence/x.png', label: 'evidence shot', from: 'evidence' },
  ], links: [{ url: 'https://github.com/nmar33/x/pull/4', label: 'PR 4', id: 'pl_1', by: 'cc-9' }],
  files: Array.from({ length: 8 }, (_, i) => ({ path: `backend/f${i}.py`, add: 10 + i, del: 1 })), at: '2026-11-02T10:00:00', message: 'Capture reads stdin.', text: 'Capture reads stdin.', versions: [], placements: [] },
]
const DOCS: Doc[] = [
  { id: 'pd_post', project: 'alpha', name: 'Launch post', created_at: '2026-11-02T12:00:00', archived_at: '', current: 1,
    versions: [{ n: 1, at: '2026-11-02T12:00:00', actor: 'operator', note: '', items: [] }] },
  { id: 'pd_rel', project: 'alpha', name: 'Release note', created_at: '2026-11-01T12:00:00', archived_at: '', current: 1,
    versions: [{ n: 1, at: '2026-11-01T12:00:00', actor: 'operator', note: '', items: [
      { id: 'pi_1', card_id: 'pu_new', text: 'The board keeps a card dropped on a hidden column.', position: 1, changed: false },
    ] }] },
]
const BOARD: PublishBoard = { project: 'alpha', cards: CARDS, docs: DOCS }

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

type Post = { path: string; body: Record<string, unknown> }
function serve(posts: Post[]) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url)
    const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } })
    if (init?.method === 'POST') {
      posts.push({ path, body: JSON.parse(String(init.body)) as Record<string, unknown> })
      return json({ item: { id: 'pi_9' }, existing: false, card: CARDS[0], doc: { ...DOCS[0], id: 'pd_new' } })
    }
    if (path.startsWith('/api/snapshot')) return json({ projects: [{ code: 'alpha' }] })
    if (path.startsWith('/api/publishing/cards/')) return json({ ...CARDS[0], history: [] })
    if (path.startsWith('/api/publishing?')) return json(BOARD)
    return new Response('{}', { status: 404 })
  }))
}

beforeEach(() => { window.location.hash = '#project=alpha' })
afterEach(() => { vi.unstubAllGlobals(); window.location.hash = ''; localStorage.clear() })

describe('PublishPage', () => {
  it('shows the cards with their original and the documents as tabs in creation order', async () => {
    serve([])
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getAllByText('The board keeps a card dropped on a hidden column.')).toHaveLength(2))   // the card, and its item in the open document
    expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument()
    // the original under the edited text
    expect(screen.getByText('the board drops a card on a hidden column')).toBeInTheDocument()
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual([expect.stringContaining('Release note'), expect.stringContaining('Launch post')])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    // The commits fold under one line: open it to see the sha.
    expect(screen.queryByText('abc1234')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /1 commit/ }))
    expect(screen.getByText('abc1234')).toBeInTheDocument()
    const fetched = (fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls.map((c) => String(c[0]))
    expect(fetched).toContain('/api/publishing?project=alpha')
  })

  it('places the cursor card into the Nth document with a digit, after j moves the cursor', async () => {
    const posts: Post[] = []
    serve(posts)
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument())
    fireEvent.keyDown(window, { key: '2' })
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.path).toBe('/api/publishing/docs/pd_post/items')
    expect(posts[0]!.body).toMatchObject({ card_id: 'pu_new', actor: 'operator' })
    fireEvent.keyDown(window, { key: 'j' })
    fireEvent.keyDown(window, { key: '1' })
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1]!.path).toBe('/api/publishing/docs/pd_rel/items')
    expect(posts[1]!.body).toMatchObject({ card_id: 'pu_old' })
  })

  it('edits the card text with e and saves it with Enter', async () => {
    const posts: Post[] = []
    serve(posts)
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'j' })
    fireEvent.keyDown(window, { key: 'e' })
    const field = await screen.findByRole('textbox', { name: 'Card text' })
    fireEvent.change(field, { target: { value: 'Capture reads stdin, on every tool.' } })
    fireEvent.keyDown(field, { key: 'Enter' })
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.path).toBe('/api/publishing/cards/pu_old/text')
    expect(posts[0]!.body).toMatchObject({ text: 'Capture reads stdin, on every tool.', actor: 'operator' })
  })

  it('shows the live diff and the counter while editing, and fills the box with the original', async () => {
    const posts: Post[] = []
    serve(posts)
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'e' })
    const field = await screen.findByRole('textbox', { name: 'Card text' })
    expect(screen.getByText('10 words · 50 characters')).toBeInTheDocument()
    expect([...document.querySelectorAll('del')].map((d) => d.textContent).join('')).toContain('drops')
    expect([...document.querySelectorAll('ins')].map((d) => d.textContent).join('')).toContain('keeps')
    fireEvent.click(screen.getByRole('button', { name: 'use the original' }))
    expect(field).toHaveValue('the board drops a card on a hidden column')
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toMatchObject({ path: '/api/publishing/cards/pu_new/text', body: { text: 'the board drops a card on a hidden column' } })
  })

  it('shows where each image came from, the links by host, at most six files, and removes an attached image', async () => {
    const posts: Post[] = []
    serve(posts)
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument())
    expect(screen.getByText('attached · by cc-9')).toBeInTheDocument()
    expect(screen.getByText('evidence')).toBeInTheDocument()
    expect(screen.getByText('github.com')).toBeInTheDocument()
    // The files and commits sit under one line until it is opened.
    expect(screen.queryByText('f0.py')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /8 files/ }))
    expect(screen.getAllByText(/\+1[0-7]/)).toHaveLength(8)
    const remove = screen.getAllByRole('button', { name: 'Remove the image' })
    expect(remove).toHaveLength(1)
    fireEvent.click(remove[0]!)
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.path).toBe('/api/publishing/attachments/pa_1/remove')
  })

  it('attaches an image file dropped on a card', async () => {
    const posts: Post[] = []
    serve(posts)
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument())
    const card = document.querySelector('[data-card="pu_old"]')!
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'board-shot.png', { type: 'image/png' })
    fireEvent.drop(card, { dataTransfer: { files: [file], types: ['Files'], getData: () => '' } })
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.path).toBe('/api/publishing/cards/pu_old/attach')
    expect(posts[0]!.body).toMatchObject({ images: [{ title: 'board-shot', ext: 'png', data_base64: 'iVBORw==' }] })
  })

  it('narrows the cards to a strip with [ and keeps placing with digits', async () => {
    const posts: Post[] = []
    serve(posts)
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'f' })
    expect(screen.queryByText('Capture reads stdin.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show the cards ([)' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'j' })
    fireEvent.keyDown(window, { key: '1' })
    await waitFor(() => expect(posts.some((p) => p.path === '/api/publishing/docs/pd_rel/items')).toBe(true))
    expect(posts.find((p) => p.path === '/api/publishing/docs/pd_rel/items')!.body).toMatchObject({ card_id: 'pu_old' })
    fireEvent.keyDown(window, { key: 'f' })
    expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument()
  })

  it('writes a card by hand from the c key', async () => {
    const posts: Post[] = []
    serve(posts)
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'c' })
    const box = await screen.findByPlaceholderText(/What shipped, worth telling/)
    fireEvent.change(box, { target: { value: 'Sprints: a board per week.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Make the card' }))
    await waitFor(() => expect(posts.some((p) => p.path === '/api/publishing/cards')).toBe(true))
    expect(posts.find((p) => p.path === '/api/publishing/cards')!.body).toMatchObject({ project: 'alpha', text: 'Sprints: a board per week.' })
  })

  it('makes a document from the n key', async () => {
    const posts: Post[] = []
    serve(posts)
    render(wrap(<PublishPage />))
    await waitFor(() => expect(screen.getByText('Capture reads stdin.')).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'n' })
    const name = await screen.findByPlaceholderText(/Name on the tab/)
    fireEvent.change(name, { target: { value: 'Video script' } })
    fireEvent.click(screen.getByRole('button', { name: 'Make the document' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toMatchObject({ path: '/api/publishing/docs', body: { project: 'alpha', name: 'Video script' } })
  })
})
