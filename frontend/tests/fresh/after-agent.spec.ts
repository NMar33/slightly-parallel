import { test, expect } from '@playwright/test'

/**
 * After a real agent worked in the project (scripts/fresh_user/scenario.py):
 * the pages a person opens next show that work.
 */

const CODE = process.env.FRESH_CODE ?? 'calc'
const AGENT = process.env.FRESH_AGENT ?? ''
const TASK = process.env.FRESH_TASK ?? ''
// The first thing said in the chat: the pages show a chat by it.
const SAID = process.env.FRESH_SAID ?? ''

test('the agent has its page, with the chat', async ({ page }) => {
  expect(AGENT, 'FRESH_AGENT').not.toBe('')
  const thrown: string[] = []
  page.on('pageerror', (e) => thrown.push(String(e)))
  await page.goto(`/agent/${AGENT}`)
  await expect(page.getByText(AGENT).first()).toBeVisible()
  await expect(page.getByText(SAID, { exact: false }).first()).toBeVisible()
  expect(thrown).toEqual([])
})

test('the board shows the task', async ({ page }) => {
  test.skip(TASK === '', 'the agent made no task')
  await page.goto(`/project/${CODE}#tasks`)
  await expect(page.getByText(/unit tests|tests for calc/i).first()).toBeVisible()
})

test('the entry pages show the decision, the rule and the scan', async ({ page }) => {
  const thrown: string[] = []
  page.on('pageerror', (e) => thrown.push(String(e)))
  await page.goto('/decisions')
  await expect(page.getByText(/pytest/i).first()).toBeVisible()
  await page.goto('/rules')
  await expect(page.getByText(/single file/i).first()).toBeVisible()
  await page.goto('/scans')
  await expect(page.getByText(CODE).first()).toBeVisible()
  expect(thrown).toEqual([])
})

test('the overview and the chats list the project and the chat', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText(CODE).first()).toBeVisible()
  await page.goto('/chats')
  await expect(page.getByText(SAID, { exact: false }).first()).toBeVisible()
})
