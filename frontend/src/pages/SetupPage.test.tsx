import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import SetupPage from './SetupPage'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const info = {
  app_root: '/m', contract_path: '/m/SLIGHTLY-PARALLEL.md', contract_exists: true, data_root: '/data', example: { project: 'shopfront', enabled: false, present: false, building: false, error: '' }, api_url: 'http://x',
  integrations: [{ project: 'shop', path: '/work/shop', created_date: '2610-01', status: 'stale', hooks: true, git: true }],
  data_projects: [], codex: { state: 'absent', config: '~/.codex/config.toml' },
  adapters: { claude_verified: true, opencode_verified: false, codex_verified: false, cursor_verified: false },
}

describe('SetupPage', () => {
  it("Re-integrate sends the row's project and folder, not the empty form", async () => {
    const posted: Array<Record<string, unknown>> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posted.push(JSON.parse(String(init.body)))
        const body = { dry_run: false, project_code: 'shop', project_dir: '/work/shop', results: [] }
        return { ok: true, status: 200, json: async () => body }
      }
      const body = url.startsWith('/api/setup/info') ? info : { projects: [], agents: [] }
      return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => JSON.stringify(body) }
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter><SetupPage /></MemoryRouter></QueryClientProvider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Re-integrate' }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]).toMatchObject({ project_code: 'shop', project_dir: '/work/shop', dry_run: false })
  })
})
