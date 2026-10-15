import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DocVersions, type Version } from './DocVersions'

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const versions: Version[] = [
  { id: 'dv_3', created_at: '2026-10-10T12:00:00', agent_id: 'operator', body: '# Launch\n\nThird, pasted.', note: 'pasted from a chat' },
  { id: 'dv_2', created_at: '2026-10-10T11:00:00', agent_id: 'cc-writer01', body: '# Launch\n\nSecond, tighter.', note: 'tighter' },
  { id: 'dv_1', created_at: '2026-10-10T10:00:00', agent_id: 'cc-writer01', body: '# Launch\n\nFirst draft.', note: '' },
]

function mount(list: Version[], onChanged = () => {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DocVersions docId="dc_doc1" versions={list} mentions={[]} onSession={() => {}} onChanged={onChanged} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('a document\'s versions', () => {
  const posted: Array<{ url: string; body: unknown }> = []
  beforeEach(() => {
    localStorage.clear()
    posted.length = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/versions') && init?.method === 'POST') {
        posted.push({ url, body: JSON.parse(String(init.body)) })
        return json(201, { version: { id: 'dv_4' }, n: 4 })
      }
      if (url.includes('/api/snapshot')) return json(200, { agents: [{ agent_id: 'cc-writer01', agent_name: 'Writer' }] })
      return json(404, { detail: `unexpected ${url}` })
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('lists the versions newest first, numbered, with who wrote each and its note', () => {
    mount(versions)
    const opens = screen.getAllByRole('button', { name: /^Open version/ })
    expect(opens.map((r) => r.getAttribute('aria-label'))).toEqual(['Open version 3', 'Open version 2', 'Open version 1'])
    const rows = opens.map((b) => b.closest('li') as HTMLElement)
    expect(within(rows[0]!).getByText('you')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('pasted from a chat')).toBeInTheDocument()
    // An agent's version links to the agent's page.
    expect(within(rows[1]!).getByRole('link')).toHaveAttribute('href', '/agent/cc-writer01')
    // No note: the start of the text stands in.
    expect(within(rows[2]!).getByText(/First draft\./)).toBeInTheDocument()
  })

  it('opens a version to read it, and compares it with the one before', async () => {
    mount(versions)
    fireEvent.click(screen.getByRole('button', { name: 'Open version 2' }))
    const win = await screen.findByRole('dialog', { name: 'Version 2' })
    expect(within(win).getByRole('heading', { name: 'Launch' })).toBeInTheDocument()
    expect(within(win).getByText('Second, tighter.')).toBeInTheDocument()
    expect(within(win).getByRole('button', { name: /copy/i })).toBeInTheDocument()

    fireEvent.click(within(win).getByRole('radio', { name: 'changes from v1' }))
    expect(within(win).getByText('First draft.')).toHaveClass('line-through')
    expect(within(win).getByText('Second, tighter.')).toBeInTheDocument()
  })

  it('has nothing to compare for the first version', async () => {
    mount(versions)
    fireEvent.click(screen.getByRole('button', { name: 'Open version 1' }))
    const win = await screen.findByRole('dialog', { name: 'Version 1' })
    expect(within(win).queryByRole('radio', { name: /changes from/ })).toBeNull()
  })

  it('says how a version arrives when there is none', () => {
    mount([])
    expect(screen.getByText(/the agent posts its text back here with doc_version/)).toBeInTheDocument()
  })

  it('takes a version pasted by hand, with its note', async () => {
    const onChanged = vi.fn()
    mount(versions, onChanged)
    fireEvent.click(screen.getByRole('button', { name: '+ paste a version' }))
    const save = screen.getByRole('button', { name: 'save version' })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Text'), { target: { value: '# Launch\n\nFourth.' } })
    fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'from a chat without tools' } })
    fireEvent.click(save)
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]).toEqual({
      url: '/api/docs/dc_doc1/versions',
      body: { body: '# Launch\n\nFourth.', note: 'from a chat without tools', agent_id: 'operator' },
    })
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(screen.queryByLabelText('Text')).toBeNull()
    expect(localStorage.getItem('sp-doc-version-draft:dc_doc1')).toBeNull()
  })
})
