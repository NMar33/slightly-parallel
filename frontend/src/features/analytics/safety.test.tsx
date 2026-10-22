import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SafetyBadge } from './safety'

describe('SafetyBadge', () => {
  it('opens on its button and closes on a click outside or Escape, leaving the outside click to its target', () => {
    let clicked = 0
    render(<><button type="button" onClick={() => { clicked += 1 }}>elsewhere</button><SafetyBadge lines={['SELECT only']} /></>)
    const badge = screen.getByRole('button', { name: /read-only/ })
    fireEvent.click(badge)
    expect(screen.getByText('SELECT only')).toBeInTheDocument()
    fireEvent.mouseDown(screen.getByText('SELECT only'))
    expect(screen.getByText('SELECT only')).toBeInTheDocument()   // inside: stays
    const outside = screen.getByText('elsewhere')
    fireEvent.mouseDown(outside)
    fireEvent.click(outside)
    expect(screen.queryByText('SELECT only')).toBeNull()
    expect(clicked).toBe(1)                                         // no invisible backdrop ate it
    fireEvent.click(badge)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByText('SELECT only')).toBeNull()
  })
})
