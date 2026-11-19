import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { tmuxSockets } from './sockets'
import { test, expect, ROOT, PROJECT, echoCalc, expectLine, lines, printFile, ready, sessions, typeLine } from './fixtures'

/**
 * The terminals in the window: tabs, sleep and wake, restore after the
 * tmux server is gone, and how fast output reaches the screen.
 */

test.describe('tabs', () => {
  test('"+" opens a shell in a new tab; tabs switch; closing one takes its tab away', async ({ win, shell, server }) => {
    const { page } = win
    await ready(page)
    const strip = page.getByRole('tablist', { name: 'Chats' })
    await expect(strip.getByRole('tab')).toHaveCount(1)

    // a plain click on "+": the shell, no list (tk_e7649e7c)
    await page.getByRole('button', { name: 'New terminal', exact: true }).click()
    await expect(strip.getByRole('tab')).toHaveCount(2)
    const first = strip.getByRole('tab', { name: new RegExp(`^${shell.label} `) })
    const second = strip.getByRole('tab', { name: new RegExp(`^${PROJECT} `) })
    await expect(second).toHaveAttribute('aria-selected', 'true')
    await expect(first).toHaveAttribute('aria-selected', 'false')
    await ready(page)
    await typeLine(page, echoCalc('in-', '1+1', '-second'))
    await expectLine(page, 'in-2-second')

    // One terminal in front; the tab left stays mounted, hidden (TermApp KEEP_SCREENS, tk_74f2d3ba).
    await first.click()
    await expect(first).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('.aqua-screen .xterm')).toHaveCount(1)
    await expect(page.locator('.aqua-kept .xterm')).toHaveCount(1)
    await ready(page)
    await expect.poll(async () => (await lines(page)).some((l) => l.trim() === 'in-2-second')).toBe(false)
    await page.keyboard.press('Alt+Digit2')
    await expect(second).toHaveAttribute('aria-selected', 'true')
    await expectLine(page, 'in-2-second')

    await second.click({ button: 'right' })
    await page.getByRole('menuitem', { name: 'Close the terminal' }).click()
    await expect(strip.getByRole('tab')).toHaveCount(1)
    await expect(first).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('.xterm')).toHaveCount(1)
    await expect.poll(async () => (await sessions(server.api)).map((s) => s.id)).toEqual([shell.id])
  })
})

test.describe('sleep and restore', () => {
  test('sleep from the tab menu stops the terminal and keeps its tab; Wake brings a live shell back', async ({ win, shell, server }) => {
    const { page } = win
    await ready(page)
    const tab = page.getByRole('tab', { name: new RegExp(`^${shell.label} `) })
    await tab.click({ button: 'right' })
    await page.getByRole('menuitem', { name: /^Sleep/ }).click()
    await expect(page.getByText(`${shell.label} is asleep: the agent is stopped, the chat is kept.`)).toBeVisible()
    await expect(page.locator('.xterm')).toHaveCount(0)
    await expect(tab).toBeVisible()
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id)?.asleep).toBe(true)

    await page.getByRole('button', { name: 'Wake' }).click()
    await ready(page)
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id)?.asleep).toBe(false)
    await typeLine(page, echoCalc('awake-', '2*3'))
    await expectLine(page, 'awake-6')
  })

  test('an ended tmux tab opens a shell only after the operator asks', async ({ win, shell, server }) => {
    const { page } = win
    test.skip(shell.backend !== 'tmux', 'tmux is required')
    await ready(page)
    // Leave one shell running so exiting this one does not stop the tmux server.
    const keep = await server.api.post('/api/terminal/sessions', { data: { kind: 'shell', project: PROJECT } })
    expect(keep.ok()).toBe(true)
    await typeLine(page, 'exit')
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id)?.state).toBe('ended')
    await page.getByRole('button', { name: 'Open a shell in it' }).click()
    await ready(page)
    await typeLine(page, echoCalc('shell-', '6*7'))
    await expectLine(page, 'shell-42')
  })

  test('after the tmux server is gone, the window offers Restore all and brings the terminal back', async ({ win, shell, server }) => {
    const { page } = win
    await ready(page)
    const row = (await sessions(server.api)).find((s) => s.id === shell.id)
    test.skip(row?.backend !== 'tmux', 'restore is for tmux terminals: tmux is not on this machine (never on Windows)')
    // The sandbox's own tmux server, found by its socket (never a bare `tmux kill-server`).
    const socks = tmuxSockets(process.env.SP_DESKTOP_E2E_TMUX!)
    expect(socks.length, 'no sandbox tmux socket').toBeGreaterThan(0)
    for (const s of socks) execFileSync('tmux', ['-S', s, 'kill-server'], { stdio: 'ignore' })
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id)?.state).toBe('ended')
    const need = await (await server.api.get('/api/terminal/restore')).json()
    expect(need.needed).toBe(1)

    // The card is a status with the terminal's name in it (its heading changes once restored).
    const card = page.getByRole('status').filter({ hasText: shell.label })
    await expect(card).toContainText('1 terminal ended without being put to sleep')
    await expect(card).toContainText(shell.label)
    await card.getByRole('button', { name: 'Restore all' }).click()
    await expect(card).toContainText('Restored')
    await expect(card.getByLabel('restored')).toHaveCount(1)
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id)?.state).not.toBe('ended')
    await card.getByRole('button', { name: 'Close' }).click()
    await ready(page)
    await typeLine(page, echoCalc('back-', '3+4'))
    await expectLine(page, 'back-7')
  })
})

test.describe('speed', () => {
  test('5 MB of coloured output reaches the screen in time and the page stays responsive', async ({ win }) => {
    const { page } = win
    await ready(page)
    // Lines of 16 colours, about 5 MB, in a file the sandbox shell cats.
    const file = path.join(ROOT, 'work', 'colours.txt')
    const row = Array.from({ length: 16 }, (_, i) => `\x1b[3${i % 8}${i >= 8 ? ';1' : ''}mcolour${String(i).padStart(2, '0')}\x1b[0m`).join(' ')
    const out: string[] = []
    let size = 0
    for (let n = 0; size < 5 * 1024 * 1024; n++) { const l = `${String(n).padStart(6, '0')} ${row}`; out.push(l); size += l.length + 1 }
    fs.writeFileSync(file, out.join('\n') + '\n')
    const mb = fs.statSync(file).size / 1024 / 1024

    // The page's longest stall while the output pours in: a timer that should tick every 50 ms.
    await page.evaluate(() => {
      const g = window as unknown as { __gap: number; __tick: number }
      g.__gap = 0; g.__tick = performance.now()
      setInterval(() => { const now = performance.now(); g.__gap = Math.max(g.__gap, now - g.__tick); g.__tick = now }, 50)
    })
    const started = Date.now()
    await typeLine(page, `${printFile(file)}; ${echoCalc('speed-', '6*7')}`)
    await expectLine(page, 'speed-42', 120_000)
    const secs = (Date.now() - started) / 1000
    const gap = await page.evaluate(() => (window as unknown as { __gap: number }).__gap)
    const rate = mb / secs
    console.log(`speed: ${mb.toFixed(1)} MB in ${secs.toFixed(2)} s = ${rate.toFixed(1)} MB/s; the page's longest stall ${Math.round(gap)} ms`)
    test.info().annotations.push({ type: 'speed', description: `${rate.toFixed(1)} MB/s, longest stall ${Math.round(gap)} ms` })
    // Loose on purpose: a guard against a fall to a crawl, not a benchmark.
    expect(secs, `${mb.toFixed(1)} MB took ${secs.toFixed(1)} s`).toBeLessThan(60)
    expect(gap, 'the page froze while the output came').toBeLessThan(2000)
    // Still answering: a key reaches the shell straight after.
    const t0 = Date.now()
    await typeLine(page, echoCalc('after-', '5+5'))
    await expectLine(page, 'after-10')
    expect(Date.now() - t0).toBeLessThan(5000)
    fs.rmSync(file, { force: true })
  })
})
