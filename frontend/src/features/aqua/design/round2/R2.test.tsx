import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AquaDesign } from '../AquaDesign'
import { getAqua, resetAqua, setChatsAsleep } from '../store'
import { chatsIn, detachWin, getDesk, group, resetDesk, serversFor, ungroup, workspaceSleepPlan, wsOfChat } from './desk'

const page = (q: string) => render(<MemoryRouter initialEntries={[`/aqua?${q}`]}><AquaDesign /></MemoryRouter>)
const mainFrame = () => screen.getByRole('dialog', { name: 'Window: SP Aqua' })

beforeEach(() => { resetAqua(); resetDesk(); Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true }) })

describe('round 2: the workspaces', () => {
  it('starts with one workspace per project and the Release week group across two projects', () => {
    const d = getDesk()
    expect(chatsIn(d, 'ws_release').map((s) => s.id)).toEqual(['cc-2a6e0d93', 'cc-f41a9d70'])
    expect(new Set(serversFor(d, 'ws_release').map((s) => s.project))).toEqual(new Set(['kelp', 'lumen']))
  })

  it('moves chats into a new group, out of their old workspace, and ungroup sends them back to their project', () => {
    const id = group(['cc-b03d55e1', 'cc-7f2b8c40'])
    let d = getDesk()
    expect(wsOfChat(d, 'cc-b03d55e1')).toBe(id)
    expect(chatsIn(d, 'ws_harbor').some((s) => s.id === 'cc-b03d55e1')).toBe(false)
    ungroup(id)
    d = getDesk()
    expect(wsOfChat(d, 'cc-b03d55e1')).toBe('ws_harbor')
    expect(wsOfChat(d, 'cc-7f2b8c40')).toBe('ws_kelp')
  })

  it('sleeping a workspace keeps a server running that another awake workspace still needs', () => {
    // Release week holds release-0.9 (Kelp); watch-debounce (Kelp) stays awake in Kelp CLI, so the docs preview stays up
    const plan = workspaceSleepPlan(getDesk(), 'ws_release', getAqua().asleep, true)
    expect(plan.kept).toContain('docs preview')
    act(() => { setChatsAsleep(plan.chats, true, plan.servers) })
    expect(getAqua().asleep['cc-2a6e0d93']).toBe(true)
    expect(getAqua().up.ew_k1).toBe(true)
  })
})

describe('round 2: the window', () => {
  it('grows outward for a sidebar: the window moves left by the sidebar, the terminal stays put', () => {
    page('v=g')
    const before = parseInt(mainFrame().style.left, 10)
    fireEvent.click(screen.getAllByRole('button', { name: 'Left sidebar' })[0]!)
    expect(parseInt(mainFrame().style.left, 10)).toBe(before - 236)
    expect(screen.getByRole('navigation', { name: 'Workspaces' })).toBeTruthy()
  })

  it.each(['g', 'h', 'i'])('variant %s zooms out to the workspace and to every workspace, and Esc comes back', (v) => {
    page(`v=${v}`)
    fireEvent.keyDown(window, { key: 'ArrowUp', ctrlKey: true, shiftKey: true })
    expect(screen.getByRole('button', { name: 'Detach the workspace' })).toBeTruthy()
    fireEvent.keyDown(window, { key: 'ArrowUp', ctrlKey: true, shiftKey: true })
    expect(screen.getAllByText('Every workspace').length).toBeGreaterThan(0)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByText('Every workspace')).toBeNull()
  })

  it('a detached workspace gets its own window and leaves the main window strip', () => {
    page('v=g')
    act(() => { detachWin('ws', 'ws_release') })
    expect(screen.getByRole('dialog', { name: /Window: release-0.9 — Release week/ })).toBeTruthy()
  })
})
