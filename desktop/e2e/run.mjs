// `npm run e2e` in desktop/: the window's end-to-end suite, run by the
// frontend's Playwright (frontend/node_modules), so desktop/ needs no second
// copy of it. NODE_PATH lets the specs import @playwright/test from there.
// Arguments pass through: npm run e2e -- -g "sidebars" --repeat-each 2
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const modules = path.resolve(here, '..', '..', 'frontend', 'node_modules')
const cli = path.join(modules, '@playwright', 'test', 'cli.js')
if (!fs.existsSync(cli)) {
  console.error(`no Playwright at ${cli}: run npm install in frontend/ first`)
  process.exit(2)
}
const r = spawnSync(process.execPath, [cli, 'test', '-c', path.join(here, 'playwright.config.ts'), ...process.argv.slice(2)], {
  stdio: 'inherit',
  env: { ...process.env, NODE_PATH: [modules, process.env.NODE_PATH].filter(Boolean).join(path.delimiter) },
})
process.exit(r.status ?? 1)
