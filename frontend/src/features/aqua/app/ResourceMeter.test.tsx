import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { saveSettings } from '../../../lib/settings'
import { useTermScheme } from '../../terminal/useScheme'
import { ResourceMeter } from './ResourceMeter'

const green = 'var(--status-green)'
const yellow = 'var(--status-amber)'
const red = 'var(--status-red)'
const gray = 'var(--text-secondary)'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

// The app calls useTermScheme at its root. This mounts the same cross-window listener.
function TerminalWindow() {
  useTermScheme()
  return <ResourceMeter />
}

it('colors the fill at both thresholds and syncs saved settings with an open terminal window', async () => {
  const stored: Record<string, number | boolean> = {}
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/settings') {
      if (init?.method === 'POST') Object.assign(stored, JSON.parse(String(init.body)).values)
      return Response.json({ groups: [{ settings: Object.entries(stored).map(([key, value]) => ({ key, value })) }] })
    }
    if (url === '/api/monitor/now') {
      return Response.json({
        enabled: true, sample: { temp_c: 67.5, cpu: 75, mem_pct: 90, net_rx: 50 * 1024 ** 2 }, spark: [],
      })
    }
    return Response.json({}, { status: 404 })
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><TerminalWindow /></QueryClientProvider>)

  const button = await screen.findByRole('button', { name: 'System resources' })
  const fill = button.querySelectorAll<HTMLElement>('[data-resource-strip]')
  expect(fill).toHaveLength(1)
  const bar = fill[0]!
  expect(bar.style.backgroundColor).toBe(red)
  const redWidth = parseFloat(bar.style.width)
  fireEvent.mouseEnter(button)
  expect(screen.getByText('68 °C')).toBeTruthy()

  await act(() => saveSettings({ 'terminal.resource_yellow': 50, 'terminal.resource_red': 95 }))
  await waitFor(() => expect(bar.style.backgroundColor).toBe(yellow))
  expect(parseFloat(bar.style.width)).toBeLessThan(redWidth)
  await act(() => saveSettings({ 'terminal.resource_yellow_enabled': false }))
  await waitFor(() => expect(bar.style.backgroundColor).toBe(green))
  const greenWidth = bar.style.width
  await act(() => saveSettings({ 'terminal.resource_color': false }))
  await waitFor(() => expect(bar.style.backgroundColor).toBe(gray))
  expect(bar.style.width).toBe(greenWidth)
  await act(() => saveSettings({ 'terminal.resource_meter': false }))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'System resources' })).toBeNull())
  await act(() => saveSettings({ 'terminal.resource_meter': true }))
  expect(await screen.findByRole('button', { name: 'System resources' })).toBeTruthy()
  expect(screen.queryByText('68 °C')).toBeNull()
})

it('keeps absent signals empty and hides the meter when the system monitor is off', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['settings'], { groups: [] })
  client.setQueryData(['monitor', 'now'], { enabled: true, sample: { cpu: 0 }, spark: [] })
  const { unmount } = render(<QueryClientProvider client={client}><ResourceMeter /></QueryClientProvider>)
  const button = screen.getByRole('button', { name: 'System resources' })
  expect(button.querySelector<HTMLElement>('[data-resource-strip]')?.style.backgroundColor).toBe(green)
  unmount()

  client.setQueryData(['monitor', 'now'], { enabled: false })
  render(<QueryClientProvider client={client}><ResourceMeter /></QueryClientProvider>)
  expect(screen.queryByRole('button', { name: 'System resources' })).toBeNull()
})

it('keeps ordinary transfers green regardless of recent peaks and scales temperature separately', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  const monitor = ['monitor', 'now']
  const mib = 1024 ** 2
  const sample = { net_rx: 2 * mib, net_tx: 3 * mib, temp_c: 67.5 }
  client.setQueryData(monitor, { enabled: true, sample, spark: [{ net_rx: mib }] })
  render(<QueryClientProvider client={client}><ResourceMeter /></QueryClientProvider>)
  const bar = screen.getByRole('button', { name: 'System resources' }).querySelector<HTMLElement>('[data-resource-strip]')!
  expect(bar.style.backgroundColor).toBe(green)
  const greenWidth = parseFloat(bar.style.width)
  act(() => client.setQueryData(monitor, { enabled: true, sample, spark: [{ net_rx: 190 * mib }] }))
  await waitFor(() => expect(bar.style.backgroundColor).toBe(green))
  act(() => client.setQueryData(monitor, { enabled: true, sample: { net_rx: 70 * mib, net_tx: 7 * mib }, spark: [] }))
  await waitFor(() => expect(bar.style.backgroundColor).toBe(yellow))
  expect(parseFloat(bar.style.width)).toBeGreaterThan(greenWidth)
  act(() => client.setQueryData(monitor, { enabled: true, sample: { temp_c: 95 }, spark: [] }))
  await waitFor(() => expect(bar.style.backgroundColor).toBe(red))
})
