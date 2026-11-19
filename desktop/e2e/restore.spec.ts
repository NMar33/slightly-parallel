import fs from 'node:fs'
import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { _electron, type APIRequestContext, type ElectronApplication, type Page } from '@playwright/test'
import { test, expect, ELECTRON, HEADLESS, HIDDEN, PROJECT, catchLinksOut, launchArgs, launchEnv, ready } from './fixtures'

/**
 * Windows after a restart (tk_f5b4a9d3): the windows besides the main one,
 * open when the app is closed, come back at its next start, as a browser
 * restores its session. desktop/main.js keeps them in windows.json in the
 * app's user-data folder; Settings › Terminal › On start decides at start.
 *
 * Each test has a user-data folder of its own and starts the app in it more
 * than once: the folder outlives a start, as the operator's does.
 */

/** Wayland: the desktop places windows, so only their size comes back. */
const WAYLAND = process.platform === 'linux' && !HEADLESS && !!(HIDDEN || process.env.WAYLAND_DISPLAY)

type Saved = { url: string; width: number; height: number; x?: number; y?: number }
type Shown = { id: number; url: string; size: number[]; pos: number[] }

/** Sizes match to the pixel, except on GNOME's Wayland, which rounds a
 *  window's size by a pixel or two (900×600 shows as 900×601). */
const SLACK = WAYLAND ? 2 : 0
const near = (got: number[], want: number[]) => got.length === want.length && got.every((v, i) => Math.abs(v - want[i]) <= SLACK)
/** Headless (SP_E2E_HEADLESS=1) has one display of 1×1 px: Chromium fits a
 *  new window into it (420×240, the minimum, at 0,0), so a restored window's
 *  size and place are checked only on a real display. */
const FITS = !HEADLESS
const sizeOf = (w: { width: number; height: number }) => [w.width, w.height]

const savedIn = (dir: string): Saved[] => {
  try { return (JSON.parse(fs.readFileSync(path.join(dir, 'windows.json'), 'utf-8')) as { windows: Saved[] }).windows } catch { return [] }
}

async function start(userData: string, origin?: string): Promise<{ app: ElectronApplication; page: Page }> {
  const args = launchArgs(userData).map((arg) => origin && arg.startsWith('--url=') ? `--url=${origin}` : arg)
  const app = await _electron.launch({ executablePath: ELECTRON, args, env: launchEnv(), timeout: 30_000 })
  await catchLinksOut(app)
  const page = await app.firstWindow()
  await page.waitForLoadState('domcontentloaded')
  return { app, page }
}

/** What the start decided (main.js sets it once the saved windows are dealt with). */
const decided = async (app: ElectronApplication) => {
  let got: { choice: string; saved: number; opened: number; asked: number } | null = null
  await expect.poll(async () => {
    got = await app.evaluate(() => (globalThis as unknown as { __spRestore?: typeof got }).__spRestore ?? null)
    return got !== null
  }, { timeout: 15_000, message: 'the start decided about the saved windows' }).toBe(true)
  return got!
}

/** Every window of the app, the main one (the first opened) first. */
const shown = (app: ElectronApplication): Promise<Shown[]> => app.evaluate(({ BrowserWindow }) =>
  BrowserWindow.getAllWindows().sort((a, b) => a.id - b.id)
    .map((w) => ({ id: w.id, url: w.webContents.getURL(), size: w.getSize(), pos: w.getPosition() })))

/** The page of the window whose address is `url`. */
async function pageAt(app: ElectronApplication, url: string): Promise<Page> {
  await expect.poll(() => app.windows().some((p) => p.url() === url), { message: `a window at ${url}` }).toBe(true)
  return app.windows().find((p) => p.url() === url)!
}

async function onStart(api: APIRequestContext, choice: 'restore' | 'ask' | 'main') {
  const r = await api.post('/api/settings', { data: { values: { 'terminal.restore_windows': choice } } })
  expect(r.ok(), await r.text()).toBeTruthy()
}

test.describe('windows after a restart', () => {
  let userData = ''
  const open: ElectronApplication[] = []
  test.beforeEach(() => { userData = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-desktop-e2e-restore-')) })
  test.afterEach(async ({ server }) => {
    for (const app of open.splice(0)) await app.close().catch(() => {})
    fs.rmSync(userData, { recursive: true, force: true })
    await onStart(server.api, 'restore')
  })
  const launch = async (origin?: string) => { const s = await start(userData, origin); open.push(s.app); return s }
  const quit = async (app: ElectronApplication) => { await app.close(); open.splice(open.indexOf(app), 1) }

  test('a detached chat and workspace come back after a quit with their addresses and sizes; one closed by hand does not', async ({ server, shell }) => {
    await onStart(server.api, 'restore')
    const { app, page } = await launch()
    await ready(page)
    const origin = new URL(page.url()).origin
    const chatUrl = `${origin}/term?detached=${shell.id}`
    const wsUrl = `${origin}/term?ws=${PROJECT}`

    // The chat from its tab's menu, the workspace by the page's own op.
    await page.getByRole('tab', { name: new RegExp(`^${shell.label}`) }).click({ button: 'right' })
    await page.getByRole('menuitem', { name: 'Detach into its own window' }).click()
    await pageAt(app, chatUrl)
    await page.evaluate((url) => (window as unknown as { spWindow: { postMessage: (m: unknown) => void } }).spWindow.postMessage({ op: 'detach', url }), wsUrl)
    // Both drawn, so the desktop's own first sizing is over before ours.
    await ready(await pageAt(app, chatUrl))
    await (await pageAt(app, wsUrl)).waitForLoadState('load')
    await new Promise((r) => setTimeout(r, 500))
    // Saved as each opened, before any quit.
    await expect.poll(() => savedIn(userData).map((w) => w.url)).toEqual([chatUrl, wsUrl])

    // Sizes (and, where a window may place itself, places) the operator gave them.
    const want = { [chatUrl]: { width: 733, height: 455, x: 140, y: 120 }, [wsUrl]: { width: 811, height: 522, x: 420, y: 260 } }
    await app.evaluate(({ BrowserWindow }, { want, place }) => {
      for (const w of BrowserWindow.getAllWindows()) {
        const b = want[w.webContents.getURL()]
        if (b) w.setBounds(place ? b : { width: b.width, height: b.height })
      }
    }, { want, place: !WAYLAND })
    // Moves and resizes are written a moment later (debounced), still before a quit.
    await expect.poll(async () => {
      const live = (await shown(app)).slice(1)
      const saved = savedIn(userData)
      return saved.length === 2 && live.length === 2 && saved.every((w, i) => near(sizeOf(w), sizeOf(want[w.url]))
        && near(sizeOf(w), live[i].size) && w.url === live[i].url)
    }, { message: 'the sizes given, saved' }).toBe(true)
    const placed = Object.fromEntries((await shown(app)).slice(1).map((w) => [w.url, w.pos]))

    await quit(app)
    const kept = savedIn(userData)
    expect(kept.map((w) => w.url)).toEqual([chatUrl, wsUrl])
    for (const w of kept) expect(near(sizeOf(w), sizeOf(want[w.url])), `${w.url} ${w.width}x${w.height}`).toBe(true)
    // Wayland keeps no place: the desktop decides it.
    if (WAYLAND) expect(kept.every((w) => w.x === undefined && w.y === undefined)).toBe(true)

    // Started again: the main window, then both, as they were.
    const again = await launch()
    expect(await decided(again.app)).toEqual({ choice: 'restore', saved: 2, opened: 2, asked: 0 })
    await pageAt(again.app, chatUrl)
    await pageAt(again.app, wsUrl)
    const back = await shown(again.app)
    expect(back.map((w) => w.url)).toEqual([again.page.url(), chatUrl, wsUrl])
    expect(new URL(back[0].url).search).toBe('')
    if (FITS) for (const [i, w] of back.slice(1).entries()) expect(near(w.size, sizeOf(kept[i])), `${w.url} ${w.size}`).toBe(true)
    if (FITS && !WAYLAND) expect(back.slice(1).map((w) => w.pos)).toEqual([placed[chatUrl], placed[wsUrl]])
    // The chat's window is its terminal again.
    await ready(await pageAt(again.app, chatUrl))

    // The operator closes the workspace's window himself: it is gone from the set.
    const wsPage = await pageAt(again.app, wsUrl)
    await wsPage.evaluate(() => (window as unknown as { spWindow: { postMessage: (m: unknown) => void } }).spWindow.postMessage({ op: 'close' }))
    await expect.poll(() => savedIn(userData).map((w) => w.url)).toEqual([chatUrl])
    await quit(again.app)

    const third = await launch()
    expect(await decided(third.app)).toEqual({ choice: 'restore', saved: 1, opened: 1, asked: 0 })
    await pageAt(third.app, chatUrl)
    expect((await shown(third.app)).map((w) => w.url)).toEqual([third.page.url(), chatUrl])
  })

  test('the main window closed closes the others and keeps them for next time', async ({ server, shell }) => {
    await onStart(server.api, 'restore')
    const { app, page } = await launch()
    const chatUrl = `${new URL(page.url()).origin}/term?detached=${shell.id}`
    await page.evaluate((url) => (window as unknown as { spWindow: { postMessage: (m: unknown) => void } }).spWindow.postMessage({ op: 'detach', url }), chatUrl)
    await pageAt(app, chatUrl)
    const closed = app.waitForEvent('close')
    await page.evaluate(() => (window as unknown as { spWindow: { postMessage: (m: unknown) => void } }).spWindow.postMessage({ op: 'close' }))
    await closed
    open.splice(open.indexOf(app), 1)
    expect(savedIn(userData).map((w) => w.url)).toEqual([chatUrl])
  })

  test('closing during startup preserves previous windows and a newly detached window', async () => {
    let requestWaiting = false
    let holdSettings = true
    const local = createServer((req, res) => {
      if (req.url === '/api/settings') {
        if (holdSettings) { requestWaiting = true; return }
        res.writeHead(200, { 'content-type': 'application/json' }).end('{}')
        return
      }
      res.writeHead(200, { 'content-type': 'text/html' }).end('<title>Restore test</title>')
    })
    await new Promise<void>((resolve) => local.listen(0, '127.0.0.1', resolve))
    try {
      const origin = `http://127.0.0.1:${(local.address() as AddressInfo).port}`
      const previous = [`${origin}/term?detached=old`, `${origin}/term?ws=old`]
      const fresh = `${origin}/term?detached=new`
      fs.writeFileSync(path.join(userData, 'windows.json'), JSON.stringify({ version: 1,
        windows: previous.map((url) => ({ url, width: 700, height: 500 })) }))
      const { app, page } = await launch(origin)
      await expect.poll(() => requestWaiting).toBe(true)
      await page.evaluate((url) => (window as unknown as { spWindow: { postMessage: (m: unknown) => void } }).spWindow.postMessage({ op: 'detach', url }), fresh)
      await pageAt(app, fresh)
      const expected = [...previous, fresh].sort()
      await expect.poll(() => savedIn(userData).map((w) => w.url).sort()).toEqual(expected)
      await quit(app)
      expect(savedIn(userData).map((w) => w.url).sort()).toEqual(expected)

      holdSettings = false
      const again = await launch(origin)
      expect(await decided(again.app)).toEqual({ choice: 'restore', saved: 3, opened: 3, asked: 0 })
      for (const url of [...previous, fresh]) await pageAt(again.app, url)
    } finally {
      local.closeAllConnections()
      local.close()
    }
  })

  test('«only the main window»: none come back, and the set is let go', async ({ server, shell }) => {
    const chatUrl = `${server.url}/term?detached=${shell.id}`
    const wsUrl = `${server.url}/term?ws=${PROJECT}`
    fs.writeFileSync(path.join(userData, 'windows.json'), JSON.stringify({ version: 1, windows: [
      { url: chatUrl, width: 700, height: 500 }, { url: wsUrl, width: 800, height: 520 },
    ] }))
    await onStart(server.api, 'main')
    const { app } = await launch()
    expect(await decided(app)).toEqual({ choice: 'main', saved: 2, opened: 0, asked: 0 })
    expect((await shown(app)).length).toBe(1)
    expect(savedIn(userData)).toEqual([])
  })

  test('«ask»: the main window asks; Yes opens them, a terminal that is gone included; No lets them go', async ({ server, shell }) => {
    const chatUrl = `${server.url}/term?detached=${shell.id}`
    const goneUrl = `${server.url}/term?detached=t_gone_e2e`
    const seed = () => fs.writeFileSync(path.join(userData, 'windows.json'), JSON.stringify({ version: 1, windows: [
      { url: chatUrl, width: 700, height: 500 }, { url: goneUrl, width: 640, height: 420 },
    ] }))
    await onStart(server.api, 'ask')

    seed()
    const yes = await launch()
    expect(await decided(yes.app)).toEqual({ choice: 'ask', saved: 2, opened: 0, asked: 2 })
    const ask = yes.page.getByRole('alertdialog', { name: 'Windows of last time' })
    await expect(ask).toContainText('Open the 2 windows that were open last time?')
    // Nothing opens before the answer, and the set waits in the file.
    expect((await shown(yes.app)).length).toBe(1)
    expect(savedIn(userData).map((w) => w.url)).toEqual([chatUrl, goneUrl])
    await ask.getByRole('button', { name: 'Yes' }).click()
    await expect(ask).toHaveCount(0)
    await ready(await pageAt(yes.app, chatUrl))
    // A window whose terminal no longer exists opens and says so; closing it forgets it.
    const gone = await pageAt(yes.app, goneUrl)
    await expect(gone.getByText('This terminal is gone.')).toBeVisible()
    const both = (await shown(yes.app)).slice(1)
    expect(both.map((w) => w.url)).toEqual([chatUrl, goneUrl])
    if (FITS) expect(near(both[0].size, [700, 500]) && near(both[1].size, [640, 420]), JSON.stringify(both)).toBe(true)
    await quit(yes.app)
    expect(savedIn(userData).map((w) => w.url)).toEqual([chatUrl, goneUrl])

    seed()
    const no = await launch()
    expect(await decided(no.app)).toEqual({ choice: 'ask', saved: 2, opened: 0, asked: 2 })
    const ask2 = no.page.getByRole('alertdialog', { name: 'Windows of last time' })
    await ask2.getByRole('button', { name: 'No' }).click()
    await expect(ask2).toHaveCount(0)
    await expect.poll(() => savedIn(userData)).toEqual([])
    expect((await shown(no.app)).length).toBe(1)
  })
})
