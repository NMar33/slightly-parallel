import { describe, expect, it } from 'vitest'

import { areasOf } from './settings'

describe('areasOf — which stamp areas a query listens to', () => {
  it('sends task-shaped keys to the tasks area', () => {
    for (const key of [['tasks', 'board'], ['sprints', 'deck', 0], ['milestones', 'x'], ['time-running'], ['evidence-prompts']])
      expect(areasOf(key), String(key)).toContain('tasks')
  })
  it('sends the kept pages and day books to their ledgers, not to the chats', () => {
    for (const head of ['visions', 'rules', 'problems', 'skills', 'artifacts', 'decisions-page', 'standups-page', 'prompt-library'])
      expect(areasOf([head, 'x'])).toEqual(['rest'])
  })
  it('keeps what never lives in the data root off the freshness signal', () => {
    for (const head of ['monitor', 'terminal', 'logs', 'backups', 'backup', 'capture'])
      expect(areasOf([head, 'x'])).toEqual([])
  })
  it('sends every time key to the tasks area, never to "any"', () => {
    for (const head of ['time-entries', 'time-entries-all', 'time-running', 'time-summary-all', 'time-sprints-every', 'time-task', 'time-auto'])
      expect(areasOf([head])).toEqual(['tasks'])
  })
  it('asks for the board\'s task-only counts on a task change, not on a chat', () => {
    for (const kind of ['since', 'notes', 'evidence', 'links'])
      expect(areasOf(['tasks', 'board', kind, 'p', 'p'])).toEqual(['tasks'])
    expect(areasOf(['tasks', 'board', 'mentions', 'p', 'p'])).toEqual(['tasks', 'chats'])
    expect(areasOf(['tasks', 'project', 'p'])).toEqual(['tasks'])
    expect(areasOf(['tasks', 'all'])).toEqual(['tasks'])
    expect(areasOf(['tasks', 'board', 'tasks', 'p', 'p', false])).toEqual(['tasks', 'chats'])
  })
  it('answers null for a key it does not know — reload on every change is never wrong', () => {
    expect(areasOf(['something-new'])).toBeNull()
  })
  it('a chat and a task lens follow the chats', () => {
    expect(areasOf(['session-turns', 'a'])).toEqual(['chats'])
    expect(areasOf(['lens', 'tasks'])).toEqual(['tasks', 'chats'])
  })
  it('the tour scripts and stills follow the rest', () => {
    expect(areasOf(['tour', 'scripts'])).toEqual(['rest'])
    expect(areasOf(['story-templates'])).toEqual([])
  })
  it('the home page\'s year and the film do not reload on a chat moving', () => {
    expect(areasOf(['overview', 'year', '250101'])).toEqual([])
    expect(areasOf(['overview', 'standups'])).toEqual(['rest'])
    expect(areasOf(['timelapse', 'p'])).toEqual([])
  })
})
