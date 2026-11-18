import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../../lib/getJson', () => ({
  postJson: vi.fn(() => Promise.resolve({})),
  getJson: vi.fn((path: string) => Promise.resolve(path.startsWith('/api/time/summary') ? { today_min: path.includes('project=') ? 75 : 190 } : {})),
}))
vi.mock('../../../../lib/uiPrefs', () => ({ persistPref: vi.fn((k: string, v: string) => localStorage.setItem(k, v)) }))

import { HealthLayer, HealthSettings, HealthTint, HealthTitle, useHealthEdge } from '.'
import { getHealth, resetHealthStore, setHealthSettings, tick } from './health'

const T0 = new Date(2026, 10, 18, 9, 0, 0).getTime()
let now = T0
const MIN = 60_000

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{children}</QueryClientProvider>)
}

function Edge() { return <span data-testid="edge">{useHealthEdge() ?? 'none'}</span> }

function workTo(min: number) { act(() => { for (let m = 0; m <= min; m += 1) { now = T0 + m * MIN; tick(now) } }) }

describe('the window parts', () => {
  beforeEach(() => { localStorage.clear(); now = T0; resetHealthStore(() => now) })

  it('the label shows the counter, folded too; the tint and edge appear from yellow', () => {
    workTo(95)
    const { container } = wrap(<><span className="relative"><HealthTint /><HealthTitle folded /></span><Edge /></>)
    expect(container.querySelector('[data-health-label="yellow"]')!.textContent).toBe('1:35')
    expect(container.querySelector('[data-health-tint="yellow"]')).not.toBeNull()
    expect(screen.getByTestId('edge').textContent).toContain('color-mix')
  })

  it('the suggestion and its buttons show only on hover', () => {
    workTo(95)
    const { container } = wrap(<HealthTitle folded={false} />)
    expect(container.querySelector('[data-health-hover]')).toBeNull()
    fireEvent.mouseEnter(container.querySelector('[data-health-label]')!.parentElement!)
    expect(container.querySelector('[data-health-suggestion="yellow"]')).not.toBeNull()
    expect(container.querySelector('[data-health-did]')).not.toBeNull()
  })

  it('a click on the label opens the day card with the server\'s minutes; a break shows its window', async () => {
    workTo(20)
    const { container } = wrap(<><HealthTitle folded={false} /><HealthLayer top={30} project="alpha" /></>)
    fireEvent.click(container.querySelector('[data-health-label]')!)
    expect(await screen.findByText('3:10')).toBeTruthy()
    expect(await screen.findByText('1:15')).toBeTruthy()
    fireEvent.click(container.querySelector('[data-health-start]')!)
    expect(getHealth().d.away).not.toBeNull()
    expect(container.querySelector('[data-health-break]')).not.toBeNull()
    expect(container.querySelector('[data-health-label="break"]')).not.toBeNull()
    fireEvent.click(container.querySelector('[data-health-done]')!)
    expect(getHealth().d.away).toBeNull()
  })

  it('off: nothing is drawn', () => {
    workTo(160)
    act(() => setHealthSettings({ on: false }))
    const { container } = wrap(<><HealthTint /><HealthTitle folded={false} /><HealthLayer top={0} project="alpha" /><Edge /></>)
    expect(container.querySelector('[data-health-label]')).toBeNull()
    expect(container.querySelector('[data-health-tint]')).toBeNull()
    expect(screen.getByTestId('edge').textContent).toBe('none')
  })

  it('the settings rows carry the off switch', () => {
    wrap(<HealthSettings />)
    fireEvent.click(screen.getAllByRole('radio', { checked: false })[0]!)
    expect(getHealth().s.on).toBe(false)
  })
})
