import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { defaultLayout, hideItem } from '../features/sidebar/layout'
import { clearHistory, getLayout, setLayout, undoDepth } from '../features/sidebar/store'
import SidebarSettingsPage from './SidebarSettingsPage'

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><SidebarSettingsPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('the sidebar settings page', () => {
  beforeEach(() => {
    localStorage.clear()
    setLayout(defaultLayout(), { history: false })
    clearHistory()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ groups: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('keeps Undo after Reset to default', () => {
    setLayout(hideItem(defaultLayout(), '/tour'))
    mount()
    const reset = screen.getByRole('button', { name: /Reset to default/ })
    expect(reset).toBeEnabled()
    fireEvent.click(reset)
    expect(getLayout().hidden).toEqual([])
    expect(undoDepth()).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /^Undo/ })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: /^Undo/ }))
    expect(getLayout().hidden).toEqual(['/tour'])
  })

  it('cancels a group rename with the X, by mouse or by Tab', () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Views' }))
    const field = screen.getByLabelText('Group name') as HTMLInputElement
    fireEvent.change(field, { target: { value: 'Vieww' } })
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    // The mouse: the button keeps the field's focus, so no blur at all.
    expect(fireEvent.mouseDown(cancel)).toBe(false)
    // The keyboard: focus moves to the button, which is still inside the form.
    fireEvent.blur(field, { relatedTarget: cancel })
    fireEvent.click(cancel)
    const labels = () => getLayout().groups.map((g) => g.label)
    expect(labels()).toContain('Views')
    expect(labels()).not.toContain('Vieww')
    expect(screen.queryByLabelText('Group name')).toBeNull()
  })

  it('commits a group rename when focus leaves the form', () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Views' }))
    const field = screen.getByLabelText('Group name') as HTMLInputElement
    fireEvent.change(field, { target: { value: 'Pages' } })
    fireEvent.blur(field, { relatedTarget: document.body })
    expect(getLayout().groups.map((g) => g.label)).toContain('Pages')
  })
})
