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
  const bars = Array.from(button.querySelectorAll<HTMLElement>('[data-resource-bar]'))
  const colors = () => bars.map((bar) => bar.style.backgroundColor)
  const heights = () => bars.map((bar) => bar.style.height)
  expect(colors()).toEqual([green, yellow, red, green])
  expect(heights()).toEqual(['50%', '75%', '90%', '50%'])
  fireEvent.click(button)
  expect(screen.getByText('68 °C')).toBeTruthy()

  await act(() => saveSettings({ 'terminal.resource_yellow': 50, 'terminal.resource_red': 75 }))
  await waitFor(() => expect(colors()).toEqual([yellow, red, red, yellow]))
  await act(() => saveSettings({ 'terminal.resource_color': false }))
  await waitFor(() => expect(colors()).toEqual([gray, gray, gray, gray]))
  expect(heights()).toEqual(['50%', '75%', '90%', '50%'])
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
  const bars = Array.from(button.querySelectorAll<HTMLElement>('[data-resource-bar]'))
  expect(bars.map((bar) => bar.style.backgroundColor)).toEqual([gray, green, gray, gray])
  expect(bars.map((bar) => bar.style.height)).toEqual(['0%', '0%', '0%', '0%'])
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
  const bars = screen.getByRole('button', { name: 'System resources' }).querySelectorAll<HTMLElement>('[data-resource-bar]')
  const fills = () => [bars[0], bars[3]].map((bar) => [bar.style.backgroundColor, bar.style.height])
  expect(fills()).toEqual([[green, '50%'], [green, '5%']])

  act(() => client.setQueryData(monitor, { enabled: true, sample, spark: [{ net_rx: 190 * mib }] }))
  await waitFor(() => expect(fills()).toEqual([[green, '50%'], [green, '5%']]))
  act(() => client.setQueryData(monitor, { enabled: true, sample: { net_rx: 70 * mib, net_tx: 7 * mib, temp_c: 95 }, spark: [] }))
  await waitFor(() => expect(fills()).toEqual([[red, '100%'], [yellow, '77%']]))
  act(() => client.setQueryData(monitor, { enabled: true, sample: { net_rx: 150 * mib }, spark: [] }))
  await waitFor(() => expect(fills()).toEqual([[gray, '0%'], [red, '100%']]))
})
