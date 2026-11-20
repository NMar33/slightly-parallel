import { test, expect, URL_ } from './fixtures'
import { leaked } from '../../frontend/tests/e2e/cleanEnv'

/**
 * The suite runs from a clean environment (playwright.config.ts cleanEnv):
 * a run started in Slightly Parallel's own terminal, or by an agent, sees
 * none of that shell's SP_* variables, and neither do its server and
 * windows. Before, SP_UI_DEV sent every page of the sandbox server to the
 * operator's Vite, and SP_ENABLE_TERMINAL, SP_LOG_DIR and the agent's
 * session reached the server and the shells it starts.
 */

test('the run sees none of the shell it was started from', () => {
  expect(Object.keys(process.env).filter(leaked)).toEqual([])
})

test('the sandbox server serves its own pages', async ({ server }) => {
  // SP_UI_DEV in the server's environment answers every page with a redirect.
  const r = await server.api.get('/term', { maxRedirects: 0 })
  expect(r.status(), r.headers().location ?? '').toBe(200)
  expect(r.url()).toBe(`${URL_}/term`)
})
