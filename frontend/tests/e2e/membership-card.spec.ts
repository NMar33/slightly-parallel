import { test as base, expect } from '@playwright/test'

// The direct API calls stand in for the operator's pages (their cookie).
const test = base.extend({
  request: async ({ request }, use) => {
    await request.get('/api/health', { headers: { 'Sec-Fetch-Site': 'same-origin' } })
    await use(request)
  },
})

/**
 * The agent card's projects (tk_d1d25a4d step 3): the operator joins a chat
 * to a second project from its card, and the second project's Chats page
 * lists it. The chat is pdr-framework-dev's lenses chat, which no other
 * flow joins; it leaves again at the end.
 */
const AGENT = 'mira-sztern-lenses-2608-09'
const NAME = 'mira-sztern-lenses'
const HOME = 'pdr-framework-dev'
const MEMBER = 'beta-corp'

test('the agent card joins a chat to a second project, whose Chats page then lists it', async ({ page, request }) => {
  await page.goto(`/agent/${AGENT}`)
  await page.getByRole('button', { name: `Edit ${NAME}` }).first().click()
  const dialog = page.getByRole('dialog')
  const chips = dialog.getByRole('list', { name: 'Member projects' })
  await expect(chips.getByRole('listitem')).toHaveText([`${HOME}· home`])
  try {
    await dialog.getByRole('combobox', { name: 'Join a project' }).selectOption(MEMBER)
    await expect(dialog.getByRole('status')).toContainText(`member of: ${HOME}, ${MEMBER}`)
    await expect(chips.getByRole('listitem')).toHaveCount(2)
    await expect(dialog.getByRole('button', { name: `Leave ${HOME}` })).toHaveCount(0)

    await page.goto(`/project/${MEMBER}#activity`)   // the Chats tab
    await expect(page.getByRole('list', { name: 'Chats' }).getByText(NAME).first()).toBeVisible()
  } finally {
    const leave = await request.post(`/api/agents/${AGENT}/membership`, { data: { op: 'leave', project: MEMBER } })
    expect([200, 409]).toContain(leave.status())
  }
})
