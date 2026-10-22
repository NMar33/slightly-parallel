/**
 * The link into a page's tour: it carries the page's hash, ✕ puts it away,
 * and bringing the guide back brings it back.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { PageTourLink } from './PageTourLink'

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
})

afterEach(() => vi.unstubAllGlobals())

function mount(at = '/skills#skill=sk_x') {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <PageTourLink script="skills" />
    </MemoryRouter>,
  )
}

describe('PageTourLink', () => {
  it('starts the tour on this page with what is open', () => {
    mount()
    const link = screen.getByRole('link', { name: /How this page works/ })
    expect(link).toHaveAttribute('href', '/skills?tour=skills&step=0#skill=sk_x')
  })

  it('shows nothing for a page without a tour', () => {
    render(
      <MemoryRouter initialEntries={['/x']}>
        <PageTourLink script="no-such-tour" />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('is put away by ✕ and comes back with the guide', () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Hide this link' }))
    expect(screen.queryByRole('link')).toBeNull()
    expect(localStorage.getItem('sp-tourlink-skills-hidden')).toBe('yes')

    // Closing the guide changes nothing here.
    act(() => {
      window.dispatchEvent(new CustomEvent('sp:pref', { detail: { key: 'sp-guide-skills-hidden', value: 'yes' } }))
    })
    expect(screen.queryByRole('link')).toBeNull()

    // "About this page" brings the guide back, and the link with it.
    act(() => {
      window.dispatchEvent(new CustomEvent('sp:pref', { detail: { key: 'sp-guide-skills-hidden', value: null } }))
    })
    expect(screen.getByRole('link', { name: /How this page works/ })).toBeInTheDocument()
    expect(localStorage.getItem('sp-tourlink-skills-hidden')).toBeNull()
  })

  it('stays away across a reload', () => {
    localStorage.setItem('sp-tourlink-skills-hidden', 'yes')
    mount()
    expect(screen.queryByRole('link')).toBeNull()
  })
})
