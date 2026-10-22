import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { PanelBoundary } from './ErrorBoundary'

function Boom({ fail }: { fail: boolean }): JSX.Element {
  if (fail) throw new Error('bad payload')
  return <span>fine</span>
}

describe('a panel that throws', () => {
  it('fails alone, says which, and can try again', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    let fail = true
    const Flaky = () => <Boom fail={fail} />
    render(
      <div>
        <PanelBoundary name="Agent timeline"><Flaky /></PanelBoundary>
        <PanelBoundary name="Sprints"><Boom fail={false} /></PanelBoundary>
      </div>,
    )
    expect(screen.getByText('Agent timeline failed to draw.')).toBeInTheDocument()
    expect(screen.getByText('bad payload')).toBeInTheDocument()
    expect(screen.getByText('fine')).toBeInTheDocument()
    fail = false
    fireEvent.click(screen.getByText('try again'))
    expect(screen.getAllByText('fine')).toHaveLength(2)
  })
})
