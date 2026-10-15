import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

// The terminal library fails to load (a stale chunk after a release, say).
vi.mock('xterm', () => { throw new Error('chunk missing') })

import { Screen } from './Screen'

describe('Screen', () => {
  it('says so in the pane when the terminal cannot start, instead of an unhandled rejection', async () => {
    render(<QueryClientProvider client={new QueryClient()}><Screen sid="s1" token="tok" /></QueryClientProvider>)
    expect(await screen.findByRole('alert')).toHaveTextContent(/The terminal could not start/)
  })
})
