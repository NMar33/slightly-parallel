import fs from 'node:fs'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { _electron, type ElectronApplication, type Page } from '@playwright/test'
import {
  ELECTRON, PROJECT, ROOT, catchLinksOut, expect, expectLine, fullSize, launchArgs, launchEnv, mainTerminalPage, linksOut,
  openShell, printFile, ready, sessionTab, test, typeLine,
} from './fixtures'
import { offsetNow, runTrusted } from './scrollProbe'

const dashboardButton = (page: Page) => page.getByRole('button', { name: 'Dashboard', exact: true })
const terminalButton = (page: Page) => page.getByRole('button', { name: 'Terminal', exact: true })
const kanbanLink = (page: Page) => page.getByRole('navigation', { name: 'Views', exact: true })
  .getByRole('link', { name: 'Kanban', exact: true })
const terminalInput = (page: Page) => page.locator('.aqua-screen').getByRole('textbox', { name: 'Terminal input' })
const windowCount = (app: ElectronApplication) => app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)

async function dashboardPage(app: ElectronApplication, terminal: Page) {
  let dashboard: Page | undefined
  await expect.poll(() => {
    dashboard = app.context().pages().find((page) => page !== terminal && page.url() !== 'about:blank')
    return !!dashboard
  }).toBe(true)
  return dashboard!
}

async function switchSide(app: ElectronApplication, page: Page, name: 'Dashboard' | 'Terminal') {
  await (name === 'Dashboard' ? dashboardButton(page) : terminalButton(page)).click()
  await expect.poll(() => app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0]?.contentView.children.some((view) => (
      'webContents' in view && view.webContents !== BrowserWindow.getAllWindows()[0]?.webContents && view.getVisible()
    )),
  )).toBe(name === 'Dashboard')
}

async function terminalLink(page: Page, text: string, button: 'left' | 'right' = 'left') {
  const y = await page.locator('.aqua-screen .xterm-rows > div').evaluateAll((rows, text) => {
    const row = rows.find((el) => el.textContent?.trim() === text)
    if (!row) throw new Error('No terminal row for ' + text)
    const box = row.getBoundingClientRect()
    return box.y + box.height / 2
  }, text)
  const cell = await page.locator('.aqua-screen .xterm-screen').boundingBox()
  if (!cell) throw new Error('No xterm screen')
  const x = cell.x + 16
  await page.mouse.move(x, y - 20)
  await page.mouse.move(x, y)
  await page.mouse.click(x, y, { button })
}

test('the dashboard and terminal switch without reloading and keep both documents and their state', async ({ win, shell, server }) => {
  const { page, app } = win
  const dash = await dashboardPage(app, page)
  await expect(dashboardButton(page)).toBeVisible()
  await ready(page)
  await fullSize(app, page)
  const other = await openShell(server.api, 'dashboard-test-second')
  await expect(sessionTab(page, other.id)).toBeVisible()
  await sessionTab(page, other.id).click()
  const file = path.join(ROOT, 'work', 'dashboard-scroll.txt')
  fs.writeFileSync(file, Array.from({ length: 240 }, (_, i) => 'L' + String(i + 1).padStart(5, '0') + ' terminal history').join('\n') + '\n')
  await typeLine(page, printFile(file))
  await expectLine(page, 'L00240 terminal history')
  await terminalInput(page).focus()
  const originalInput = await terminalInput(page).elementHandle()
  await page.keyboard.type('echo held-input-across-dashboard')
  await runTrusted(page, [-600], 25)
  const terminalScroll = await offsetNow(page)
  expect(terminalScroll).not.toBeNull()
  expect(terminalScroll!).toBeLessThan(220 * 25)
  const terminalDocument = await page.evaluate(() => performance.timeOrigin)
  await expect(kanbanLink(dash)).toHaveCount(1)
  const dashboardDocument = await kanbanLink(dash).evaluate(() => performance.timeOrigin)

  await switchSide(app, page, 'Dashboard')
  await kanbanLink(dash).click()
  await expect(dash.getByRole('heading', { name: 'Kanban' })).toBeVisible()
  const board = dash.getByRole('navigation', { name: 'Boards' })
  const boardChoice = board.getByRole('button', { name: 'beta-corp', exact: true })
  await boardChoice.click()
  const filter = dash.locator('[title^="Show only important tasks"]')
  await filter.click()
  await expect(filter).toHaveAttribute('aria-pressed', 'true')
  const scroller = dash.locator('main .overflow-x-auto').first()
  const scrollLeft = await scroller.evaluate((el) => { el.scrollLeft = 100; return el.scrollLeft })
  expect(scrollLeft).toBeGreaterThan(0)
  const route = await board.evaluate(() => location.href)

  await switchSide(app, page, 'Terminal')
  await expect(sessionTab(page, other.id)).toHaveAttribute('aria-selected', 'true')
  await expect(sessionTab(page, shell.id)).toHaveAttribute('aria-selected', 'false')
  await expect.poll(() => offsetNow(page)).toBe(terminalScroll)
  expect(await page.evaluate(() => performance.timeOrigin)).toBe(terminalDocument)
  await expect.poll(() => originalInput.evaluate((el) => document.activeElement === el)).toBe(true)
  await page.keyboard.press('Enter')
  await expectLine(page, 'held-input-across-dashboard')

  await switchSide(app, page, 'Dashboard')
  await expect(filter).toHaveAttribute('aria-pressed', 'true')
  expect(await scroller.evaluate((el) => el.scrollLeft)).toBe(scrollLeft)
  expect(await board.evaluate(() => location.href)).toBe(route)
  expect(await board.evaluate(() => performance.timeOrigin)).toBe(dashboardDocument)
  expect(await windowCount(app)).toBe(1)
})

test('record links enter the dashboard and external terminal links still reach the browser', async ({ win, server }) => {
  const { app, page } = win
  const dash = await dashboardPage(app, page)
  await expect(dashboardButton(page)).toBeVisible()
  await ready(page)
  await fullSize(app, page)
  const made = await server.api.post('/api/tasks', {
    data: { project: PROJECT, title: 'Dashboard link task', status: 'todo', actor: 'operator' },
  })
  expect(made.ok(), await made.text()).toBeTruthy()
  const task: string = (await made.json()).metadata.id
  const note = 'nt_8ce63585'
  const external = 'https://example.invalid/dashboard-link'
  const file = path.join(ROOT, 'work', 'dashboard-links.txt')
  fs.writeFileSync(file, [task, note, external, 'dashboard links printed', ''].join('\n'))
  await typeLine(page, printFile(file))
  await expectLine(page, 'dashboard links printed')
  await expect(kanbanLink(dash)).toHaveCount(1)
  const dashboardDocument = await kanbanLink(dash).evaluate(() => performance.timeOrigin)

  await terminalLink(page, task)
  await page.getByRole('button', { name: 'Open on the board' }).click()
  await expect(terminalButton(page)).toBeVisible()
  await expect(dash.getByRole('dialog', { name: 'Edit task' }).getByLabel('Title', { exact: true })).toHaveValue('Dashboard link task')
  expect(await kanbanLink(dash).evaluate(() => location.pathname + location.search)).toContain('/kanban?task=' + task)

  await terminalButton(page).click()
  await terminalLink(page, note)
  await page.getByRole('button', { name: 'Open on the Notes page' }).click()
  await expect(terminalButton(page)).toBeVisible()
  expect(await kanbanLink(dash).evaluate(() => location.pathname + location.search)).toContain('/notes?note=' + note)
  await expect(dash.getByText('UI test note from cli', { exact: true }).first()).toBeVisible()
  expect(await kanbanLink(dash).evaluate(() => performance.timeOrigin)).toBe(dashboardDocument)

  await terminalButton(page).click()
  await terminalLink(page, external, 'right')
  await page.getByRole('menuitem', { name: 'Open', exact: true }).click()
  await expect.poll(() => linksOut(app)).toEqual([external])
  await expect(dashboardButton(page)).toBeVisible()
  expect(await windowCount(app)).toBe(1)
})

test('the main window reopens on the side last shown', async ({ server: _server }) => {
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-dashboard-window-profile-'))
  const start = () => _electron.launch({ executablePath: ELECTRON, args: launchArgs(userData), env: launchEnv(), timeout: 30_000 })
  let app: Awaited<ReturnType<typeof start>> | undefined
  try {
    app = await start()
    const initial = await mainTerminalPage(app)
    await dashboardButton(initial).click()
    await expect(terminalButton(initial)).toBeVisible()
    await app.close()
    app = await start()
    const restored = await mainTerminalPage(app)
    await expect(terminalButton(restored)).toBeVisible()
    await expect(kanbanLink(await dashboardPage(app, restored))).toBeVisible()
    await terminalButton(restored).click()
    await expect(dashboardButton(restored)).toBeVisible()
    await app.close()
    app = await start()
    await expect(dashboardButton(await mainTerminalPage(app))).toBeVisible()
  } finally {
    await app?.close().catch(() => {})
    fs.rmSync(userData, { recursive: true, force: true })
  }
})

test('the dashboard cannot access the terminal document or the native bridge', async ({ bare }) => {
  const { app, page } = bare
  const dash = await dashboardPage(app, page)
  await dashboardButton(page).click()
  const link = kanbanLink(dash)
  await expect(link).toBeVisible()
  expect(await link.evaluate(() => 'spWindow' in window)).toBe(false)
  expect(await link.evaluate(() => ({
    parentIsSelf: window.parent === window,
    topIsSelf: window.top === window,
    opener: window.opener === null,
    parentBridge: 'spWindow' in window.parent,
    topBridge: !!window.top && 'spWindow' in window.top,
    terminalDocument: !!window.parent.document.querySelector('[data-aqua-frame]'),
  }))).toEqual({
    parentIsSelf: true, topIsSelf: true, opener: true,
    parentBridge: false, topBridge: false, terminalDocument: false,
  })
  expect(await windowCount(app)).toBe(1)
})

test('native navigation keeps cross-origin form bodies out of both views', async ({ bare }) => {
  const { app, page } = bare
  const dash = await dashboardPage(app, page)
  const requests: string[] = []
  for (const [index, source] of [page, dash].entries()) {
    const destination = 'https://example.invalid/native-post-' + index
    await app.context().route(destination, async (route) => {
      requests.push(route.request().method())
      await route.fulfill({ status: 200, body: 'navigation probe' })
    })
    const before = source.url()
    await source.evaluate((action) => {
      const form = document.createElement('form')
      form.method = 'POST'
      form.action = action
      document.body.append(form)
      form.submit()
    }, destination)
    await expect.poll(() => linksOut(app)).toContain(destination)
    expect(source.url()).toBe(before)
  }
  expect(requests).toEqual([])
})

test('native navigation handles meta refresh in both views', async ({ bare }) => {
  const { app, page } = bare
  const dash = await dashboardPage(app, page)
  for (const [index, source] of [page, dash].entries()) {
    const before = source.url()
    const destination = 'https://example.invalid/native-refresh-' + index
    await app.context().route(destination, (route) => route.fulfill({ status: 200, body: 'navigation probe' }))
    await source.evaluate((url) => {
      const meta = document.createElement('meta')
      meta.httpEquiv = 'refresh'
      meta.content = '0; url=' + url
      document.head.append(meta)
    }, destination)
    await expect.poll(() => linksOut(app)).toContain(destination)
    expect(source.url()).toBe(before)
  }
})

test('native navigation rejects script, data and file URLs', async ({ bare }) => {
  const { app, page } = bare
  const dash = await dashboardPage(app, page)
  const file = path.join(ROOT, 'work', 'navigation-probe.html')
  fs.writeFileSync(file, '<title>Local navigation probe</title>')
  const fileUrl = pathToFileURL(file).href
  for (const source of [page, dash]) {
    const before = source.url()
    const result = await source.evaluate(() => new Promise<string>((resolve) => {
      const attribute = 'data-script-link-probe'
      const observer = new MutationObserver(() => {
        if (document.documentElement.hasAttribute(attribute)) resolve('script ran')
      })
      observer.observe(document.documentElement, { attributes: true, attributeFilter: [attribute] })
      document.addEventListener('securitypolicyviolation', (event) => {
        if (event.effectiveDirective.startsWith('script-src')) resolve('script blocked')
      }, { once: true })
      const link = document.createElement('a')
      link.href = 'javascript:void(document.documentElement.setAttribute("data-script-link-probe","ran"))'
      document.body.append(link)
      link.click()
      setTimeout(() => resolve('no result'), 1500)
    }))
    expect(result).toBe('script blocked')
    for (const url of ['data:text/html,Navigation%20probe', fileUrl]) {
      await source.evaluate((target) => { window.open(target, '_blank', 'noopener'); location.assign(target) }, url)
      expect(source.url()).toBe(before)
    }
  }
  expect(await linksOut(app)).toEqual([])
  expect(await windowCount(app)).toBe(1)
})

async function listen(server: Server) {
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  return 'http://127.0.0.1:' + (server.address() as AddressInfo).port
}

test('native navigation checks each redirect in both views and a same-origin popup', async () => {
  const requests: string[] = []
  const foreignServer = createServer((req, res) => { requests.push(req.url ?? ''); res.end('navigation probe') })
  const foreign = await listen(foreignServer)
  const hops: string[] = []
  const appServer = createServer((req, res) => {
    const match = /^\/chain\/(\d+)\/(first|second)$/.exec(req.url ?? '')
    if (match) {
      hops.push(req.url!)
      res.writeHead(match[2] === 'first' ? 302 : 307, {
        location: match[2] === 'first' ? '/chain/' + match[1] + '/second' : foreign + '/target/' + match[1],
      }).end()
      return
    }
    res.writeHead(200, { 'content-type': 'text/html' }).end('<title>Navigation test</title>')
  })
  const origin = await listen(appServer)
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-native-navigation-'))
  let app: ElectronApplication | undefined
  try {
    const args = launchArgs(userData).map((arg) => arg.startsWith('--url=') ? '--url=' + origin : arg)
    app = await _electron.launch({ executablePath: ELECTRON, args, env: launchEnv(), timeout: 30_000 })
    await catchLinksOut(app)
    const page = await mainTerminalPage(app)
    const dash = await dashboardPage(app, page)
    for (const [index, source] of [page, dash, page].entries()) {
      const before = source.url()
      await source.evaluate(({ target, popup }) => {
        if (popup) window.open(target, '_blank', 'noopener')
        else location.assign(target)
      }, { target: origin + '/chain/' + index + '/first', popup: index === 2 })
      await expect.poll(() => linksOut(app!)).toContain(foreign + '/target/' + index)
      expect(source.url()).toBe(before)
    }
    expect(hops).toEqual([0, 1, 2].flatMap((i) => ['/chain/' + i + '/first', '/chain/' + i + '/second']))
    expect(requests).toEqual([])
    await expect.poll(() => windowCount(app!)).toBe(1)
  } finally {
    await app?.close().catch(() => {})
    appServer.close()
    foreignServer.close()
    fs.rmSync(userData, { recursive: true, force: true })
  }
})
