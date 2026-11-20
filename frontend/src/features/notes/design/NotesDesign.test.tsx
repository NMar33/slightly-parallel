import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { Checklist, Choice, CopyBlock, Diagram, Fold, Gallery, NoteText, parseFlow } from './blocks'
import { NOTES, SEED } from './mock'
import { parseNote, type Block } from './model'
import { MockNoteEnv } from './MockEnv'
import { NotesDesign } from './NotesDesign'
import { openOf, resetMarks, tick, useMarks } from './store'
import { TaskNotes } from './TaskNotes'

function wrap(ui: ReactNode, url = '/notes') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}><MockNoteEnv>{ui}</MockNoteEnv></MemoryRouter></QueryClientProvider>
}

const note = (id: string) => NOTES.find((n) => n.id === id)!
const first = <T extends Block['type']>(id: string, type: T) =>
  note(id).sections.flatMap((s) => s.blocks.flatMap((b) => (b.type === 'fold' ? b.blocks : [b]))).find((b): b is Extract<Block, { type: T }> => b.type === type)!

beforeEach(() => { resetMarks(SEED) })

describe('the note markup', () => {
  it('reads the title, the sections and every rich block', () => {
    const n = parseNote({ id: 'nt_00000001', project: 'p', kind: 'context', task: '', chat: 'c', created: '', updated: '', versions: 1, body: [
      '# Title', 'Lead tk_fc2d244e.', '## One', '- [ ] a', '- [x] b', '```copy Send', 'hello', '```',
      ':::fold More', '```choice Pick?', '1. x', '2. y', '```', ':::', '## Two', '```gallery', '![cap](shot:list)', '```', '```mermaid', 'flowchart LR', 'A[a] --> B[b]', '```',
    ].join('\n') })
    expect(n.title).toBe('Title')
    expect(n.sections.map((s) => s.title)).toEqual(['', 'One', 'Two'])
    expect(n.sections[1]!.blocks.map((b) => b.type)).toEqual(['check', 'copy', 'fold'])
    expect(n.sections[2]!.blocks.map((b) => b.type)).toEqual(['gallery', 'mermaid'])
    expect(n.refs).toEqual(['tk_fc2d244e'])
  })

  it('keys a tick by the item text, so a new version keeps the ticks of unchanged items', () => {
    const a = parseNote({ ...note('nt_19b0f4ac') })
    const b = parseNote({ ...note('nt_19b0f4ac'), body: note('nt_19b0f4ac').body.replace('## Материалы', '## Материалы\n\nНовая строка.') })
    const ids = (n: typeof a) => n.sections.flatMap((s) => s.blocks).flatMap((x) => (x.type === 'check' ? x.items.map((i) => i.id) : []))
    expect(ids(b)).toEqual(ids(a))
  })

  it('counts what is open: the long sign-in note has 12 manual actions to tick', () => {
    expect(openOf(note('nt_b3e1a0c4'), { ticks: {}, answers: {}, copied: {} }).toTick).toBe(12)
    expect(openOf(note('nt_8c02d5e3'), { ticks: {}, answers: {}, copied: {} }).toAnswer).toBe(2)
  })
})

describe('the rich blocks', () => {
  it('draws ids as chips with the live title and status, and leaves ids in code alone', () => {
    render(wrap(<NoteText text={'See tk_51b87348 and `tk_51b87348`.'} />))
    const chip = document.querySelector('[data-chip="tk_51b87348"]')!
    expect(chip.textContent).toContain('Точки входа: круг дизайна и сборка')
    expect(chip.textContent).toContain('done')
    expect(document.querySelectorAll('[data-chip]')).toHaveLength(1)
  })

  it('copies the raw text of a copy block, ids as ids', async () => {
    const written: string[] = []
    Object.assign(navigator, { clipboard: { writeText: async (s: string) => { written.push(s) } } })
    const block = first('nt_2a6f0e91', 'copy')
    render(wrap(<CopyBlock block={block} />))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Copy/ })) })
    expect(written[0]).toBe(block.text)
    expect(written[0]).toContain('tk_51b87348')
  })

  it('ticks a checklist item and counts what is left', () => {
    const block = first('nt_19b0f4ac', 'check')
    render(wrap(<Checklist block={block} />))
    expect(screen.getByText('2 of 4 left')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox', { name: /GitHub Pages/ }))
    expect(screen.getByText('1 of 4 left')).toBeTruthy()
  })

  it('answers a choice with a button and takes the answer back', () => {
    const block = first('nt_8c02d5e3', 'choice')
    render(wrap(<Choice block={block} />))
    expect(screen.getByText('your answer is needed')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /A — список и карточка/ }))
    expect(screen.getByText('answered')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /A — список и карточка/ }))
    expect(screen.getByText('your answer is needed')).toBeTruthy()
  })

  it('steps through a gallery with its captions', () => {
    const block = first('nt_8c02d5e3', 'gallery')
    render(wrap(<Gallery block={block} />))
    const fig = document.querySelector('figure')!
    expect(within(fig as HTMLElement).getByText(/^A\. Список/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Next picture' }))
    expect(within(fig as HTMLElement).getByText(/^B\. Полки/)).toBeTruthy()
    expect(document.querySelectorAll('[data-shot]').length).toBe(7)
  })

  it('opens a fold that holds open items and says how many', () => {
    const fold = parseNote({ id: 'nt_00000002', project: 'p', kind: 'actions', task: '', chat: 'c', created: '', updated: '', versions: 1,
      body: '# T\n:::fold Steps\n- [ ] one\n- [ ] two\n:::' }).sections[0]!.blocks[0] as Extract<Block, { type: 'fold' }>
    render(wrap(<Fold block={fold} />))
    expect((document.querySelector('details') as HTMLDetailsElement).open).toBe(true)
    expect(screen.getByText('2 open')).toBeTruthy()
  })

  it('draws a mermaid flowchart as boxes and arrows', () => {
    const src = first('nt_2a6f0e91', 'mermaid').src
    expect(parseFlow(src).nodes).toHaveLength(8)
    render(wrap(<Diagram src={src} />))
    expect(screen.getByText('Хук capture.py')).toBeTruthy()
    expect(document.querySelectorAll('[data-block="mermaid"] path[marker-end]').length).toBe(7)
  })
})

describe('the variants', () => {
  for (const [v, sign] of [['a', 'Outline'], ['b', 'Waits on you'], ['c', 'The newest note'], ['d', 'Read the whole note'], ['e', 'Into another chat']] as const) {
    it(`variant ${v} opens on the mock notes`, () => {
      render(wrap(<NotesDesign />, `/notes?v=${v}`))
      expect(document.querySelector(`[data-variant="${v}"]`)).toBeTruthy()
      expect(screen.getAllByText(new RegExp(sign)).length).toBeGreaterThan(0)
      expect(document.querySelectorAll('[data-note]').length).toBeGreaterThan(0)
    })
  }

  it('a tick made in one variant shows in another', () => {
    const { unmount } = render(wrap(<NotesDesign />, '/notes?v=b'))
    const box = screen.getAllByRole('checkbox', { name: /Включить GitHub Pages/ })[0]!
    fireEvent.click(box)
    unmount()
    render(wrap(<NotesDesign />, '/notes?v=d'))
    expect((screen.getAllByRole('checkbox', { name: /Включить GitHub Pages/ })[0] as HTMLInputElement).checked).toBe(true)
  })

  it('the queue leaves out a note a newer one replaces', () => {
    render(wrap(<NotesDesign />, '/notes?v=b'))
    const queue = screen.getByRole('region', { name: 'Waits on you' })
    expect(within(queue).queryByText('Tidepool: вход, состояние на июль')).toBeNull()
  })

  it('shows the empty, loading and error states', () => {
    const { unmount } = render(wrap(<NotesDesign />, '/notes?state=empty'))
    expect(screen.getByText('No notes yet.')).toBeTruthy()
    unmount()
    render(wrap(<NotesDesign />, '/notes?state=error'))
    expect(screen.getByText('Could not load the notes.')).toBeTruthy()
  })
})

describe('the task window', () => {
  it('lists the task\'s notes, the one waiting on an answer first, its choices working in place', () => {
    render(wrap(<TaskNotes taskId="tk_51b87348" notes={NOTES} />))
    const items = [...document.querySelectorAll('[data-note]')].map((e) => e.getAttribute('data-note'))
    expect(items[0]).toBe('nt_8c02d5e3')
    expect(items).toHaveLength(3)
    expect(screen.getByText(/1 waits on an answer/)).toBeTruthy()
    expect(screen.getAllByText('your answer is needed')).toHaveLength(2)
  })

  it('tells its own notes from notes that only name the task', () => {
    render(wrap(<TaskNotes taskId="tk_84803453" notes={NOTES} />))
    expect(screen.getAllByText('names this task').length).toBe(2)
  })

  it('shares the marks with the page', () => {
    function Probe() { return <span data-testid="n">{Object.keys(useMarks().ticks).length}</span> }
    render(wrap(<><TaskNotes taskId="tk_2c7d90a1" notes={NOTES} /><Probe /></>))
    act(() => tick('x', true))
    expect(screen.getByTestId('n').textContent).toBe('1')
  })
})
