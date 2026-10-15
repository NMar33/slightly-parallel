/**
 * Appearance page — the choices render, apply live, and persist.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import AppearancePage from './AppearancePage'
import { ThemeProvider } from '../providers/ThemeProvider'
import { getVariant } from '../lib/variants'

function renderPage() {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <AppearancePage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('AppearancePage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('renders all four sections with their choices', () => {
    renderPage()
    const theme = screen.getByRole('radiogroup', { name: 'Theme' })
    expect(within(theme).getAllByRole('radio')).toHaveLength(3)
    const skins = screen.getByRole('radiogroup', { name: 'App skin' })
    expect(within(skins).getAllByRole('radio')).toHaveLength(5)
    const accents = screen.getByRole('radiogroup', { name: 'Accent color' })
    expect(within(accents).getAllByRole('radio')).toHaveLength(4)
    const scales = screen.getByRole('radiogroup', { name: 'Interface scale' })
    expect(within(scales).getAllByRole('radio')).toHaveLength(4)
  })

  it('picking a skin persists it and marks the card selected', () => {
    renderPage()
    const skins = screen.getByRole('radiogroup', { name: 'App skin' })
    const terminal = within(skins).getByRole('radio', { name: /Terminal phosphor/ })
    fireEvent.click(terminal)
    expect(terminal.getAttribute('aria-checked')).toBe('true')
    expect(getVariant('skin')).toBe('terminal')
    expect(localStorage.getItem('sp-variant-skin')).toBe('terminal')
  })

  it('reset returns every choice to its default, clearing storage', () => {
    renderPage()
    fireEvent.click(screen.getByRole('radio', { name: /Ember/ }))
    fireEvent.click(screen.getByRole('radio', { name: /Large · 125%/ }))
    expect(getVariant('accent')).toBe('ember')
    expect(getVariant('scale')).toBe('125')
    fireEvent.click(screen.getByRole('button', { name: /Reset to defaults/ }))
    expect(getVariant('accent')).toBe('meridian')
    expect(getVariant('scale')).toBe('100')
    expect(localStorage.getItem('sp-variant-accent')).toBeNull()
    expect(localStorage.getItem('sp-variant-scale')).toBeNull()
  })

  it('theme cards drive the theme mode', () => {
    renderPage()
    const theme = screen.getByRole('radiogroup', { name: 'Theme' })
    const dark = within(theme).getByRole('radio', { name: /Dark/ })
    fireEvent.click(dark)
    expect(dark.getAttribute('aria-checked')).toBe('true')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })
})
