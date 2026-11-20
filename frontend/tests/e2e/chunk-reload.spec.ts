import { expect, test } from '@playwright/test'

for (const persistent of [false, true]) {
  test(persistent ? 'a missing page chunk gives up after one reload' : 'an open page reloads once when an old asset is gone', async ({ page }) => {
    const entry = await page.goto('/about')
    const link = page.getByRole('main').getByRole('link', { name: 'Guide', exact: true })
    await expect(link).toBeVisible()

    let chunkRequests = 0
    let documentRequests = 0
    page.on('request', (request) => {
      if (request.isNavigationRequest() && new URL(request.url()).pathname === '/guide') documentRequests++
    })
    await page.route('**/assets/GuidePage-*.js', (route) => {
      chunkRequests++
      return persistent || chunkRequests === 1 ? route.fulfill({ status: 404 }) : route.continue()
    })

    await link.click()
    if (persistent) {
      await expect(page.getByTestId('crash-screen')).toBeVisible()
    } else {
      await expect(page.getByRole('heading', { name: 'How Slightly Parallel works', exact: true })).toBeVisible()
      await expect(page.getByTestId('crash-screen')).toHaveCount(0)
    }
    expect(documentRequests).toBe(1)
    expect(chunkRequests).toBe(2)
    expect(entry?.headers()['cache-control']).toBe('no-cache')
  })
}
