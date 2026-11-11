import { expect, test, type Page } from '@playwright/test'

/**
 * Entry points on the server's data (tk_51b87348): the topic kept from the
 * #entrypoint the config seeds in alpha-labs (playwright.config.ts
 * addEntryPoint). The operator names it, adds a way in and a message of
 * where it stopped, pauses it, lays the topics out as shelves, and reads it
 * on a phone and in the dark theme.
 */

const TOPIC = 'the release film and its studio'

function watch(page: Page): string[] {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(String(e)))
  return errors
}

test.describe('entry points', () => {
  test('the kept topic: named, a way in, where it stopped, paused, shelves, and back', async ({ page }) => {
    const errors = watch(page)
    await page.goto('/entrypoints?layout=list')
    await expect(page.getByRole('heading', { name: 'Entry points', level: 1 })).toBeVisible()
    const nav = page.getByRole('navigation', { name: 'Topics' })
    await nav.getByRole('button', { name: new RegExp(TOPIC) }).click()
    let card = page.getByTestId('ep-card')
    await expect(card.getByText('no name yet')).toBeVisible()
    // The chat the topic came from is at the bottom, with its resume command.
    const thread = card.getByRole('list', { name: 'Chats on this topic' })
    await expect(thread.getByText('came from here')).toBeVisible()
    await expect(card.getByTestId('ep-card-head').getByText('claude -r 0e2e-entry-0001')).toBeVisible()

    await card.getByRole('button', { name: 'Rename the topic' }).click()
    await card.getByRole('textbox', { name: "The topic's name" }).fill('The release film')
    await card.getByRole('button', { name: 'Save' }).click()
    card = page.getByRole('article', { name: 'The release film' })
    await expect(card.getByRole('heading', { name: 'The release film' })).toBeVisible()

    await card.getByRole('button', { name: 'Add a way in' }).click()
    const form = card.getByTestId('ep-way-form')
    await form.getByPlaceholder('What you call it').fill('Film studio')
    await form.getByPlaceholder('http://localhost:8120').fill('http://127.0.0.1:9/tour/custom')
    await form.getByPlaceholder('npm run dev').fill('python3 sp.py run')
    await form.getByRole('button', { name: 'Add the way in' }).click()
    const way = card.getByTestId('ep-way').filter({ hasText: 'Film studio' })
    await expect(way).toBeVisible()
    // Nothing listens on port 9: down, with its start command to copy.
    await expect(way.getByText('down')).toBeVisible()
    await expect(way.getByText('python3 sp.py run')).toBeVisible()

    await card.getByRole('textbox', { name: 'Where it stopped, in your words' }).fill('Rendered at 1920px; not uploaded.')
    await card.getByRole('button', { name: 'Add to the feed' }).click()
    await expect(card.getByText('Rendered at 1920px; not uploaded.')).toBeVisible()

    await card.getByRole('radiogroup', { name: 'State' }).getByRole('radio', { name: 'paused' }).click()
    await expect(card.getByRole('radiogroup', { name: 'State' }).getByRole('radio', { name: 'paused' })).toHaveAttribute('aria-checked', 'true')

    // The briefing as text carries what was just written.
    await card.getByRole('radiogroup', { name: 'Show' }).getByRole('radio', { name: 'as text' }).click()
    const text = card.getByTestId('ep-briefing-text')
    await expect(text).toContainText('# The release film')
    await expect(text).toContainText('start: `python3 sp.py run`')
    await expect(text).toContainText('Rendered at 1920px; not uploaded.')

    // Shelves: the same card under its tile; the layout is kept on reload.
    await page.getByRole('group', { name: 'Layout' }).getByRole('button', { name: 'Shelves of tiles' }).click()
    const tile = page.getByTestId('ep-tile').filter({ hasText: 'The release film' })
    await tile.getByRole('button', { name: /^The release film/, expanded: false }).click()
    await expect(page.getByRole('article', { name: 'The release film' })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('group', { name: 'Layout' }).getByRole('button', { name: 'Shelves of tiles' })).toHaveAttribute('aria-pressed', 'true')

    // Back as it was, for the other tests on this server.
    await page.goto('/entrypoints?layout=list')
    card = page.getByRole('article', { name: 'The release film' })
    await card.getByRole('radiogroup', { name: 'State' }).getByRole('radio', { name: 'active' }).click()
    await expect(page.getByTestId('crash-screen')).toHaveCount(0)
    expect(errors).toEqual([])
  })

  test('on a phone the topics are a row above the card, nothing wider than the screen; the dark theme draws', async ({ page }) => {
    const errors = watch(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.emulateMedia({ colorScheme: 'dark' })
    await page.goto('/entrypoints?layout=list')
    // The shell has no phone layout of its own: its sidebar is folded, as on a narrow window.
    await page.getByRole('button', { name: 'Collapse sidebar' }).click()
    await expect(page.getByTestId('ep-card')).toBeVisible()
    // The page's own parts (the shell's top bar is the shell's): no element
    // of the topic list, the card or the shelves past the screen's edge.
    const past = () => page.evaluate(() => {
      const roots = Array.from(document.querySelectorAll('[data-testid="ep-card"], nav[aria-label="Topics"], [data-testid="ep-shelf"]'))
      return roots.flatMap((root) => [root, ...Array.from(root.querySelectorAll('*'))])
        .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1 && !el.closest('[class*="overflow-x-auto"]'))
        .map((el) => `${el.tagName} ${(el.textContent ?? '').slice(0, 30)}`)
    })
    expect(await past()).toEqual([])
    await page.getByRole('group', { name: 'Layout' }).getByRole('button', { name: 'Shelves of tiles' }).click()
    await expect(page.getByTestId('ep-shelf').first()).toBeVisible()
    expect(await past()).toEqual([])
    await expect(page.getByTestId('crash-screen')).toHaveCount(0)
    expect(errors).toEqual([])
  })
})
