import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { FilesTab } from './FilesTab'

// The tab's own view; the files controls (features/files) read their keys apart.
const VIEW = 'sp-files-view'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('FilesTab', () => {
  it('draws when the site store refuses to give its view', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key: string) => { if (key === VIEW) throw new DOMException('blocked', 'SecurityError'); return null })
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter><FilesTab projectCode="p" /></MemoryRouter></QueryClientProvider>)
    expect(document.body.textContent).not.toBe('')
    expect(screen.queryByText(/blocked/)).not.toBeInTheDocument()
  })
})

const FLEET = {
  files: [
    { path: 'README.md', key: 'alpha::README.md', project: 'alpha', total: 2, created: 0, modified: 2, deleted: 0, lines_add: 3, lines_del: 1 },
    { path: 'README.md', key: 'beta::README.md', project: 'beta', total: 1, created: 0, modified: 1, deleted: 0, lines_add: 7, lines_del: 0 },
  ],
  dates: ['2608-18'],
  matrix: { 'alpha::README.md||2608-18': { count: 2, lines_add: 3, lines_del: 1 }, 'beta::README.md||2608-18': { count: 1, lines_add: 7, lines_del: 0 } },
  entries: [
    { id: 'fl_a', project: 'alpha', date: '2608-18', time: '10:01', agent_id: 'cc-a', l1: 'readme', scan_id: 'sn_a', session_id: '', paths_n: 1 },
    { id: 'fl_b', project: 'beta', date: '2608-18', time: '10:02', agent_id: 'cc-b', l1: 'readme too', scan_id: 'sn_b', session_id: '', paths_n: 1 },
  ],
  cells: { 'alpha::README.md||fl_a': { count: 2, lines_add: 3, lines_del: 1, why: 'alpha wrote it' }, 'beta::README.md||fl_b': { count: 1, lines_add: 7, lines_del: 0, why: 'beta wrote it' } },
  max: 2,
}

describe('FilesTab over every project', () => {
  it('keeps the same path apart per project, offers a chip per project, and narrows to one', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      expect(url).not.toContain('project=')
      return new Response(JSON.stringify(FLEET), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter><FilesTab /></MemoryRouter></QueryClientProvider>)
    const { findByRole, findAllByText, getByRole, queryByRole } = await import('@testing-library/react').then((m) => ({ ...m, ...screen }))
    await findByRole('radiogroup', { name: 'Project' })
    expect((await findAllByText('README.md')).length).toBe(2)   // one per project, not merged
    expect(getByRole('radio', { name: 'alpha' })).toBeInTheDocument()
    getByRole('radio', { name: 'beta' }).click()
    await new Promise((r) => setTimeout(r, 0))
    expect((await findAllByText('README.md')).length).toBe(1)
    expect(queryByRole('radio', { name: 'nothing' })).toBeNull()
  })
})
