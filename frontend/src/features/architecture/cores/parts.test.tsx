import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AgentName } from './parts'

vi.mock('../../../lib/useAgentNames', () => ({
  useAgentNames: () => (id: string) => (id === 'cc-ci' ? 'CI / Backend (macos-latest, Python 3.12) (push) Failing after 2m Details' : id === 'cc-ok' ? 'photo work' : id),
}))

describe('AgentName on the cores pages', () => {
  it('shows a short name, and the id for a pasted title, which stays in the tooltip', () => {
    render(<><AgentName id="cc-ok" /><AgentName id="cc-ci" /></>)
    expect(screen.getByText('photo work')).toBeInTheDocument()
    const ci = screen.getByText('cc-ci')
    expect(ci.getAttribute('title')).toContain('CI / Backend')
  })
})
