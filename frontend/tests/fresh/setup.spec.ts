import { test, expect } from '@playwright/test'

/**
 * Setup, as a new user does it in the browser: the server has just started
 * in a new data folder, with the example project in it; point it at
 * another empty data folder (which gets the example too), then integrate a
 * project. The folders come from the runner
 * (scripts/fresh_user/run.py), which checks the files afterwards.
 */

const DATA = process.env.FRESH_DATA ?? ''
const PROJECT = process.env.FRESH_PROJECT ?? ''
const CODE = process.env.FRESH_CODE ?? 'calc'
const TOOLS = (process.env.FRESH_TOOLS ?? 'claude-code').split(',')

test.describe.configure({ mode: 'serial' })

test('the runner passed its folders', () => {
  expect(DATA, 'FRESH_DATA').not.toBe('')
  expect(PROJECT, 'FRESH_PROJECT').not.toBe('')
})

test('step 1: choose the data folder', async ({ page }) => {
  // The example is played into the new folder within this step: the step's own time, not the default minute.
  test.setTimeout((Number(process.env.FRESH_EXAMPLE_SECONDS || 240) + 60) * 1000)
  await page.goto('/setup')
  await expect(page.getByText('Choose where Slightly Parallel keeps its records')).toBeVisible()
  // A new install holds the example project, and Setup says so.
  await expect(page.getByText('example project', { exact: false }).first()).toBeVisible()
  await page.getByLabel('Data root path').fill(DATA)
  await page.getByLabel('Data root path').press('Enter')
  const info = () => page.request.get('/api/setup/info').then((r) => r.json())
  if ((await info()).data_root !== DATA) {
    // Enter did not submit: use the card's button.
    await page.getByLabel('Data root path').locator('xpath=ancestor::*[.//button][1]').getByRole('button').first().click()
  }
  await expect.poll(async () => (await info()).data_root).toBe(DATA)
  // An empty folder gets the example project as well, played in the
  // background; the sidebar says so until it is there.
  await page.reload()
  await expect.poll(async () => {
    const e = (await info()).example
    return `${e.present}/${e.building}/${e.error}`
  }, { timeout: Number(process.env.FRESH_EXAMPLE_SECONDS || 240) * 1000, intervals: [2000] }).toBe('true/false/')
})

test('step 2: integrate the project', async ({ page }) => {
  await page.goto('/setup')
  await page.getByLabel('Project code').fill(CODE)
  await page.getByLabel('Project folder').fill(PROJECT)
  // Every tool's box is ticked by default; make sure of the ones this run drives.
  if (TOOLS.includes('opencode')) await page.getByLabel('OpenCode plugin: records OpenCode chats', { exact: false }).check()
  if (TOOLS.includes('codex')) await page.getByLabel('Codex hooks: record Codex chats', { exact: false }).check()
  await page.getByRole('button', { name: 'Preview' }).click()
  await expect(page.getByText('Preview, nothing written yet')).toBeVisible()
  await page.getByRole('button', { name: 'Integrate', exact: true }).click()
  await expect.poll(async () => {
    const d = await (await page.request.get('/api/setup/info')).json()
    return d.integrations.some((i: { project: string }) => i.project === CODE)
  }).toBe(true)
  // The page says what to do next.
  await expect(page.getByText('Start an agent', { exact: true })).toBeVisible()
})

test('the project has its page, empty and without a crash', async ({ page }) => {
  const thrown: string[] = []
  page.on('pageerror', (e) => thrown.push(String(e)))
  await page.goto(`/project/${CODE}`)
  await expect(page.getByRole('heading', { name: CODE }).first()).toBeVisible()
  for (const tab of ['tasks', 'activity', 'tools']) {
    await page.goto(`/project/${CODE}#${tab}`)
    await page.waitForTimeout(800)
  }
  await page.goto('/')
  await expect(page.getByText(CODE).first()).toBeVisible()
  expect(thrown).toEqual([])
})
