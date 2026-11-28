import { execFile } from 'node:child_process'
import fs from 'node:fs'
import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { promisify } from 'node:util'
import { _electron, type Page } from '@playwright/test'
import { createServer as createViteServer } from 'vite'
import { DESKTOP, ELECTRON, expect, launchArgs, launchEnv, mainTerminalPage, test, URL_, WINDOWS } from './fixtures'

const run = promisify(execFile)
const repo = path.dirname(DESKTOP)
const python = path.join(repo, 'backend', '.venv', WINDOWS ? 'Scripts/python.exe' : 'bin/python')

// Let Playwright own the Electron process, using the real launcher's arguments.
const captureWindowCommand = `
import json
import sp
import sys
sp.read_env = lambda: {}
sp.detached = lambda argv, log: print("WINDOW_ARGS=" + json.dumps(argv)) or 0
sp.cmd_window(sys.argv[1:])
`

test('sp window boots on the configured Vite origin with React refresh and the native dashboard', async ({}) => {
  test.setTimeout(90_000)
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-electron-dev-'))
  const vite = await createViteServer({
    root: path.join(repo, 'frontend'),
    cacheDir: path.join(tmp, 'vite'),
    server: { proxy: { '/api': { target: URL_ }, '/ws': { target: URL_.replace(/^http/, 'ws') } } },
  })
  try {
    const probe = createServer()
    await new Promise<void>((resolve) => probe.listen(0, '127.0.0.1', resolve))
    const port = (probe.address() as AddressInfo).port
    await new Promise<void>((resolve) => probe.close(() => resolve()))
    await vite.listen(port)
    const vitePort = (vite.httpServer!.address() as AddressInfo).port
    const dev = `http://127.0.0.1:${vitePort}`
    // The backend keeps its API on its own port and redirects document requests to Vite.
    let redirectOrigin = dev
    const backend = createServer((req, res) => {
      if (req.url?.startsWith('/api/')) {
        res.setHeader('Content-Type', 'application/json')
        res.end('{"enabled":true}')
      } else {
        res.writeHead(307, { Location: redirectOrigin + req.url })
        res.end()
      }
    })
    await new Promise<void>((resolve) => backend.listen(0, '127.0.0.1', resolve))
    try {
      const backendPort = (backend.address() as AddressInfo).port
      const env = { ...launchEnv(), HOST: '127.0.0.1', SP_PORT: String(backendPort), VITE_PORT: String(vitePort) }
      const extra = launchArgs(path.join(tmp, 'profile')).slice(1).filter((arg) => !arg.startsWith('--url='))
      const windowArgs = async () => {
        const { stdout } = await run(python, ['-c', captureWindowCommand, ...extra], { cwd: repo, env, encoding: 'utf-8' })
        const output = stdout.split(/\r?\n/).find((line) => line.startsWith('WINDOW_ARGS='))!
        return (JSON.parse(output.slice('WINDOW_ARGS='.length)) as string[]).slice(1)
      }
      const args = await windowArgs()
      expect(args).toContain(`--url=${dev}`)
      redirectOrigin = URL_
      expect(await windowArgs()).toContain(`--url=http://127.0.0.1:${backendPort}`)
      const app = await _electron.launch({ executablePath: ELECTRON, args, env })
      try {
        const pageErrors: string[] = []
        const watchErrors = (page: Page) => page.on('pageerror', (error) => pageErrors.push(error.message))
        for (const page of app.context().pages()) watchErrors(page)
        app.context().on('page', watchErrors)
        const term = await mainTerminalPage(app)
        await expect(term).toHaveURL(`${dev}/term`)
        // Vite compiles the import graph on first use of a fresh cache.
        const dashboardButton = term.getByRole('button', { name: 'Dashboard', exact: true })
        await expect.poll(async () => pageErrors[0] ?? await dashboardButton.isVisible(), { timeout: 30_000 }).toBe(true)
        expect(await term.evaluate(() => typeof Reflect.get(window, 'spWindow')?.postMessage)).toBe('function')
        expect(await term.evaluate(() => typeof Reflect.get(window, '$RefreshReg$'))).toBe('function')
        await dashboardButton.click()
        const findDashboard = () => app.context().pages().find((page) => page.url() === `${dev}/`)
        await expect.poll(() => !!findDashboard()).toBe(true)
        const dashboard = findDashboard()!
        await expect(dashboard.getByRole('navigation', { name: 'Views' })).toBeVisible({ timeout: 30_000 })
        expect(pageErrors).toEqual([])
        expect(await dashboard.evaluate(() => typeof Reflect.get(window, 'spWindow'))).toBe('undefined')
      } finally {
        await app.close()
      }
    } finally {
      await new Promise<void>((resolve) => backend.close(() => resolve()))
    }
  } finally {
    await vite.close()
    fs.rmSync(tmp, { recursive: true, force: true })
  }
})
