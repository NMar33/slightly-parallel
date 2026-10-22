import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type APIRequestContext } from '@playwright/test'

/**
 * Every page opens — on the shipped demo data, without a crash.
 *
 * The routes are read from App.tsx itself, so a page added there is tested
 * here with no one remembering to. A route's `:code` is a demo project,
 * `:id` a real agent or prompt where the route wants one. A page fails when
 * the browser throws (an uncaught error) or the app shows its crash screen;
 * an empty state or a "not found" page is an answer, not a failure.
 *
 * The backend has its twin: backend/tests/test_every_get_answers.py.
 */

const here = path.dirname(fileURLToPath(import.meta.url))
const app = fs.readFileSync(path.resolve(here, '../../src/App.tsx'), 'utf-8')
const ROUTES = [...new Set(
  [...app.matchAll(/path="([^"]+)"|path: '([^']+)'/g)]
    .map((m) => m[1] ?? m[2]!)
    .filter((p) => p.startsWith('/') && !p.includes('*')),
)].sort()

interface Ids { code: string; agent: string; prompt: string }
let ids: Promise<Ids> | null = null

async function lookup(request: APIRequestContext): Promise<Ids> {
  const get = async (url: string) => (await request.get(url)).json().catch(() => ({}))
  const snap = await get('/api/snapshot')
  const code = snap.projects?.[0]?.code ?? 'x'
  const agents = await get(`/api/agents?project=${encodeURIComponent(code)}`)
  const agent = (Array.isArray(agents) ? agents : agents.agents ?? [])[0]?.agent_id ?? 'x'
  const prompts = await get('/api/prompts?limit=1')
  const prompt = (prompts.prompts ?? prompts.rows ?? [])[0]?.id ?? 'x'
  return { code, agent, prompt }
}

function fill(route: string, v: Ids): string {
  return route
    .replace(':code', encodeURIComponent(v.code))
    .replace(/^\/agent\/:id/, `/agent/${encodeURIComponent(v.agent)}`)
    .replace(/^\/prompts\/:id/, `/prompts/${encodeURIComponent(v.prompt)}`)
    .replace(/:id/g, 'x')
}

test.describe('every page opens', () => {
  test('the route list was read', () => {
    expect(ROUTES.length).toBeGreaterThan(30)
  })

  for (const route of ROUTES) {
    test(route, async ({ page, request }) => {
      ids ??= lookup(request)
      const url = fill(route, await ids)
      const thrown: string[] = []
      page.on('pageerror', (e) => thrown.push(String(e)))
      await page.goto(url, { waitUntil: 'domcontentloaded' })
      // Long enough for the page's first data to arrive and draw.
      await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
      await expect(page.getByTestId('crash-screen')).toHaveCount(0)
      expect(thrown, `uncaught in ${url}`).toEqual([])
    })
  }
})

/**
 * The same walk in the dark theme, on the pages people live in. Dark is a
 * second set of token values, so a colour that exists only in light shows
 * up here as a crash or a console error — and a smaller list keeps CI fast.
 */
const DARK_ROUTES = ['/', '/kanban', '/chats', '/calendar', '/visions', '/rules', '/problems',
  '/monitor', '/stats', '/terminal', '/prompts', '/project/:code']

test.describe('the dark theme opens', () => {
  test.use({ colorScheme: 'dark' })
  for (const route of DARK_ROUTES) {
    test(`${route} in dark`, async ({ page, request }) => {
      ids ??= lookup(request)
      const url = fill(route, await ids)
      await page.addInitScript(() => { try { localStorage.setItem('sp-theme', 'dark') } catch { /* fine */ } })
      const thrown: string[] = []
      page.on('pageerror', (e) => thrown.push(String(e)))
      await page.goto(url, { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
      await expect(page.getByTestId('crash-screen')).toHaveCount(0)
      expect(thrown, `uncaught in ${url} (dark)`).toEqual([])
      // The theme really applied: the app ground is the dark base, not white.
      const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
      expect(bg, `body ground in ${url}`).not.toBe('rgb(255, 255, 255)')
    })
  }
})

/**
 * Every page in Russian. The unit tests all run in English, so this is where
 * a Russian render is proved: no crash, no uncaught error, the sidebar in
 * Russian, and the page's own title in Russian unless it names data (a
 * project, an agent, a prompt), which stays as it was written.
 */
const CYRILLIC = /[А-Яа-яЁё]/
const DATA_TITLE = /^\/(agent|prompts|project)\b|:id|:code/

test.describe('every page opens in Russian', () => {
  for (const route of ROUTES) {
    test(`${route} in Russian`, async ({ page, request }) => {
      ids ??= lookup(request)
      const url = fill(route, await ids)
      // The language is a preference the server keeps for every tab. Answered
      // here, in this page only: a Russian choice written to the shared test
      // server would turn the English tests running beside these Russian.
      await page.route('**/api/prefs', (r) => (r.request().method() === 'GET'
        ? r.fulfill({ json: { prefs: { 'sp-lang': 'ru' } } })
        : r.fulfill({ json: { ok: true } })))
      await page.addInitScript(() => { try { localStorage.setItem('sp-lang', 'ru') } catch { /* fine */ } })
      const thrown: string[] = []
      page.on('pageerror', (e) => thrown.push(String(e)))
      await page.goto(url, { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
      await expect(page.getByTestId('crash-screen')).toHaveCount(0)
      expect(thrown, `uncaught in ${url} (ru)`).toEqual([])
      const nav = await page.locator('nav').first().locator('a').allInnerTexts()
      const english = nav.map((s) => s.trim()).filter((s) => s && !CYRILLIC.test(s))
      expect(english, `sidebar entries not in Russian on ${url}`).toEqual([])
      if (!DATA_TITLE.test(route)) {
        const h1 = page.locator('main h1, h1').first()
        if (await h1.count()) {
          const title = (await h1.innerText()).trim()
          if (title) expect(title, `page title on ${url}`).toMatch(CYRILLIC)
        }
      }
    })
  }
})
