import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/**
 * Playwright config — happy-path E2E for Slightly Parallel.
 *
 * Hermetic by design: boots its OWN backend on :8129 on a fresh COPY of
 * the shipped demo fixtures, so results never depend on the operator's
 * live data root or an already-running dev server — and a run never
 * writes into the fixtures themselves (preferences, tmux configs, the
 * monitor's record all land in the copy). The backend serves
 * frontend/dist; tests/e2e/global-setup.ts rebuilds it when src/ is newer.
 *
 * Base URL uses 127.0.0.1 not localhost — Node's happy-eyeballs sometimes
 * resolves ::1 before 127.0.0.1, and FastAPI listens on IPv4 by default.
 */

const REPO = path.resolve(__dirname, '..')
// SP_E2E_PORT lets two runs share a machine (each boots its own server).
const E2E_PORT = Number(process.env.SP_E2E_PORT) || 8129

/**
 * The data root the test server runs on: a throwaway copy of fixtures/.
 * The config is loaded by the runner AND by every worker; only the runner
 * starts the server, so only the runner makes the copy.
 */
function dataRoot(): string {
  if (process.env.TEST_WORKER_INDEX !== undefined || process.env.SP_E2E_URL) return ''
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-e2e-'))
  fs.cpSync(path.join(REPO, 'fixtures'), root, { recursive: true })
  process.on('exit', () => { try { fs.rmSync(root, { recursive: true, force: true }) } catch { /* the OS cleans tmp */ } })
  return root
}
const DATA_ROOT = dataRoot()
// The backend's own interpreter, where each system puts it.
const PYTHON = process.platform === 'win32'
  ? path.join(REPO, 'backend', '.venv', 'Scripts', 'python.exe')
  : path.join(REPO, 'backend', '.venv', 'bin', 'python')

export default defineConfig({
  testDir: './tests/e2e',
  // Builds frontend/dist first when the source is newer: the backend serves it.
  globalSetup: './tests/e2e/global-setup.ts',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.SP_E2E_URL ?? `http://127.0.0.1:${E2E_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // Offline-safe — fixtures come from the local backend, no external calls
    // permitted. If a test hits the network, it's a bug — fail loud.
    launchOptions: { args: ['--disable-background-networking'] },
  },
  projects: [
    // The terminal flow turns the global terminal.enabled setting on while it
    // runs, which the other flows must not see: it runs by itself, after them.
    { name: 'chromium', use: { ...devices['Desktop Chrome'] }, grepInvert: /terminal:/ },
    { name: 'terminal', use: { ...devices['Desktop Chrome'] }, grep: /terminal:/, dependencies: ['chromium'] },
  ],
  webServer: process.env.SP_E2E_URL
    ? undefined
    : {
        command: `"${PYTHON}" -m uvicorn backend.server:app --host 127.0.0.1 --port ${E2E_PORT}`,
        cwd: `${REPO}/backend`,
        env: {
          ...process.env,
          SP_DATA_ROOT: DATA_ROOT,
          SP_PORT: String(E2E_PORT),
          // No skills into the home folder, no monitor writing into the fixtures.
          SP_SANDBOX: '1',
          // The terminal flow opens a shell: a plain one, never the
          // operator's interactive bash (its rc may prompt for sudo).
          SHELL: '/bin/sh',
        },
        url: `http://127.0.0.1:${E2E_PORT}/api/health`,
        reuseExistingServer: false,
        timeout: 60_000,
        stdout: 'pipe',
        stderr: 'pipe',
      },
})
