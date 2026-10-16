/**
 * The guide is written from the pages: every product route has a section,
 * and the old four-level story is gone from the text.
 */
import { describe, expect, it } from 'vitest'

import appSource from '../App.tsx?raw'
import guideSource from './GuidePage.tsx?raw'
import pagesSource from '../features/guide/pages.ts?raw'
import { GUIDE_PAGES, guideAnchor } from '../features/guide/pages'

/** The routes from the "the product" marker in App.tsx to the end of the routes. */
function productRoutes(): string[] {
  const start = appSource.indexOf('the product')
  const end = appSource.indexOf('</Routes>', start)
  const block = appSource.slice(start, end)
  const out: string[] = []
  for (const m of block.matchAll(/<Route\s+path="([^"]+)"/g)) out.push(m[1])
  return out
}

describe('the guide', () => {
  it('has a section for every product route', () => {
    const routes = productRoutes().filter((r) => r !== '*')
    // Redirects and second names are not pages: /chats is the Chats page,
    // and /sessions is the address it was published at, still answering.
    const redirects = ['/activity', '/sessions', '/health']   // /health is the lower half of /monitor now
    const known = new Set(GUIDE_PAGES.map((p) => p.route))
    const missing = routes.filter((r) => {
      if (redirects.includes(r) || known.has(r)) return false
      // A sub-route is covered by its page: /tour/custom by /tour, /prompts/:id by /prompts.
      const parent = r.replace(/\/[^/]+$/, '')
      return !known.has(parent)
    })
    expect(missing).toEqual([])
    // The three lens pages must be here by name.
    for (const base of ['scans', 'standups', 'decisions']) expect(known.has(`/${base}`)).toBe(true)
  })

  it('names every page in its own words, without the four-level story', () => {
    const text = `${guideSource}\n${pagesSource}`
    expect(text).not.toMatch(/\bL[1-4]\b/)
    expect(text).not.toMatch(/pyramid/i)
    expect(text).not.toMatch(/\blayers?\b/i)
    expect(text).not.toMatch(/\blevel contract\b/i)
  })

  it('gives every page a distinct anchor', () => {
    const anchors = GUIDE_PAGES.map((p) => guideAnchor(p.route))
    expect(new Set(anchors).size).toBe(anchors.length)
    expect(guideAnchor('/')).toBe('overview')
    expect(guideAnchor('/settings/sidebar')).toBe('settings-sidebar')
    expect(guideAnchor('/agent/:id')).toBe('agent-id')
  })

  it('keeps every page text short and plain', () => {
    for (const p of GUIDE_PAGES) {
      expect(p.text.length, p.route).toBeLessThan(600)
      expect(p.text, p.route).not.toMatch(/\?/)
    }
  })
})
