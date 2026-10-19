import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ComputerCard, IntegrateComputer } from './Computer'
import type { ComputerState } from './data'

const off: ComputerState = {
  autostart: { on: false, paths: [] }, shortcut: { on: false, paths: [] }, system: 'linux', sandbox: false,
}

describe('IntegrateComputer', () => {
  it('offers both, clear, and says where to turn them off', () => {
    render(<IntegrateComputer state={off} autostart={false} shortcut={false} onAutostart={() => {}} onShortcut={() => {}} />)
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[]
    expect(boxes.map((b) => b.checked)).toEqual([false, false])
    expect(screen.getByText(/Settings › On this computer/)).toBeInTheDocument()
  })
  it('shows what is on as on, and asks nothing on a test server', () => {
    const { rerender, container } = render(<IntegrateComputer
      state={{ ...off, autostart: { on: true, paths: ['/x'] } }} autostart={false} shortcut={false}
      onAutostart={() => {}} onShortcut={() => {}} />)
    const first = screen.getAllByRole('checkbox')[0] as HTMLInputElement
    expect(first.checked && first.disabled).toBe(true)
    rerender(<IntegrateComputer state={{ ...off, sandbox: true }} autostart={false} shortcut={false}
      onAutostart={() => {}} onShortcut={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('ComputerCard', () => {
  it('switches one at once', async () => {
    const fetch = vi.fn(async (url: string, _init?: RequestInit) => new Response(JSON.stringify(
      url.includes('/info') ? { computer: off } : { changed: {}, computer: off }), { status: 200, headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetch)
    render(<QueryClientProvider client={new QueryClient()}><ComputerCard /></QueryClientProvider>)
    fireEvent.click((await screen.findAllByRole('checkbox'))[0]!)
    await vi.waitFor(() => expect(fetch.mock.calls.some(([u, init]) =>
      String(u).endsWith('/api/setup/computer') && JSON.parse(String((init as RequestInit).body)).autostart === true)).toBe(true))
    vi.unstubAllGlobals()
  })
})
