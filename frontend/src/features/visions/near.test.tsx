import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { VisionsDocument } from './Document'
import { SkillsLibrary } from '../skills/Library'

/** An IntersectionObserver the test drives: `show(el)` brings an element near. */
class FakeObserver {
  static all: FakeObserver[] = []
  watched = new Set<Element>()
  constructor(private cb: IntersectionObserverCallback) { FakeObserver.all.push(this) }
  observe(el: Element) { this.watched.add(el) }
  unobserve(el: Element) { this.watched.delete(el) }
  disconnect() { this.watched.clear() }
  takeRecords() { return [] }
  static show(el: Element) {
    for (const o of FakeObserver.all) {
      if (!o.watched.has(el)) continue
      o.cb([{ target: el, isIntersecting: true } as IntersectionObserverEntry], o as unknown as IntersectionObserver)
    }
  }
}

const row = (i: number) => ({
  id: `vs_${i}`, created_date: `2609-${String(10 + i).padStart(2, '0')}`, created_time: '10:00', project: 'p',
  agent_id: 'cc-a', l1: `Vision number ${i}`, source: 'captured', session_id: null, source_turn: null,
  versions_n: 1, tags: 'one', l2: `What vision ${i} means.`,
})

let asked: string[] = []

/** What the pages read beside the entries, answered empty. */
const QUIET: Record<string, () => unknown> = {
  '/api/sets': () => ({ sets: [] }),
  '/api/integrations/targets': () => ({ targets: [] }),
  '/api/integrations': () => ({ integrations: [] }),
  '/api/skills/found': () => ({ found: [] }),
  '/api/skills/usage': () => ({ days: 30, skills: {}, unknown: [] }),
}

function serve(own: Record<string, (url: string) => unknown>) {
  asked = []
  const routes = { ...QUIET, ...own }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    asked.push(url)
    const hit = Object.keys(routes).find((k) => url.startsWith(k))
    const body = hit ? routes[hit]!(url) : {}
    return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => JSON.stringify(body) }
  }))
}

const visionDetail = (url: string) => {
  const id = url.split('/').pop()!
  const i = Number(id.slice(3))
  return {
    metadata: row(i), l2: `What vision ${i} means.`, l3: [], l4: '',
    kept: { kind: 'vision', message: `The words of vision ${i}`, turn: null, before: [], after: [], versions: [], current: null },
  }
}

const details = (prefix: string) => asked.filter((u) => new RegExp(`^${prefix}/[a-z]+_\\d+$`).test(u))

function mount(ui: React.ReactElement, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  FakeObserver.all = []
  vi.stubGlobal('IntersectionObserver', FakeObserver)
  window.location.hash = ''
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.location.hash = '' })

describe('kept pages read records near the screen', () => {
  it('reads the first screen, then a section as it comes near', async () => {
    serve({
      '/api/visions?': () => ({ total: 10, visions: Array.from({ length: 10 }, (_, i) => row(i)) }),
      '/api/visions/': visionDetail,
    })
    mount(<VisionsDocument />)
    // The first screen opens with its records; every entry is listed with its interpretation.
    expect(await screen.findByText('The words of vision 9')).toBeInTheDocument()
    expect(details('/api/visions')).toHaveLength(4)
    expect(screen.getAllByText('What vision 0 means.').length).toBeGreaterThan(0)
    expect(screen.queryByText('The words of vision 0')).not.toBeInTheDocument()
    // The oldest comes near: its record is read, and only its.
    const section = document.getElementById('vision-vs_0')!.parentElement!
    act(() => FakeObserver.show(section))
    expect(await screen.findByText('The words of vision 0')).toBeInTheDocument()
    expect(details('/api/visions')).toHaveLength(5)
    expect(asked.some((u) => u.includes('with_l2=1'))).toBe(true)
  })

  it('a search reads every record, since it looks in the words too', async () => {
    serve({
      '/api/visions?': () => ({ total: 10, visions: Array.from({ length: 10 }, (_, i) => row(i)) }),
      '/api/visions/': visionDetail,
    })
    mount(<VisionsDocument />)
    await screen.findByText('The words of vision 9')
    fireEvent.change(screen.getByLabelText('Find in visions'), { target: { value: 'words of vision 2' } })
    await waitFor(() => expect(details('/api/visions')).toHaveLength(10))
    expect(await screen.findByText('The words of vision 2')).toBeInTheDocument()
  })

  it('the skill opened is read wherever its row is', async () => {
    const skill = (i: number) => ({
      id: `sk_${i}`, created_date: '2609-20', created_time: '10:00', project: 'p', agent_id: 'cc-a', l1: `skill-${i}`,
      name: `skill-${i}`, description: `Does thing ${i}.`, status: 'active', source: 'written', session_id: null,
      source_turn: 0, versions_n: 1, tags: null,
    })
    serve({
      '/api/skills?': () => ({ total: 30, skills: Array.from({ length: 30 }, (_, i) => skill(i)) }),
      '/api/skills/': (url) => {
        const i = Number(url.split('/').pop()!.slice(3))
        return {
          metadata: skill(i),
          skill: { current: { n: 1, at: '2609-20 10:00', how: 'written', note: '', skill_md: `---\nname: skill-${i}\ndescription: Does thing ${i}.\n---\n\nStep ${i}.`, files: {}, hash: 'h' }, checks: [], installs: [], usage: { uses: 0, recent: 0, days: 30, projects: [], last_used: '', sessions: [] } },
        }
      },
    })
    window.location.hash = '#skill=sk_25'
    mount(<SkillsLibrary />)
    await waitFor(() => expect(asked).toContain('/api/skills/sk_25'))
    // The first rows and the open one, not all thirty.
    await waitFor(() => expect(details('/api/skills').length).toBeGreaterThan(0))
    expect(details('/api/skills').length).toBeLessThan(30)
  })
})
