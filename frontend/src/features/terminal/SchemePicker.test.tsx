import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SETTINGS_QUERY_KEY } from '../../lib/settings'
import { SchemeButton, useWindowScheme } from '../aqua/app/scheme'
import { SchemePicker } from './SchemePicker'
import { useApplyTermScheme } from './useScheme'

let stored: Record<string, string>
const posts: Array<Record<string, unknown>> = []
let refuse = false

const payload = () => ({
  groups: [{ name: 'Terminal', settings: [
    { key: 'terminal.scheme', value: stored['terminal.scheme'] },
    { key: 'terminal.scheme_scope', value: stored['terminal.scheme_scope'] },
  ] }],
  environment: [], file: '/x/settings.json',
})
const answer = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))

beforeEach(() => {
  stored = { 'terminal.scheme': 'sp-now', 'terminal.scheme_scope': 'terminal' }
  posts.length = 0
  refuse = false
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (String(url) !== '/api/settings') return answer({ detail: 'Not Found' }, 404)
    if (init?.method === 'POST') {
      const { values } = JSON.parse(String(init.body)) as { values: Record<string, string> }
      posts.push(values)
      if (refuse) return answer({ detail: 'terminal.scheme must be one of: …' }, 422)
      Object.assign(stored, values)
      return answer({ ok: true })
    }
    return answer(payload())
  }))
})
afterEach(() => { vi.unstubAllGlobals(); document.documentElement.removeAttribute('style') })

const wrap = (ui: React.ReactNode, qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) =>
  ({ qc, ...render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>) })

const tile = (name: RegExp) => within(screen.getByRole('radiogroup', { name: 'Colour scheme' })).getByRole('radio', { name })

describe('the scheme picker', () => {
  it('shows all twelve schemes with the same sample, the current one marked, Solarized Light marked low', async () => {
    wrap(<SchemePicker />)
    await waitFor(() => expect(tile(/^Slightly Parallel now/).getAttribute('aria-checked')).toBe('true'))
    const tiles = within(screen.getByRole('radiogroup', { name: 'Colour scheme' })).getAllByRole('radio')
    expect(tiles).toHaveLength(12)
    expect(document.querySelectorAll('[data-preview]')).toHaveLength(12)
    expect(new Set([...document.querySelectorAll('[data-preview]')].map((p) => p.textContent)).size).toBe(1)
    expect(tile(/^Nord/).textContent).toContain('9.2 AAA')
    expect(tile(/^Solarized Light/).querySelector('[data-low]')?.textContent).toBe('low contrast')
    expect(document.querySelectorAll('[data-low]')).toHaveLength(1)
  })

  it('a click saves the scheme and marks it at once; the scope saves too', async () => {
    wrap(<SchemePicker />)
    await waitFor(() => expect(tile(/^Nord/)).toBeTruthy())
    fireEvent.click(tile(/^Nord/))
    await waitFor(() => expect(tile(/^Nord/).getAttribute('aria-checked')).toBe('true'))
    await waitFor(() => expect(posts).toEqual([{ 'terminal.scheme': 'nord' }]))
    fireEvent.click(screen.getByRole('radio', { name: 'whole window' }))
    await waitFor(() => expect(posts.at(-1)).toEqual({ 'terminal.scheme_scope': 'window' }))
    expect(stored).toEqual({ 'terminal.scheme': 'nord', 'terminal.scheme_scope': 'window' })
  })

  it('a refused save puts the old pick back', async () => {
    refuse = true
    wrap(<SchemePicker />)
    await waitFor(() => expect(tile(/^Dracula/)).toBeTruthy())
    fireEvent.click(tile(/^Dracula/))
    await waitFor(() => expect(tile(/^Slightly Parallel now/).getAttribute('aria-checked')).toBe('true'))
    expect(tile(/^Dracula/).getAttribute('aria-checked')).toBe('false')
  })
})

function Root() {
  useApplyTermScheme()
  const s = useWindowScheme()
  return <div data-testid="root" data-scheme={s.id} style={s.style}><SchemeButton /></div>
}

describe('the page and the terminal window in the scheme', () => {
  it('sp-now leaves the page as it was; a scheme sets the terminal tokens, and the whole window the chrome', async () => {
    const { qc } = wrap(<Root />)
    const root = () => screen.getByTestId('root')
    const html = document.documentElement.style
    await waitFor(() => expect(html.getPropertyValue('--sp-term-bg')).toBe('#0E1013'))
    expect(html.getPropertyValue('--term-ground')).toBe('')
    expect(root().style.getPropertyValue('--aq-term-bg')).toBe('')

    act(() => { stored['terminal.scheme'] = 'catppuccin-latte'; void qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }) })
    await waitFor(() => expect(root().dataset.scheme).toBe('catppuccin-latte'))
    expect(html.getPropertyValue('--sp-term-bg')).toBe('#EFF1F5')
    expect(html.getPropertyValue('--term-ground')).toBe('#EFF1F5')
    expect(root().style.getPropertyValue('--aq-term-bg')).toBe('#EFF1F5')
    expect(root().style.getPropertyValue('--r2-strip')).toBe('')

    act(() => { stored['terminal.scheme_scope'] = 'window'; void qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }) })
    await waitFor(() => expect(root().style.getPropertyValue('--r2-strip')).not.toBe(''))
    expect(root().style.getPropertyValue('--bg-base')).toBe('#EFF1F5')
    expect(root().style.colorScheme).toBe('light')

    act(() => { stored = { 'terminal.scheme': 'sp-now', 'terminal.scheme_scope': 'terminal' }; void qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }) })
    await waitFor(() => expect(root().dataset.scheme).toBe('sp-now'))
    expect(html.getPropertyValue('--term-ground')).toBe('')
    expect(root().style.getPropertyValue('--r2-strip')).toBe('')
  })

  it('the window\'s quick switch opens the same grid; Esc closes it', async () => {
    wrap(<Root />)
    fireEvent.click(screen.getByRole('button', { name: 'Colour scheme' }))
    const dialog = screen.getByRole('dialog', { name: 'Colour scheme' })
    await waitFor(() => expect(within(dialog).getAllByRole('radio', { name: /AAA|AA/ }).length).toBeGreaterThan(0))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
