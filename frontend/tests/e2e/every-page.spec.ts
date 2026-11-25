import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

/**
 * Every page opens — on the shipped demo data, without a crash.
 *
 * The routes are read from App.tsx itself, so a page added there is tested
 * here with no one remembering to. A route's `:code` is a demo project,
 * `:id` a real agent or prompt where the route wants one. A page fails when
 * the browser throws (an uncaught error), the app shows its crash screen,
 * the server answers one of its requests with a 5xx (an empty state drawn
 * over a server error would pass otherwise), or the page logs an error to
 * the console; an empty state or a "not found" page (a 404) is an answer,
 * not a failure.
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

/**
 * What went wrong on a page while it opened: uncaught errors, 5xx answers,
 * console errors. A 4xx is the browser's own console line for an answer
 * ("not found" is a page), so it is left out; its 5xx twin is caught by the
 * response itself.
 */
function watch(page: Page): { problems: string[] } {
  const problems: string[] = []
  page.on('pageerror', (e) => problems.push(`uncaught: ${String(e)}`))
  page.on('response', (r) => { if (r.status() >= 500) problems.push(`${r.status()} ${r.request().method()} ${r.url()}`) })
  page.on('requestfailed', (r) => {
    const failure = r.failure()?.errorText
    if (failure === 'net::ERR_NO_BUFFER_SPACE') problems.push(`${failure} ${r.method()} ${r.url()}`)
  })
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const text = m.text()
    if (/^Failed to load resource: the server responded with a status of 4\d\d/.test(text)) return
    problems.push(`console.error: ${text}`)
  })
  return { problems }
}

function fill(route: string, v: Ids): string {
  return route
    .replace(':code', encodeURIComponent(v.code))
    .replace(/^\/agent\/:id/, `/agent/${encodeURIComponent(v.agent)}`)
    .replace(/^\/prompts\/:id/, `/prompts/${encodeURIComponent(v.prompt)}`)
    .replace(/:id/g, 'x')
}

const BATCH = process.env.SP_E2E_PAGE_WALK_BATCH === '1'

function walk(routes: string[], suffix = '', prepare?: (page: Page) => Promise<void>,
  verify?: (page: Page, url: string, route: string) => Promise<void>): void {
  async function check(page: Page, problems: string[], route: string, values: Ids): Promise<void> {
    const url = fill(route, values)
    problems.length = 0
    await page.goto(url, { waitUntil: 'domcontentloaded' })
    // Long enough for the page's first data to arrive and draw.
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
    await expect(page.getByTestId('crash-screen')).toHaveCount(0)
    expect(problems, `in ${url}${suffix}`).toEqual([])
    await verify?.(page, url, route)
  }

  if (BATCH) {
    test(`all ${routes.length} routes${suffix}`, async ({ page, request }) => {
      test.setTimeout(180_000)
      ids ??= lookup(request)
      const values = await ids
      await prepare?.(page)
      const { problems } = watch(page)
      const failures: unknown[] = []
      for (const route of routes) {
        try {
          await test.step(`${route}${suffix}`, () => check(page, problems, route, values))
        } catch (error) {
          failures.push(error)
        }
      }
      console.log(`Checked ${routes.length} routes${suffix}; ${failures.length} failed.`)
      if (failures.length) throw failures[0]
    })
    return
  }

  for (const route of routes) {
    test(`${route}${suffix}`, async ({ page, request }) => {
      ids ??= lookup(request)
      const values = await ids
      await prepare?.(page)
      await check(page, watch(page).problems, route, values)
    })
  }
}

test.describe('every page opens', () => {
  test('the route list was read', () => {
    expect(ROUTES.length).toBeGreaterThan(30)
  })

  walk(ROUTES)
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
  walk(DARK_ROUTES, ' in dark', (page) => page.addInitScript(() => {
    try { localStorage.setItem('sp-theme', 'dark') } catch { /* fine */ }
  }), async (page, url) => {
    // The theme really applied: the app ground is the dark base, not white.
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
    expect(bg, `body ground in ${url}`).not.toBe('rgb(255, 255, 255)')
  })
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
  walk(ROUTES, ' in Russian', async (page) => {
    // Keep the Russian setting local to this page. Playwright routing turns
    // off HTTP caching, so for a batch intercept only the preference fetch.
    if (!BATCH) {
      await page.route('**/api/prefs', (r) => (r.request().method() === 'GET'
        ? r.fulfill({ json: { prefs: { 'sp-lang': 'ru' } } })
        : r.fulfill({ json: { ok: true } })))
    }
    await page.addInitScript((cachedWalk) => {
      try { localStorage.setItem('sp-lang', 'ru') } catch { /* fine */ }
      if (!cachedWalk) return
      const fetchReal = window.fetch.bind(window)
      window.fetch = (input, init) => {
        const target = new URL(input instanceof Request ? input.url : String(input), location.href)
        if (target.origin !== location.origin || target.pathname !== '/api/prefs') return fetchReal(input, init)
        const method = init?.method ?? (input instanceof Request ? input.method : 'GET')
        return Promise.resolve(Response.json(method.toUpperCase() === 'GET' ? { prefs: { 'sp-lang': 'ru' } } : { ok: true }))
      }
    }, BATCH)
  }, async (page, url, route) => {
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
})
