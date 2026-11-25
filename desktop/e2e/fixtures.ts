import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { _electron, expect, request as http, test as base, type APIRequestContext, type ElectronApplication, type Locator, type Page } from '@playwright/test'
import { recordPaneEvidence } from './pane-evidence'

/**
 * What every spec of the window's suite stands on:
 *
 * - `server` (once per run): the sandbox server of playwright.config.ts, an
 *   API client that is one of its own pages (Origin and the operator's
 *   cookie), and a project with a registered folder so a shell may open;
 * - `shell` (each test): every terminal of the last test closed, one fresh
 *   plain shell open — the terminal the window shows;
 * - `win` (each test, after `shell`) and `bare` (no terminal needed, so it
 *   runs on Windows too): the real Electron window of desktop/ on that server,
 *   with a user-data folder of its own (the single-instance lock would hand
 *   over to the operator's window otherwise) and links out of the app caught
 *   instead of opened in the browser.
 */

export const DESKTOP = path.resolve(__dirname, '..')
// eslint-disable-next-line @typescript-eslint/no-require-imports
export const ELECTRON: string = require('electron')
export const ROOT = process.env.SP_DESKTOP_E2E_ROOT!
export const URL_ = process.env.SP_DESKTOP_E2E_URL!
export const PROJECT = 'alpha-labs'
/** The sidebars' widths (frontend/src/features/aqua/app/model.ts LW, RW). */
export const LW = 236
export const RW = 340

export const HEADLESS = process.platform === 'linux' && process.env.SP_E2E_HEADLESS === '1'
/** The hidden display's name (global-setup.ts), '' on the real screen. */
export const HIDDEN = process.env.SP_E2E_WAYLAND ?? ''

/** The terminal runs on every system the window does: a Unix pty and /bin/sh
 *  on macOS and Linux; on Windows a ConPTY (pywinpty) and PowerShell, plain
 *  only (no tmux). */
export const TERMINAL = true
export const WINDOWS = process.platform === 'win32'
/** SP_E2E_KEEP=plain: every terminal a pty the server holds, as on Windows. */
export const KEEP_PLAIN = process.env.SP_E2E_KEEP === 'plain'
/** What the shell's prompt ends with: sh's `$`, PowerShell's `PS C:\…>`. */
export const PROMPT = WINDOWS ? '>' : '$'

/**
 * A command that prints `pre` + the value of `expr` + `post`, written so the
 * typed line never holds the printed one: `echo in-$((1+1))-x` in sh,
 * `echo "in-$(1+1)-x"` in PowerShell.
 */
export const echoCalc = (pre: string, expr: string, post = '') =>
  WINDOWS ? `echo "${pre}$(${expr})${post}"` : `echo ${pre}$((${expr}))${post}`

/** A command that prints a file, as fast as the shell can. */
export const printFile = (file: string) =>
  WINDOWS ? `[Console]::Out.Write([IO.File]::ReadAllText('${file.replace(/'/g, "''")}'))` : `cat '${file}'`

export function launchArgs(userData: string): string[] {
  return [
    DESKTOP,
    // Ubuntu 24.04 lets no unprivileged process start Chromium's sandbox
    // (AppArmor), and the e2e copy of Electron has no setuid helper.
    ...(process.platform === 'linux' ? ['--no-sandbox'] : []),
    `--user-data-dir=${userData}`,
    `--url=${URL_}`,
    // Linux, SP_E2E_HEADLESS=1: no window on the screen (Chromium's headless
    // Ozone platform, software drawing). The windows of a visible run take
    // the focus, and keys typed at the desktop meanwhile land in them.
    ...(HEADLESS ? ['--ozone-platform=headless'] : []),
    // The hidden GNOME display of global-setup.ts, when there is one.
    ...(HIDDEN ? ['--ozone-platform=wayland'] : []),
  ]
}

/** The environment a window starts in: the hidden display's, when there is one. */
export function launchEnv(): Record<string, string> {
  const env = { ...process.env } as Record<string, string>
  if (HIDDEN) Object.assign(env, { WAYLAND_DISPLAY: HIDDEN, DISPLAY: '', XDG_SESSION_TYPE: 'wayland' })
  return env
}

type Server = { url: string; api: APIRequestContext; dir: string }
type Shell = { id: string; label: string; backend: string }
type Win = { app: ElectronApplication; page: Page; userData: string }

async function withWindow(use: (w: Win) => Promise<void>) {
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-desktop-e2e-profile-'))
  const app = await _electron.launch({ executablePath: ELECTRON, args: launchArgs(userData), env: launchEnv(), timeout: 30_000 })
  const context = app.context()
  const pageErrors: string[] = []
  const watchErrors = (page: Page) => { page.on('pageerror', (error) => pageErrors.push(error.stack ?? error.message)) }
  for (const page of context.pages()) watchErrors(page)
  context.on('page', watchErrors)
  try {
    await catchLinksOut(app)
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await use({ app, page, userData })
    expect(pageErrors, 'uncaught errors in Electron renderers').toEqual([])
    for (const window of context.pages()) {
      await expectTerminalAncestorsUnscrolled(window)
    }
  } finally {
    await app.close().catch(() => {})
    fs.rmSync(userData, { recursive: true, force: true })
  }
}

/** xterm can scroll inside its host. The layout outside that host must stay put. */
export async function expectTerminalAncestorsUnscrolled(page: Page) {
  const scrolled = await page.locator('.aqua-screen').evaluateAll((screens) => screens.flatMap((screen) => {
    const result: string[] = []
    for (let node = screen.parentElement; node; node = node.parentElement) {
      if (node.scrollTop !== 0) result.push(`${node.tagName.toLowerCase()}.${node.className}: scrollTop=${node.scrollTop}`)
    }
    return result
  }))
  expect(scrolled, 'scrolled ancestors outside the terminal').toEqual([])
}

/** Use before a raw pointer action at a fixed coordinate. Locator clicks already check the target. */
export async function expectClickTarget(target: Locator, point: { x: number; y: number }) {
  const actual = await target.evaluate((element, { x, y }) => {
    const hit = document.elementFromPoint(x, y)
    return element.contains(hit) ? null : hit?.outerHTML.slice(0, 160) ?? 'outside the viewport'
  }, point)
  expect(actual, `pointer at (${point.x}, ${point.y}) hits ${target}`).toBeNull()
}

export const test = base.extend<{ shell: Shell; win: Win; bare: Win; paneEvidence: void }, { server: Server }>({
  server: [async ({}, use) => {
    const token = fs.readFileSync(path.join(ROOT, 'data', 'operator.token'), 'utf-8').trim()
    const api = await http.newContext({
      baseURL: URL_,
      // The fixture is idle while Electron is in use. A lifecycle request
      // must not reuse a connection that uvicorn may be closing meanwhile.
      extraHTTPHeaders: { origin: URL_, cookie: `sp_operator_${new URL(URL_).port}=${token}`, connection: 'close' },
    })
    const dir = path.join(ROOT, 'work', 'shell')
    fs.mkdirSync(dir, { recursive: true })
    // The terminal opens only in a project with a registered folder; the
    // fixtures have none. A registry row, nothing written into the folder.
    const reg = await api.post('/api/setup/integrate', {
      data: {
        project_code: PROJECT, project_dir: dir,
        write_agents: false, write_claude_bridge: false, write_claude_hooks: false,
        write_opencode_plugin: false, write_codex_hooks: false, write_mcp: false,
      },
    })
    expect(reg.ok(), await reg.text()).toBeTruthy()
    try {
      await use({ url: URL_, api, dir })
      await closeAll(api)
    } finally {
      await api.dispose()
    }
  }, { scope: 'worker' }],

  shell: async ({ server }, use) => {
    test.skip(!TERMINAL, 'no terminal on this system')
    await test.step('Close terminals from the preceding test', () => closeAll(server.api), { timeout: 25_000 })
    const s = await test.step('Open a fresh shell', () => openShell(server.api, 'e2e-shell'), { timeout: 25_000 })
    // SP_E2E_KEEP=plain (playwright.config.ts) took: no tmux under the run.
    if (KEEP_PLAIN || WINDOWS) expect(s.backend, 'a plain terminal').toBe('plain')
    await use(s)
  },

  win: async ({ shell: _shell }, use) => { await withWindow(use) },
  bare: async ({ server: _server }, use) => { await withWindow(use) },
  paneEvidence: async ({ win, server, shell }, use, testInfo) => {
    const attach = await recordPaneEvidence(win.page, server.api, shell, testInfo)
    try {
      await use()
    } finally {
      await attach()
    }
  },
})
export { expect }

/** shell.openExternal records instead of opening the operator's browser. */
export async function catchLinksOut(app: ElectronApplication) {
  await app.evaluate(({ shell }) => {
    const g = globalThis as unknown as { __opened: string[] }
    g.__opened = []
    shell.openExternal = async (u: string) => { g.__opened.push(u) }
  })
}
export const linksOut = (app: ElectronApplication) =>
  app.evaluate(() => (globalThis as unknown as { __opened: string[] }).__opened)

export async function openShell(api: APIRequestContext, label: string): Promise<Shell> {
  const r = await api.post('/api/terminal/sessions', { data: { kind: 'shell', project: PROJECT, label, role: 'shell' } })
  expect(r.ok(), await r.text()).toBeTruthy()
  const s = (await r.json()).session as { id: string; label: string; backend: string }
  return { id: s.id, label: s.label, backend: s.backend }
}

export type Row = { id: string; label: string; state: string; asleep?: boolean; backend?: string }
export const sessionTab = (scope: Page | Locator, id: string) => scope.locator(`[data-tab="${id}"]`).getByRole('tab')

export async function sessions(api: APIRequestContext): Promise<Row[]> {
  const r = await api.get('/api/terminal/sessions')
  expect(r.ok(), await r.text()).toBeTruthy()
  return (await r.json()).sessions as Row[]
}

export async function closeAll(api: APIRequestContext) {
  for (const s of await sessions(api)) {
    const response = await api.post(`/api/terminal/sessions/${s.id}/close`, { data: { actor: 'operator' } })
    expect(response.ok(), `closing terminal ${s.id}: ${response.status()} ${await response.text()}`).toBeTruthy()
  }
}

/* ------------------------------------------------------------ the page */

/** The terminal's lines as the page draws them (xterm's DOM renderer). */
export const lines = (page: Page) =>
  page.locator('.aqua-screen .xterm-rows > div').evaluateAll((els) => els.map((e) => (e.textContent ?? '').replace(/ /g, ' ').trimEnd()))

/** Wait for a line that is exactly `text` — never the typed command echoed. */
export async function expectLine(page: Page, text: string | RegExp, timeout = 10_000) {
  await expect.poll(async () => (await lines(page)).some((l) => typeof text === 'string' ? l.trim() === text : text.test(l)),
    { timeout, message: `a terminal line ${text}` }).toBe(true)
}

export async function ready(page: Page) {
  await expect(page.locator('.aqua-screen .xterm-rows')).toContainText(PROMPT, { timeout: WINDOWS ? 40_000 : 20_000 })
}

/**
 * Headless Ozone (SP_E2E_HEADLESS=1) has a display of 1×1 px, and Chromium
 * opens the window at its minimum, 420×240: a terminal of 10 rows and about
 * 50 columns. A spec that prints a conversation drawn for a wider terminal,
 * or opens a tall menu, gives the window the size it opens at on a real
 * display (main.js: 1000×640) and waits for the terminal to take it.
 * Elsewhere it does nothing.
 */
export async function fullSize(app: ElectronApplication, page: Page) {
  if (!HEADLESS) return
  await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].setSize(1000, 640) })
  await expect.poll(() => page.evaluate(() => innerHeight), { message: 'the window at 1000×640' }).toBeGreaterThan(600)
  await expect.poll(() => page.evaluate(() => document.querySelectorAll('.aqua-screen .xterm-rows > div').length), { message: 'the terminal at the new size' }).toBeGreaterThan(20)
}

export async function typeLine(page: Page, text: string) {
  await page.getByRole('textbox', { name: 'Terminal input' }).focus()
  await page.keyboard.type(text)
  await page.keyboard.press('Enter')
}

/** The shell's own idea of its size: `stty size` (PowerShell: the console's window) → [rows, cols]. */
export async function ptySize(page: Page): Promise<[number, number]> {
  const mark = `sz${Math.random().toString(36).slice(2, 7)}`
  await typeLine(page, WINDOWS
    ? `echo "${mark}-$([Console]::WindowHeight)x$([Console]::WindowWidth)"`
    : `echo ${mark}-$(stty size | tr ' ' x)`)
  let got: [number, number] = [0, 0]
  await expect.poll(async () => {
    const l = (await lines(page)).find((x) => new RegExp(`^${mark}-\\d+x\\d+$`).test(x.trim()))
    if (l) { const [r, c] = l.trim().slice(mark.length + 1).split('x').map(Number); got = [r, c] }
    return !!l
  }).toBe(true)
  return got
}

/** The first window of the app (the one opened at start), as the main process sees it. */
export const mainBounds = (app: ElectronApplication) =>
  app.evaluate(({ BrowserWindow }) => {
    const w = BrowserWindow.getAllWindows().sort((a: { id: number }, b: { id: number }) => a.id - b.id)[0]
    return w.getBounds()
  })

/** The width of the terminal in the page, and of xterm's screen in it. */
export const termWidth = (page: Page) => page.evaluate(() => ({
  frame: Math.round(document.querySelector('.aqua-screen')!.getBoundingClientRect().width),
  screen: Math.round(document.querySelector('.aqua-screen .xterm-screen')!.getBoundingClientRect().width),
}))

/** Nothing covers the button: the point at its centre is the button itself. */
export async function uncovered(page: Page, selector: string): Promise<boolean> {
  return page.evaluate((sel) => {
    const b = document.querySelector<HTMLElement>(sel)
    if (!b) return false
    const r = b.getBoundingClientRect()
    if (r.width === 0 || r.right < 0 || r.left > window.innerWidth) return false
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)
    return !!hit && (hit === b || b.contains(hit))
  }, selector)
}
