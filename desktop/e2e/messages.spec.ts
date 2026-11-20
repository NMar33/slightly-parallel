import fs from 'node:fs'
import path from 'node:path'
import type { APIRequestContext } from '@playwright/test'
import { expect, expectLine, KEEP_PLAIN, lines, PROJECT, ready, ROOT, test, typeLine, WINDOWS } from './fixtures'

/**
 * Messages between agents (tk_c1caab80): the server types a message into the
 * chat's live terminal, once, with its marker, when the agent's input line is
 * empty — and not over a line the operator is half-way through typing.
 *
 * The agent is a stand-in that draws Claude Code's input box and logs every
 * line it reads (backend/tests/fixtures/fake_agent_prompt.py), run in the
 * sandbox shell the window shows. The chat is tied to that terminal the way
 * the capture hook ties one: its meta names the terminal, and its breadcrumb
 * (written by the stand-in, as a hook under it would) holds the pane's shell.
 */

const FAKE = path.resolve(__dirname, '..', '..', 'backend', 'tests', 'fixtures', 'fake_agent_prompt.py')

function tieChat(agent: string, terminal: string) {
  const dir = path.join(ROOT, 'data', 'projects', PROJECT, 'chats', agent)
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({
    agent_id: agent, project: PROJECT, tool: 'claude-code', terminal,
    last_active: new Date().toISOString().slice(0, 19),
  }))
}

/** The command that starts the stand-in for `agent`, writing its breadcrumb. */
function fake(agent: string, log: string, typed = '') {
  const crumb = path.join(ROOT, 'data', '.sessions', 'e2e000000000', `${agent}.json`)
  return `SP_FAKE_CRUMB='${crumb}' SP_FAKE_AGENT=${agent} python3 '${FAKE}' '${log}' claude-code${typed ? ` '${typed}'` : ''}`
}

const read = (file: string) => (fs.existsSync(file) ? fs.readFileSync(file, 'utf-8') : '')

async function message(api: APIRequestContext, id: string) {
  const r = await api.get('/api/messages?limit=1000')
  expect(r.ok(), await r.text()).toBeTruthy()
  return ((await r.json()).messages as { id: string; delivered_via: string }[]).find((m) => m.id === id)!
}

async function send(api: APIRequestContext, to: string, text: string): Promise<string> {
  const r = await api.post('/api/messages', { data: { to, text } })
  expect(r.status(), await r.text()).toBe(201)
  return (await r.json()).message.id as string
}

test.describe('messages between agents', () => {
  test.skip(WINDOWS || KEEP_PLAIN, 'a message is typed into a tmux terminal only')

  test('a message lands in the terminal once, with its marker, when the input line is empty', async ({ server, shell, win }) => {
    const { page } = win
    await ready(page)
    const agent = `cc-e2em${Date.now().toString(16).slice(-4)}`
    const log = path.join(server.dir, `${agent}.log`)
    await typeLine(page, fake(agent, log))
    await expectLine(page, 'fake agent ready')
    tieChat(agent, shell.id)

    const id = await send(server.api, agent, 'look at the lock')
    const want = `[SP · from operator · ${id}] look at the lock`
    // At once, or on the server's next round once it sees the new link.
    await expect.poll(() => read(log), { timeout: 15_000 }).toBe(`${want}\n`)
    await expect.poll(async () => (await message(server.api, id)).delivered_via).toBe('terminal')
    // A narrow window wraps the fake agent's echo into a second visual row.
    await expect.poll(async () => {
      const rows = await lines(page)
      const echoed = `got: ${want}`
      return rows.some((row, i) => row === echoed
        || row + rows[i + 1] === echoed
        || row + ' ' + rows[i + 1] === echoed)
    }, { message: 'the complete reply is drawn in the terminal' }).toBe(true)
    // Two more rounds of the server's loop: still once.
    await page.waitForTimeout(7_000)
    expect(read(log)).toBe(`${want}\n`)
    expect((await lines(page)).filter((l) => l.includes(id))).toHaveLength(1)
  })

  test('a message is not typed over a half-typed line, and goes in once the line is empty', async ({ server, shell, win }) => {
    const { page } = win
    await ready(page)
    const agent = `cc-e2eh${Date.now().toString(16).slice(-4)}`
    const log = path.join(server.dir, `${agent}.log`)
    await typeLine(page, fake(agent, log, 'half typed'))
    await expectLine(page, 'fake agent ready')
    await expect.poll(async () => (await lines(page)).some((l) => l.includes('half typed'))).toBe(true)
    tieChat(agent, shell.id)

    const id = await send(server.api, agent, 'wait for the line')
    // Two rounds of the server's loop with the link known: nothing typed.
    await page.waitForTimeout(8_000)
    expect(read(log)).toBe('')
    expect((await message(server.api, id)).delivered_via).toBe('')
    expect((await lines(page)).some((l) => l.includes('half typed'))).toBe(true)

    // The operator clears the line: the next round types the message, once.
    fs.writeFileSync(`${log}.clear`, '')
    const want = `[SP · from operator · ${id}] wait for the line`
    await expect.poll(() => read(log), { timeout: 15_000 }).toBe(`${want}\n`)
    await page.waitForTimeout(4_000)
    expect(read(log)).toBe(`${want}\n`)
  })
})
