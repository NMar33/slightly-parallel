import { expect, test, type Page } from '@playwright/test'

const projects = { 'alpha-labs': '/tmp/alpha-labs' }
const sessions = [
  { id: 'one', label: 'Old shell', agent_kind: 'shell', attached: false, recent_output: false, running: false },
  { id: 'two', label: 'Active chat', agent_kind: 'claude', attached: true, recent_output: true, running: true },
  { id: 'three', label: 'Review chat', agent_kind: 'codex', attached: false, recent_output: false, running: false },
].map((item, index) => ({
  ...item, project: 'alpha-labs', agent_id: '', created: '2026-11-20T12:00:00',
  last_opened: null, last_activity: 1795176000 + index, activity: index, memory_bytes: (index + 1) * 1e8,
}))

async function atLimit(page: Page) {
  let limit = 3
  let scheme = 'sp-paper'
  let opened = false
  const slept: string[] = []
  const excerptReads: string[] = []
  const closes: unknown[] = []
  const closed = new Set<string>()
  const countsOnOpen: number[] = []
  const terminal = {
    id: 'requested', label: 'Requested terminal', kind: 'shell', role: 'shell', project: 'alpha-labs',
    cwd: '', command: '', agent_id: '', task_id: '', created: '2026-11-24T12:00:00',
    backend: 'plain', state: 'shell', last_output: 0, program: '',
  }
  const snapshot = () => {
    const live = sessions.filter(({ id }) => !slept.includes(id) && !closed.has(id))
    const kinds = {
      claude: { count: 0, measured: 0, bytes: 0 },
      codex: { count: 0, measured: 0, bytes: 0 },
      opencode: { count: 0, measured: 0, bytes: 0 },
      shell: { count: 0, measured: 0, bytes: 0 },
    }
    for (const row of live) {
      const kind = kinds[row.agent_kind as keyof typeof kinds]
      kind.count += 1
      kind.measured += 1
      kind.bytes += row.memory_bytes
    }
    return { count: live.length, limit, maximum: 256, sessions: live,
      memory: { total: 30e9, available: 16e9, used: live.reduce((sum, row) => sum + row.memory_bytes, 0), kinds } }
  }
  await page.route('**/api/terminal/state', (route) => route.fulfill({
    json: { enabled: true, supported: true, projects, token: 'test', tmux: false },
  }))
  await page.route('**/api/settings', async (route) => {
    if (route.request().method() === 'POST') {
      const values = route.request().postDataJSON().values
      limit = values['terminal.max_sessions'] ?? limit
      scheme = values['terminal.scheme'] ?? scheme
      return route.fulfill({ json: { saved: true } })
    }
    return route.fulfill({ json: { groups: [{ name: 'Terminal', settings: [
      { key: 'terminal.scheme', value: scheme }, { key: 'terminal.scheme_scope', value: 'window' },
    ] }], environment: [], file: '' } })
  })
  await page.route('**/api/terminal/sessions', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { sessions: opened ? [terminal] : [], counts: {} } })
    const data = snapshot()
    countsOnOpen.push(data.count)
    if (limit && data.count >= limit) return route.fulfill({ status: 429, json: {
      ...data, detail: 'The terminal limit was reached.',
      requested: { label: terminal.label, kind: 'shell', project: terminal.project, agent_kind: 'shell' },
    } })
    opened = true
    return route.fulfill({ status: 201, json: { session: terminal, existing: false } })
  })
  await page.route('**/api/terminal/limit', (route) => route.fulfill({ json: snapshot() }))
  await page.route('**/api/terminal/sessions/*/sleep', (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-2)!
    slept.push(id)
    return route.fulfill({ json: { session: { id, state: 'asleep' } } })
  })
  await page.route('**/api/terminal/sessions/*/close', (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-2)!
    closes.push(route.request().postDataJSON())
    closed.add(id)
    return route.fulfill({ json: { closed: id } })
  })
  await page.route('**/api/terminal/sessions/*/excerpts', (route) => {
    excerptReads.push(route.request().method())
    return route.fulfill({ json: { kind: 'messages', first: [{ text: 'First captured prompt' }], last: [] } })
  })
  return {
    countsOnOpen, slept, closes, excerptReads, limit: () => limit,
    async changeScheme(value: string) {
      scheme = value
      await page.evaluate(() => {
        const channel = new BroadcastChannel('sp-settings')
        channel.postMessage(null)
        channel.close()
      })
    },
  }
}

test('Aqua sleeps the three selected sessions before opening the same pending terminal', async ({ page }) => {
  const server = await atLimit(page)
  await page.goto('/term')
  await page.getByRole('button', { name: 'New terminal', exact: true }).first().click()

  const panel = page.locator('[data-aqua-frame]').getByRole('dialog', { name: 'Terminal limit' })
  await expect(panel.getByRole('heading', { name: '3 of 3 open' })).toBeVisible()
  await expect(panel.getByText(/Waiting to open Requested terminal/)).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Sleep', exact: true })).toBeDisabled()
  await panel.getByRole('button', { name: 'Select all visible' }).click()
  await expect(panel.getByText('3 selected')).toBeVisible()
  await panel.getByRole('button', { name: 'Sleep', exact: true }).click()

  await expect(panel).toBeHidden()
  await expect(page.locator('[data-window-tabs]').getByText('Requested terminal', { exact: true })).toBeVisible()
  expect([...server.slept].sort()).toEqual(['one', 'three', 'two'])
  expect(server.countsOnOpen).toEqual([3, 0])
})

test('the dashboard fallback can raise the limit and retry opening', async ({ page }) => {
  const server = await atLimit(page)
  await page.goto('/terminal')
  await page.getByRole('button', { name: /^alpha-labs/ }).click()
  const panel = page.getByRole('dialog', { name: 'Terminal limit' })
  await panel.getByRole('slider', { name: 'Terminal limit' }).press('End')
  await panel.getByRole('button', { name: 'Apply unlimited' }).click()
  await expect(panel).toBeHidden()
  expect(server.limit()).toBe(0)
  expect(server.countsOnOpen).toEqual([3, 3])
})

test('Aqua recolours the memory bar and confirms closing a running session', async ({ page }) => {
  const server = await atLimit(page)
  await page.goto('/term')
  await page.getByRole('button', { name: 'New terminal', exact: true }).first().click()
  const panel = page.getByRole('dialog', { name: 'Terminal limit' })
  const bar = panel.locator('[data-memory-kind="claude"]')
  await expect(bar).toHaveCSS('background-color', 'rgb(180, 49, 47)')
  await server.changeScheme('tokyo-night')
  await expect(bar).toHaveCSS('background-color', 'rgb(247, 118, 142)')
  expect(server.excerptReads).toEqual([])
  await panel.getByRole('button', { name: 'Excerpts for Active chat' }).click()
  await expect(panel.getByText('First captured prompt')).toBeVisible()
  expect(server.excerptReads).toEqual(['GET'])
  await panel.getByRole('checkbox', { name: 'Select Active chat' }).check()
  await panel.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(panel.getByText(/attached view or running program/)).toBeVisible()
  expect(server.closes).toEqual([])
  await panel.getByRole('button', { name: 'Confirm close' }).click()
  await expect(panel).toBeHidden()
  expect(server.closes).toEqual([{ actor: 'operator', from_limit: true, confirmed: true }])
})
