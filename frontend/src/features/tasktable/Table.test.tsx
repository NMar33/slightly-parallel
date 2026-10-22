import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { TaskTable, useTablePrefs } from './Table'

function Harness() {
  const [prefs, set] = useTablePrefs()
  return <TaskTable rows={[]} prefs={{ ...prefs, columns: ['status', 'priority'] }} set={set} onOpen={() => {}} sprints={{}} />
}

describe('the task table\'s column headings', () => {
  it('keep the keyboard on the heading that was pressed to sort', () => {
    render(<Harness />)
    const before = screen.getByRole('button', { name: 'Status' })
    before.focus()
    fireEvent.click(before)
    // Sorted by it now — and it is the same button, still holding the focus.
    const after = screen.getByRole('button', { name: 'Status' })
    expect(after).toBe(before)
    expect(document.activeElement).toBe(after)
    fireEvent.click(after)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Status' }))
  })
})
