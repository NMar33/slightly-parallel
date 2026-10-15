import { test, expect } from '@playwright/test'

/**
 * Slightly Parallel happy-path E2E — the "if this passes, the wheels are on" test.
 *
 * Runs hermetically against a copy of the shipped demo fixtures (see
 * playwright.config.ts) and targets the DEFAULT experience — the operator
 * Overview layout:
 *   - Overview:  data-testid="kpi-statline" and "fleet-cards" with one
 *                link per project (operator layout).
 *   - Project:   role="tablist" ("Project sections") with 10 tabs
 *                (Terminals hides itself in the hermetic default),
 *                the task numbers on the Overview tab, the kanban under
 *                Tasks.
 */

test.describe('Slightly Parallel happy path', () => {
  test('the home page boots with its state line, the day, and the projects', async ({ page }) => {
    await page.goto('/')

    // Loaded state, not the skeleton: the line on top, the day's agent time.
    await expect(page.getByTestId('overview-skeleton')).toHaveCount(0)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByTestId('home-day')).toBeVisible()

    // The fleet list renders with at least one project link.
    const fleet = page.getByTestId('fleet-cards')
    await expect(fleet).toBeVisible()
    await expect(fleet.getByRole('link').first()).toBeVisible()
  })

  test('clicking the first project navigates to the per-project drill', async ({
    page,
  }) => {
    await page.goto('/')

    const firstProject = page
      .getByTestId('fleet-cards')
      .getByRole('link')
      .first()
    await expect(firstProject).toBeVisible()
    await firstProject.click()

    // URL should now be /project/<code>
    await expect(page).toHaveURL(/\/project\/[^/]+$/)

    // Tab bar renders its sections (10 — the Terminals tab is hidden while
    // the terminal is disabled, the hermetic default); Overview is active.
    const tablist = page.getByRole('tablist', { name: 'Project sections' })
    await expect(tablist).toBeVisible()
    await expect(tablist.getByRole('tab')).toHaveCount(10)
    await expect(
      page.getByRole('tab', { name: 'Overview' }),
    ).toHaveAttribute('aria-selected', 'true')

    // The overview leads with the task numbers the backend sums.
    await expect(page.getByText('Open tasks')).toBeVisible()
  })

  test('Tasks tab reveals the kanban', async ({ page }) => {
    await page.goto('/')

    await page
      .getByTestId('fleet-cards')
      .getByRole('link')
      .first()
      .click()
    await expect(page).toHaveURL(/\/project\/[^/]+$/)

    await page.getByRole('tab', { name: 'Tasks' }).click()
    await expect(
      page.getByRole('tab', { name: 'Tasks' }),
    ).toHaveAttribute('aria-selected', 'true')
    // The board announces itself with its task count, whatever the view.
    await expect(page.getByText(/KANBAN/i).first()).toBeVisible()
    await expect(page.getByText(/\d+ tasks?/).first()).toBeVisible()
  })
})
