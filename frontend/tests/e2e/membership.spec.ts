import { test as base, expect } from '@playwright/test'

// The direct API calls stand in for the operator's pages, so they carry the
// cookie the server hands a page of its own (server.OperatorCookie).
const test = base.extend({
  request: async ({ request }, use) => {
    await request.get('/api/health', { headers: { 'Sec-Fetch-Site': 'same-origin' } })
    await use(request)
  },
})

/**
 * An agent in a second project (tk_d1d25a4d step 2): the demo's cutover cell
 * (a chat with timed turns, so it has sessions) starts in beta-corp and joins
 * alpha-labs. The member project's Chats, Agents and Pins pages show it. One
 * test, joined and left inside it, so no other flow sees alpha-labs with a
 * member.
 */
const AGENT = 'cc-cutover01'
const NAME = 'cutover cell'
const HOME = 'beta-corp'
const MEMBER = 'alpha-labs'

test('membership: a chat joined to a second project shows on its Chats, Agents and Pins pages', async ({ page, request }) => {
  const main = page.getByRole('main')
  // Before the join the member project shows none of it (the sidebar lists
  // every project's chats, so each look is inside the page itself).
  await page.goto(`/project/${MEMBER}#agents`)
  await expect(main.getByText('agent-genesis').first()).toBeVisible()
  await expect(main.getByText(NAME)).toHaveCount(0)
  await page.goto(`/project/${MEMBER}#activity`)  // the Chats tab
  await expect(page.getByRole('list', { name: 'Chats' }).getByRole('button').first()).toBeVisible()
  await expect(page.getByRole('list', { name: 'Chats' }).getByText(NAME)).toHaveCount(0)

  const join = await request.post(`/api/agents/${AGENT}/membership`, { data: { op: 'join', project: MEMBER } })
  expect(join.status(), await join.text()).toBe(200)
  expect((await join.json()).members).toEqual([HOME, MEMBER])
  const pin = await request.post('/api/pins', { data: { chat_agent: AGENT, turn: 1, project: HOME } })
  expect(pin.status(), await pin.text()).toBe(201)
  try {
    // Agents: the member project's roster holds its card.
    await page.goto(`/project/${MEMBER}#agents`)
    await expect(main.getByText(NAME).first()).toBeVisible()

    // Chats: the member project's chat list holds it.
    await page.goto(`/project/${MEMBER}#activity`)
    await expect(page.getByRole('list', { name: 'Chats' }).getByText(NAME).first()).toBeVisible()

    // Calendar: its chats of 11 Aug show under alpha-labs, marked «from beta-corp».
    await page.goto(`/calendar#project=${MEMBER}&month=2026-08&sel=2026-08-11`)
    await expect(main.getByTestId('from-home').first()).toHaveText(`from ${HOME}`)

    // Timelapse: named beside the film, marked, not counted in it.
    await page.goto(`/timelapse#project=${MEMBER}`)
    await expect(main.getByTestId('timelapse-members')).toContainText(`from ${HOME}`)

    // Pins: the pin stamped beta-corp shows under alpha-labs too.
    await page.goto(`/pins#project=${MEMBER}`)
    await expect(main.getByText(NAME).first()).toBeVisible()
  } finally {
    await request.post('/api/pins/remove', { data: { target: `${AGENT}#1` } })
    const leave = await request.post(`/api/agents/${AGENT}/membership`, { data: { op: 'leave', project: MEMBER } })
    expect(leave.status(), await leave.text()).toBe(200)
  }
})
