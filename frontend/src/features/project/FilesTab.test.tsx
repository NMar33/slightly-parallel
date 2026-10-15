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
