import { spawn } from 'node:child_process'
import { test, expect, HEADLESS, HIDDEN, ELECTRON, echoCalc, launchArgs, launchEnv, linksOut, ready, typeLine, expectLine, TERMINAL } from './fixtures'

/**
 * The window itself: what it opens, what the page may ask of it, where it
 * may not go, and that it is one app.
 */

test.describe('window', () => {
  test('opens frameless on /term with the bridge and GPU compositing', async ({ bare }) => {
    const { app, page } = bare
    expect(new URL(page.url()).pathname).toBe('/term')

    const w = await app.evaluate(({ BrowserWindow }) => {
      const b = BrowserWindow.getAllWindows()[0]
      return { count: BrowserWindow.getAllWindows().length, bounds: b.getBounds(), content: b.getContentBounds(), menu: b.isMenuBarVisible() }
    })
    expect(w.count).toBe(1)
    // No frame: the window's bounds are its content's, no title bar or border.
    expect(w.content).toEqual(w.bounds)
    expect(w.menu).toBe(false)

    // The bridge, and nothing else of Electron or Node in the page.
    const seen = await page.evaluate(() => ({
      bridge: typeof (window as unknown as { spWindow?: { postMessage?: unknown } }).spWindow?.postMessage,
      require: typeof (window as unknown as { require?: unknown }).require,
      process: typeof (window as unknown as { process?: unknown }).process,
      ua: navigator.userAgent,
    }))
    expect(seen).toMatchObject({ bridge: 'function', require: 'undefined', process: 'undefined' })
    expect(seen.ua).toContain('SlightlyParallelWindow/1')

    const gpu = await app.evaluate(({ app: a }) => a.getGPUFeatureStatus())
    const where = await app.evaluate(() => `${process.env.XDG_SESSION_TYPE ?? '?'} WAYLAND_DISPLAY=${process.env.WAYLAND_DISPLAY ?? ''} DISPLAY=${process.env.DISPLAY ?? ''}`)
    console.log(`display: ${where}; gpu_compositing: ${gpu.gpu_compositing}`)
    test.info().annotations.push({ type: 'display', description: where })
    test.info().annotations.push({ type: 'gpu', description: JSON.stringify(gpu) })
    // A runner without a GPU (CI's Linux under Xvfb) says so with SP_E2E_NO_GPU=1;
    // a headless run draws in software.
    if (process.env.SP_E2E_NO_GPU !== '1' && !HEADLESS) expect(gpu.gpu_compositing, JSON.stringify(gpu)).toMatch(/^enabled/)
  })

  test('one terminal is mounted and takes typed input; the window is named after it', async ({ win, shell }) => {
    const { app, page } = win
    await ready(page)
    await expect(page.locator('.xterm')).toHaveCount(1)
    await typeLine(page, 'echo sp-e2e-ok')
    await expectLine(page, 'sp-e2e-ok')
    // The page names the window after the terminal in front (op: title).
    await expect.poll(() => app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getTitle())).toContain(shell.label)
  })

  test('a link to another site does not navigate the window; it goes to the browser', async ({ bare }) => {
    const { app, page } = bare
    const before = page.url()
    await page.evaluate(() => { location.href = 'https://example.com/away' })
    await page.evaluate(() => { window.open('https://example.org/popup', '_blank') })
    await expect.poll(() => linksOut(app)).toEqual(['https://example.com/away', 'https://example.org/popup'])
    expect(page.url()).toBe(before)
    expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)).toBe(1)
    // A scheme that is not the web is neither followed nor handed on.
    await page.evaluate(() => { location.href = 'file:///etc/hosts' })
    await page.waitForTimeout(500)
    expect(page.url()).toBe(before)
    expect(await linksOut(app)).toHaveLength(2)
  })

  test('a second start with the same profile opens no second app: the first one comes forward', async ({ bare }) => {
    const { app, userData } = bare
    await app.evaluate(({ app: a }) => {
      const g = globalThis as unknown as { __second: number }
      g.__second = 0
      a.on('second-instance', () => { g.__second++ })
    })
    const child = spawn(ELECTRON, launchArgs(userData), { stdio: 'ignore', env: launchEnv() })
    const code = await new Promise<number | null>((resolve, reject) => {
      const t = setTimeout(() => { child.kill(); reject(new Error('the second start did not quit within 20 s')) }, 20_000)
      child.on('exit', (c) => { clearTimeout(t); resolve(c) })
    })
    expect(code).toBe(0)
    await expect.poll(() => app.evaluate(() => (globalThis as unknown as { __second: number }).__second)).toBe(1)
    expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)).toBe(1)
  })

  test('detach: a chat detached into its own window opens a second window on the same server', async ({ win, shell }) => {
    const { app, page } = win
    await ready(page)
    const tab = page.getByRole('tab', { name: new RegExp(`^${shell.label}`) })
    await tab.click({ button: 'right' })
    const opened = app.waitForEvent('window')
    await page.getByRole('menuitem', { name: 'Detach into its own window' }).click()
    const second = await opened
    await second.waitForLoadState('domcontentloaded')
    const u = new URL(second.url())
    expect(u.origin).toBe(new URL(page.url()).origin)
    expect(u.pathname).toBe('/term')
    expect(u.searchParams.get('detached')).toBe(shell.id)
    expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)).toBe(2)
    // The detached window is one chat: its terminal, no tab strip.
    await ready(second)
    await expect(second.getByRole('tablist', { name: 'Chats' })).toHaveCount(0)
    await typeLine(second, echoCalc('detached-', '40+2'))
    await expectLine(second, 'detached-42')
  })
})

test.describe('drag', () => {
  /*
   * Moving the window by its title row is the window system's: the row has
   * CSS app-region: drag and the system moves the window on a press there.
   * A synthetic page event never reaches that path, so this suite does not
   * drag. What it can check is that the regions are right: the row and the
   * folded tab strip drag, everything clickable in them does not.
   * (notes/2611-17-terminal-e2e.md: what would cover a real drag on each OS.)
   */
  test('the title row drags the window, its buttons do not; folded, the tab strip drags', async ({ win }) => {
    test.skip(!TERMINAL, 'the page shows the window only where the terminal runs')
    const { page } = win
    await ready(page)
    const regions = () => page.evaluate(() => {
      // Chromium's computed app-region, by either of its names.
      const r = (el: Element) => {
        const cs = getComputedStyle(el)
        return cs.getPropertyValue('app-region') || cs.getPropertyValue('-webkit-app-region') || ''
      }
      const fold = document.querySelector('[aria-label^="Fold the title row"], [aria-label^="Unfold the title row"]')!
      const row = fold.closest('.aq-app-drag') ?? fold.parentElement!.parentElement!
      const tablist = document.querySelector('[role="tablist"][aria-label="Chats"]')!
      const strip = tablist.parentElement!
      return {
        row: r(row),
        rowButtons: [...row.querySelectorAll('button')].map((b) => `${b.getAttribute('aria-label')}=${r(b)}`),
        strip: r(strip),
        stripButtons: [...strip.querySelectorAll('button')].map((b) => `${b.getAttribute('aria-label')}=${r(b)}`),
        toggles: [...document.querySelectorAll('[data-toggle]')].map((b) => `${b.getAttribute('data-toggle')}=${r(b)}`),
      }
    })

    const open = await regions()
    expect(open.row).toBe('drag')
    expect(open.rowButtons.length).toBeGreaterThan(3)
    for (const b of open.rowButtons) expect(b).toMatch(/=no-drag$/)
    expect(open.strip).not.toBe('drag')
    expect(open.toggles).toEqual(['left=no-drag', 'right=no-drag'])

    await page.keyboard.press('Alt+KeyT')
    await expect(page.locator('[data-aqua-frame][data-folded]')).toHaveCount(1)
    const folded = await regions()
    expect(folded.row).toBe('drag')
    // Folded, the thin row is one button (a click unfolds it): no drag there.
    expect(folded.rowButtons).toEqual([expect.stringMatching(/^Unfold the title row.*=no-drag$/)])
    expect(folded.strip).toBe('drag')
    for (const b of folded.stripButtons) expect(b).toMatch(/=no-drag$/)
    expect(folded.toggles).toEqual(['left=no-drag', 'right=no-drag'])
  })

  test("the bridge's drag op moves the window with the pointer until the button is let go", async ({ bare }) => {
    // main.js's fallback for a press the page sees on the row (op: drag): the
    // window follows the pointer. A Wayland window cannot place itself, so
    // there it is not checked; the pointer is a stand-in set from the test.
    test.skip(process.platform === 'linux' && !HEADLESS && !!(HIDDEN || process.env.WAYLAND_DISPLAY), 'a Wayland window cannot move itself (run with SP_E2E_HEADLESS=1, or on X11)')
    const { app, page } = bare
    await app.evaluate(({ screen }) => {
      const g = globalThis as unknown as { __cursor: { x: number; y: number } }
      g.__cursor = { x: 300, y: 300 }
      screen.getCursorScreenPoint = () => ({ ...g.__cursor })
    })
    const pos = () => app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getPosition())
    const [x0, y0] = await pos()
    await page.evaluate(() => (window as unknown as { spWindow: { postMessage: (m: unknown) => void } }).spWindow.postMessage({ op: 'drag' }))
    await app.evaluate(() => { (globalThis as unknown as { __cursor: { x: number; y: number } }).__cursor = { x: 340, y: 325 } })
    await expect.poll(pos).toEqual([x0 + 40, y0 + 25])
    // Let go: the window stays where it is when the pointer moves on.
    await page.evaluate(() => window.dispatchEvent(new PointerEvent('pointerup')))
    await page.waitForTimeout(100)
    await app.evaluate(() => { (globalThis as unknown as { __cursor: { x: number; y: number } }).__cursor = { x: 500, y: 500 } })
    await page.waitForTimeout(200)
    expect(await pos()).toEqual([x0 + 40, y0 + 25])
  })
})
