import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'
import { cleanEnv } from './tests/e2e/cleanEnv'
import { buildIfStale } from './tests/e2e/buildDist'

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

// Before anything reads it: the run and its server see none of the
// developer's shell (SP_ENABLE_TERMINAL, SP_UI_DEV, an agent's session…).
cleanEnv()

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
  // The runner, once: the server is about to start and serves frontend/dist.
  buildIfStale(__dirname)
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-e2e-'))
  fs.cpSync(path.join(REPO, 'fixtures'), root, { recursive: true })
  addUsageGolden(root)
  addHelpers(root)
  addEntryPoint(root)
  process.on('exit', () => {
    for (const dir of [root, `${root}-backups`]) {
      try { fs.rmSync(dir, { recursive: true, force: true }) } catch { /* the OS cleans tmp */ }
    }
  })
  return root
}
/**
 * The Usage page's golden data (testdata/usage/root, the server's own test
 * data): its projects' chats and the plan limits go into the copy beside the
 * demo projects — never its root files, which would replace the demo's tasks.
 * The server's usage clock is then fixed to the moment the data describes
 * (SP_NOW, read by usagelib only), so tests/e2e/usage.spec.ts can check
 * the exact numbers.
 */
const USAGE_GOLDEN = path.join(REPO, 'testdata', 'usage', 'root')
export const USAGE_NOW = '2026-11-01T14:48:00'
function addUsageGolden(root: string): void {
  if (!fs.existsSync(USAGE_GOLDEN)) return
  const projects = path.join(USAGE_GOLDEN, 'projects')
  for (const p of fs.existsSync(projects) ? fs.readdirSync(projects) : []) {
    const to = path.join(root, 'projects', p)
    if (!fs.existsSync(to)) fs.cpSync(path.join(projects, p), to, { recursive: true })
  }
  const usage = path.join(USAGE_GOLDEN, '.usage')
  if (fs.existsSync(usage)) fs.cpSync(usage, path.join(root, '.usage'), { recursive: true })
}
/**
 * Two helper chats in alpha-labs (tests/e2e/flows.spec.ts, helpers:): a
 * codex exec the demo agent started, and one started by hand, with no
 * known parent. Written the way the hook writes them (helper in meta.json).
 */
function addHelpers(root: string): void {
  const chats = path.join(root, 'projects', 'alpha-labs', 'chats')
  const write = (id: string, parent: string, said: string, answer: string) => {
    fs.mkdirSync(path.join(chats, id), { recursive: true })
    fs.writeFileSync(path.join(chats, id, 'meta.json'), JSON.stringify({
      agent_id: id, agent_name: id, project: 'alpha-labs', created_date: '2608-05', last_active: '2026-08-05T17:10:00',
      message_count: 1, tool: 'codex', session_ref: id, capture: 'hooks',
      helper: true, helper_kind: 'codex-exec', helper_of: parent, ...(parent ? { helper_of_by: 'env' } : {}),
    }))
    fs.writeFileSync(path.join(chats, id, 'chat.md'),
      `# Chat log — ${id}\n\n## Turn 1 · 2026-08-05T17:05:00\n**User**: ${said}\n**Agent**: ${answer}\n`)
  }
  write('codex-e2e00001', 'agent-genesis-2608-01', 'You are a critic. Review the rate limit design. #entrypoint never kept', 'Two issues found.')
  write('codex-e2e00002', '', 'Started by hand: summarise the SDK notes', 'Summary written.')
}

/**
 * A chat in alpha-labs whose operator typed #entrypoint (tests/e2e/
 * entrypoints.spec.ts), the agent's question as the server records it
 * (entrypoint_asks.csv: one line, a new topic) and the operator's "1".
 * The topic is made when the agent sends the answer: the spec does that
 * first, as the agent's entrypoint_answer would. The fixtures have none.
 */
const ENTRY_AGENT = 'cc-e2eentry1'
const ENTRY_TOPIC = 'the release film and its studio'
function addEntryPoint(root: string): void {
  const id = ENTRY_AGENT
  const dir = path.join(root, 'projects', 'alpha-labs', 'chats', id)
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({
    agent_id: id, agent_name: 'release film', project: 'alpha-labs', created_date: '2608-06',
    last_active: '2608-06T10:06:00', message_count: 3, tool: 'claude-code', session_ref: '0e2e-entry-0001', capture: 'hooks',
  }))
  fs.writeFileSync(path.join(dir, 'chat.md'),
    `# Chat log — ${id}\n\n## Turn 1 · 2026-08-06T10:00:00\n**User**: render the release film\n**Agent**: Rendered.\n`
    + `\n## Turn 2 · 2026-08-06T10:05:00\n**User**: #entrypoint ${ENTRY_TOPIC}\n**Agent**: A new topic: «${ENTRY_TOPIC}»?\n`
    + `\n## Turn 3 · 2026-08-06T10:06:00\n**User**: 1\n**Agent**: Made.\n`)
  // backend keeplib.keep_id: the command's id.
  const cmd = 'ep_' + crypto.createHash('sha256').update(`entrypoint|alpha-labs|${id}|2`).digest('hex').slice(0, 8)
  const lines = JSON.stringify([{ n: 1, kind: 'new', name: ENTRY_TOPIC }]).replace(/"/g, '""')
  fs.writeFileSync(path.join(root, 'entrypoint_asks.csv'),
    'id,project,agent_id,command_turn,rev,offered_turn,offered_at,proposed,lines,state,answered_turn,answer,chosen,name,made,answered_at\n'
    + `${cmd},alpha-labs,${id},2,1,2,2026-08-06T10:05:30,${ENTRY_TOPIC},"${lines}",offered,,,,,,\n`)
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
  // In CI a failing test is tried twice more, so its traces show whether it
  // fails every time; a test that passes only on a retry still fails the run
  // (flaky: a timing assert or a clock that moved, never a fix by retry).
  retries: process.env.CI ? 2 : 0,
  failOnFlakyTests: !!process.env.CI,
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
    { name: 'chromium', use: { ...devices['Desktop Chrome'] }, grepInvert: /terminal:|restore:/ },
    { name: 'terminal', use: { ...devices['Desktop Chrome'] }, grep: /terminal:/, dependencies: ['chromium'] },
    // The restore flow replaces the whole data folder: alone, after all others.
    { name: 'restore', use: { ...devices['Desktop Chrome'] }, grep: /restore:/, dependencies: ['terminal'] },
  ],
  webServer: process.env.SP_E2E_URL
    ? undefined
    : {
        command: `"${PYTHON}" -m uvicorn backend.server:app --host 127.0.0.1 --port ${E2E_PORT}`,
        cwd: `${REPO}/backend`,
        env: {
          ...process.env,
          SP_DATA_ROOT: DATA_ROOT,
          // Beside the copy, removed with it (the restore flow takes backups).
          ...(DATA_ROOT ? { SP_BACKUP_ROOT: `${DATA_ROOT}-backups` } : {}),
          SP_PORT: String(E2E_PORT),
          // No skills into the home folder, no monitor writing into the fixtures.
          SP_SANDBOX: '1',
          // The usage clock of the golden data (see addUsageGolden).
          ...(fs.existsSync(USAGE_GOLDEN) ? { SP_NOW: USAGE_NOW } : {}),
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
