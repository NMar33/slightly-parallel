import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AgentName } from '../components/AgentName'
import { api } from './api'
import { useAgentNames } from './useAgentNames'

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const AGENTS = [
  { agent_id: 'cc-aaaa1111', agent_name: 'cc-aaaa1111', chat_title: 'evidence-upgrade', created_date: '2609-14' },
  { agent_id: 'cc-bbbb2222', agent_name: 'Reviewer', chat_title: '', created_date: '2609-14' },
]

describe('useAgentNames', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('names an agent the snapshot holds, and leaves the id for one it does not', async () => {
    vi.spyOn(api, 'snapshot').mockResolvedValue({ agents: AGENTS } as never)
    const { result } = renderHook(() => useAgentNames(), { wrapper })
    expect(result.current('cc-aaaa1111')).toBe('cc-aaaa1111')            // before it arrives: never worse than the id
    await waitFor(() => expect(result.current('cc-aaaa1111')).toBe('evidence-upgrade'))
    expect(result.current('cc-bbbb2222')).toBe('Reviewer')
    expect(result.current('cc-unknown0')).toBe('cc-unknown0')
    expect(result.current(null)).toBe('')
  })

  it('AgentName keeps the id in the title', async () => {
    vi.spyOn(api, 'snapshot').mockResolvedValue({ agents: AGENTS } as never)
    render(<AgentName id="cc-bbbb2222" />, { wrapper })
    await waitFor(() => expect(screen.getByText('Reviewer')).toBeInTheDocument())
    expect(screen.getByText('Reviewer')).toHaveAttribute('title', 'cc-bbbb2222')
  })
})
