import { defineConfig, devices } from '@playwright/test'

/**
 * The browser side of the fresh-user test (scripts/fresh_user/run.py).
 * It starts no server: the runner has one going from a fresh clone and
 * passes its address in SP_E2E_URL. The steps follow one another on
 * one server, so they run one at a time.
 */
export default defineConfig({
  testDir: './tests/fresh',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: process.env.SP_E2E_URL,
    screenshot: 'only-on-failure',
    launchOptions: { args: ['--disable-background-networking'] },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
