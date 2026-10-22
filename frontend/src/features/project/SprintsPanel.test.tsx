import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { SprintsPanel } from './SprintsPanel'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

function answering() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const body = url.startsWith('/api/sprints/board') ? { sprints: [] } : url.startsWith('/api/tasks') ? { tasks: [] } : {}
    return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => JSON.stringify(body) }
  }))
}

describe('SprintsPanel', () => {
  it("shows each project's own view when the panel moves to another project", async () => {
    answering()
    localStorage.setItem('sp-sprints-view:a', 'blocks')
    localStorage.setItem('sp-sprints-view:b', 'runway')
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const tree = (code: string) => (
      <QueryClientProvider client={qc}><MemoryRouter><SprintsPanel projectCode={code} /></MemoryRouter></QueryClientProvider>
    )
    const { rerender } = render(tree('a'))
    expect(await screen.findByRole('radio', { name: 'blocks' })).toHaveAttribute('aria-checked', 'true')
    rerender(tree('b'))
    expect(await screen.findByRole('radio', { name: 'runway' })).toHaveAttribute('aria-checked', 'true')
  })
})
