import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { SessionsOfDay } from './parts'
import type { CalSession } from './model'

/**
 * A member's sessions (an agent that joined this project, tk_d1d25a4d) come
 * from the server marked `from: <home>` and count in none of the day's sums.
 * The day lists the project's own chats — the ones its «N chats» counts —
 * and the members' under a line of their own, each marked «from <home>».
 */
const ses = (id: string, over: Partial<CalSession> = {}): CalSession => ({
  id, project: 'beta', agent_id: `cc-${id}`, date: '2026-11-20', start: '10:00', end: '10:20',
  minutes: 20, turns: 3, l1: `chat ${id}`, git: { commits: 0, files: 0, add: 0, del: 0 }, ...over,
})

describe('the chats of a day with a member', () => {
  it('lists the own chats, then the members’ marked «from <home>»', () => {
    render(<MemoryRouter><SessionsOfDay date="2026-11-20" sessions={[
      ses('own1'), ses('mem1', { project: 'alpha', from: 'alpha' }), ses('own2', { start: '11:00' }),
    ]} /></MemoryRouter>)
    const own = screen.getByRole('list', { name: 'chats of this project' })
    expect(within(own).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      expect.stringContaining('chat own1'), expect.stringContaining('chat own2'),
    ])
    const members = screen.getByRole('list', { name: 'from other projects' })
    const item = within(members).getByRole('listitem')
    expect(item.textContent).toContain('chat mem1')
    expect(item.textContent).toContain('from alpha')
  })

  it('says a day with only a member’s chat has none of its own, and still shows it', () => {
    render(<MemoryRouter><SessionsOfDay date="2026-11-20" sessions={[ses('mem1', { from: 'alpha' })]} /></MemoryRouter>)
    expect(screen.getByText('No chats of this project that day.')).toBeInTheDocument()
    expect(screen.getByText('from alpha')).toBeInTheDocument()
  })
})
