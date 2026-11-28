import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { _electron, type Page } from '@playwright/test'
import {
  ELECTRON, PROJECT, ROOT, expect, expectLine, fullSize, launchArgs, launchEnv, linksOut,
  openShell, printFile, ready, sessionTab, test, typeLine,
} from './fixtures'
import { offsetNow, runTrusted } from './scrollProbe'

const dashboardButton = (page: Page) => page.getByRole('button', { name: 'Dashboard', exact: true })
const terminalButton = (page: Page) => page.getByRole('button', { name: 'Terminal', exact: true })
const dashboard = (page: Page) => page.frameLocator('iframe[title="SP dashboard"]')
const frameReady = (page: Page) => dashboard(page).getByRole('navigation', { name: 'Views', exact: true })
  .getByRole('link', { name: 'Kanban', exact: true })
const terminalInput = (page: Page) => page.locator('.aqua-screen').getByRole('textbox', { name: 'Terminal input' })

async function firstFrameSwitch(page: Page, name: 'Dashboard' | 'Terminal') {
  const button = name === 'Dashboard' ? dashboardButton(page) : terminalButton(page)
  const nextFrame = await button.evaluateHandle((button) => ({ visible: new Promise<boolean>((resolve) => {
    button.addEventListener('click', () => {
      requestAnimationFrame(() => {
        const surface = button.getAttribute('aria-label') === 'Terminal'
          ? document.querySelector('iframe[title="SP dashboard"]')
          : document.querySelector('.aqua-screen')
        resolve(!!surface && getComputedStyle(surface).visibility === 'visible')
      })
    }, { once: true })
  }) }))
  try {
    await button.click()
    expect(await nextFrame.evaluate((sample) => sample.visible)).toBe(true)
  } finally {
    await nextFrame.dispose()
  }
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

test('the dashboard and terminal switch on the next frame and keep both documents and their state', async ({ win, shell, server }) => {
  const { page, app } = win
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
  await expect(frameReady(page)).toHaveCount(1)
  const dashboardDocument = await frameReady(page).evaluate(() => performance.timeOrigin)

  await firstFrameSwitch(page, 'Dashboard')
  await frameReady(page).click()
  await expect(dashboard(page).getByRole('heading', { name: 'Kanban' })).toBeVisible()
  const board = dashboard(page).getByRole('navigation', { name: 'Boards' })
  const boardChoice = board.getByRole('button', { name: 'beta-corp', exact: true })
  await boardChoice.click()
  const filter = dashboard(page).locator('[title^="Show only important tasks"]')
  await filter.click()
  await expect(filter).toHaveAttribute('aria-pressed', 'true')
  const scroller = dashboard(page).locator('main .overflow-x-auto').first()
  const scrollLeft = await scroller.evaluate((el) => { el.scrollLeft = 100; return el.scrollLeft })
  expect(scrollLeft).toBeGreaterThan(0)
  const route = await board.evaluate(() => location.href)

  await firstFrameSwitch(page, 'Terminal')
  await expect(sessionTab(page, other.id)).toHaveAttribute('aria-selected', 'true')
  await expect(sessionTab(page, shell.id)).toHaveAttribute('aria-selected', 'false')
  await expect.poll(() => offsetNow(page)).toBe(terminalScroll)
  expect(await page.evaluate(() => performance.timeOrigin)).toBe(terminalDocument)
  await expect.poll(() => originalInput.evaluate((el) => document.activeElement === el)).toBe(true)
  await page.keyboard.press('Enter')
  await expectLine(page, 'held-input-across-dashboard')

  await firstFrameSwitch(page, 'Dashboard')
  await expect(filter).toHaveAttribute('aria-pressed', 'true')
  expect(await scroller.evaluate((el) => el.scrollLeft)).toBe(scrollLeft)
  expect(await board.evaluate(() => location.href)).toBe(route)
  expect(await board.evaluate(() => performance.timeOrigin)).toBe(dashboardDocument)
  expect(app.windows()).toHaveLength(1)
})

test('record links enter the dashboard and external terminal links still reach the browser', async ({ win, server }) => {
  const { app, page } = win
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
  await expect(frameReady(page)).toHaveCount(1)
  const dashboardDocument = await frameReady(page).evaluate(() => performance.timeOrigin)

  await terminalLink(page, task)
  await page.getByRole('button', { name: 'Open on the board' }).click()
  await expect(terminalButton(page)).toBeVisible()
  await expect(dashboard(page).getByRole('dialog', { name: 'Edit task' }).getByLabel('Title', { exact: true })).toHaveValue('Dashboard link task')
  expect(await frameReady(page).evaluate(() => location.pathname + location.search)).toContain('/kanban?task=' + task)

  await terminalButton(page).click()
  await terminalLink(page, note)
  await page.getByRole('button', { name: 'Open on the Notes page' }).click()
  await expect(terminalButton(page)).toBeVisible()
  expect(await frameReady(page).evaluate(() => location.pathname + location.search)).toContain('/notes?note=' + note)
  await expect(dashboard(page).getByText('UI test note from cli', { exact: true }).first()).toBeVisible()
  expect(await frameReady(page).evaluate(() => performance.timeOrigin)).toBe(dashboardDocument)

  await terminalButton(page).click()
  await terminalLink(page, external, 'right')
  await page.getByRole('menuitem', { name: 'Open', exact: true }).click()
  await expect.poll(() => linksOut(app)).toEqual([external])
  await expect(dashboardButton(page)).toBeVisible()
  expect(app.windows()).toHaveLength(1)
})

test('the main window reopens on the side last shown', async ({ server: _server }) => {
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-dashboard-window-profile-'))
  const start = () => _electron.launch({ executablePath: ELECTRON, args: launchArgs(userData), env: launchEnv(), timeout: 30_000 })
  let app: Awaited<ReturnType<typeof start>> | undefined
  try {
    app = await start()
    const initial = await app.firstWindow()
    await dashboardButton(initial).click()
    await expect(terminalButton(initial)).toBeVisible()
    await app.close()
    app = await start()
    const restored = await app.firstWindow()
    await expect(terminalButton(restored)).toBeVisible()
    await expect(frameReady(restored)).toBeVisible()
    await terminalButton(restored).click()
    await expect(dashboardButton(restored)).toBeVisible()
    await app.close()
    app = await start()
    await expect(dashboardButton(await app.firstWindow())).toBeVisible()
  } finally {
    await app?.close().catch(() => {})
    fs.rmSync(userData, { recursive: true, force: true })
  }
})

test('dashboard links cannot navigate the frame off the server or access the native bridge', async ({ bare }) => {
  const { app, page } = bare
  await dashboardButton(page).click()
  const link = frameReady(page)
  await expect(link).toBeVisible()
  const before = await link.evaluate(() => ({ url: location.href, bridge: 'spWindow' in window }))
  expect(before.bridge).toBe(false)
  const external = 'https://example.invalid/from-the-dashboard'
  await link.evaluate((_link, url) => { location.href = url }, external)
  await expect.poll(() => linksOut(app)).toEqual([external])
  expect(await link.evaluate(() => location.href)).toBe(before.url)
  expect(app.windows()).toHaveLength(1)
})
