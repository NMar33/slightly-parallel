import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { OverviewAnalytics } from './OverviewAnalytics'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('OverviewAnalytics', () => {
  it('says a refused read, instead of loading for ever', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, text: async () => '{"detail":"project not found: zz"}' })))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter><OverviewAnalytics projectCode="zz" /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByText('Could not load the task analytics')).toBeInTheDocument()
    expect(screen.getByText('project not found: zz')).toBeInTheDocument()
  })
})
