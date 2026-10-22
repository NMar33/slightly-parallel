import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PromptsCard } from './PromptsCard'
import { usePromptFiles } from '../prompts/parts'

const FILES = [
  { key: 'contract', label: 'Contract', about: '', path: '/x', lines: 12, modified: null, has_original: true, is_original: true, versions_n: 0 },
]

function Editor() {
  const q = usePromptFiles()
  return <div>{(q.data ?? []).map((f) => <span key={f.key}>editor:{f.key}</span>)}</div>
}

describe('prompt files list', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('the settings card and the editor share one cached shape', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ files: FILES }), { status: 200 }))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    const { rerender } = render(
      <QueryClientProvider client={client}><MemoryRouter><PromptsCard /></MemoryRouter></QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getAllByRole('link').length).toBeGreaterThan(0))
    // Settings → open editor: the editor reads the card's cached answer and must not crash.
    rerender(<QueryClientProvider client={client}><MemoryRouter><PromptsCard /><Editor /></MemoryRouter></QueryClientProvider>)
    expect(screen.getByText('editor:contract')).toBeInTheDocument()
  })
})
