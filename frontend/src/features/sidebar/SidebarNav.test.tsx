import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { SidebarNav } from './SidebarNav'
import { defaultLayout, hideItem, toggleFold } from './layout'
import { clearHistory, setLayout } from './store'

function mount(collapsed = false) {
  return render(<MemoryRouter><SidebarNav collapsed={collapsed} /></MemoryRouter>)
}

describe('SidebarNav', () => {
  beforeEach(() => { localStorage.clear(); setLayout(defaultLayout(), { history: false }); clearHistory() })

  it('renders the groups and no Hidden group when nothing is hidden', () => {
    mount()
    expect(screen.getByText('Views')).toBeInTheDocument()
    expect(screen.getByText('Entries')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Tour' })).toBeInTheDocument()
    expect(screen.queryByText('Hidden')).toBeNull()
    expect(screen.queryByRole('link', { name: 'Lab' })).toBeNull()
  })

  it('puts a hidden page in a folded Hidden group that opens on click', () => {
    setLayout(hideItem(defaultLayout(), '/tour'))
    mount()
    expect(screen.queryByRole('link', { name: 'Tour' })).toBeNull()
    const hidden = screen.getByRole('button', { name: /Hidden/ })
    expect(hidden).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(hidden)
    expect(screen.getByRole('link', { name: 'Tour' })).toBeInTheDocument()
  })

  it('shows a folded group as one button in the rail', () => {
    setLayout(toggleFold(defaultLayout(), 'lenses'))
    mount(true)
    expect(screen.queryByRole('link', { name: 'Scans' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Expand Entries' }))
    expect(screen.getByRole('link', { name: 'Scans' })).toBeInTheDocument()
  })
})
