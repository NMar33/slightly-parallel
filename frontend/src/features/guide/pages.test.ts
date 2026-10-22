import { describe, expect, it } from 'vitest'

import { GUIDE_PAGES } from './pages'

describe('the guide names every command', () => {
  it('lists #evidence and #prompt with the rest', () => {
    const all = GUIDE_PAGES.flatMap((p) => p.commands ?? (p.command ? [p.command] : []))
    for (const c of ['#vision', '#rule', '#problem', '#skill', '#artifact', '#scan', '#standup',
      '#decision', '#task', '#evidence', '#prompt', '#architecture']) {
      expect(all, c).toContain(c)
    }
  })

  it('teaches no levels', () => {
    for (const p of GUIDE_PAGES) expect(p.text, p.route).not.toMatch(/\bL[1-4]\b|pyramid|POST \/api/i)
  })
})
