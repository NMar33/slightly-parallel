import path from 'node:path'
import { defineConfig } from '@playwright/test'
import base from '../playwright.config'

/**
 * The bench of the terminal window (`npm run bench` in desktop/, run by
 * run-bench.mjs): the same sandbox server, hidden display and window as the
 * end-to-end suite (../playwright.config.ts, ../global-setup.ts,
 * ../fixtures.ts), other files. A bench measures and never fails on a
 * number; it fails only when it cannot measure.
 */
const E2E = path.resolve(__dirname, '..')
const REPO = path.resolve(E2E, '..', '..')

export default defineConfig({
  ...base,
  testDir: __dirname,
  testMatch: /.*\.bench\.ts$/,
  globalSetup: [path.join(REPO, 'frontend', 'tests', 'e2e', 'global-setup.ts'), path.join(E2E, 'global-setup.ts')],
  globalTeardown: path.join(E2E, 'global-teardown.ts'),
  timeout: 60 * 60_000,
  retries: 0,
  failOnFlakyTests: false,
  reporter: 'list',
  outputDir: path.join(E2E, 'test-results', 'bench'),
})
