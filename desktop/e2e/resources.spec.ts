import { test, expect, ready } from './fixtures'

test('saved resource thresholds, gray mode and visibility reach the open terminal window', async ({ win, server }) => {
  const { app, page } = win
  // The two windows and Settings writes are real. A fixed sample keeps the
  // expected colors independent of the runner's load and available sensors.
  await page.route('**/api/monitor/now', (route) => route.fulfill({ json: {
    enabled: true, interval: 5,
    sample: { temp_c: 67.5, cpu: 75, mem_pct: 90, net_rx: 50 * 1024 ** 2 },
    spark: [],
  } }))
  await page.reload()
  await ready(page)
  const meter = page.getByRole('button', { name: 'System resources' })
  const bars = meter.locator('[data-resource-bar]')
  await expect(meter).toBeVisible()
  await expect(bars).toHaveCount(4)
  await expect(meter.locator('svg')).toHaveCount(4)
  const paint = () => bars.evaluateAll((fills) => fills.map((bar) => getComputedStyle(bar).backgroundColor))
  const [green, yellow, red, gray] = await meter.evaluate((element) => {
    const probe = document.createElement('span')
    element.append(probe)
    try {
      return ['--status-green', '--status-amber', '--status-red', '--text-secondary'].map((token) => {
        probe.style.backgroundColor = `var(${token})`
        return getComputedStyle(probe).backgroundColor
      })
    } finally { probe.remove() }
  })
  expect(new Set([green, yellow, red, gray]).size).toBe(4)
  await expect.poll(paint).toEqual([green, yellow, red, red])
  const heights = await bars.evaluateAll((fills) => fills.map((bar) => (bar as HTMLElement).style.height))
  expect(heights).toEqual(['67.5%', '75%', '90%', '100%'])
  await meter.hover()
  await expect(page.getByText('68 °C')).toBeVisible()
  await expect(page.getByText('Network', { exact: true })).toBeVisible()
  await page.locator('.aqua-screen').hover()
  await expect(page.getByText('68 °C')).toHaveCount(0)
  await meter.focus()
  await expect(page.getByText('68 °C')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByText('68 °C')).toHaveCount(0)

  const opened = app.waitForEvent('window')
  await page.evaluate(() => { window.open('/settings', '_blank') })
  const settings = await opened
  const visibility = settings.getByRole('checkbox', { name: 'Show resource indicators' })
  const colorful = settings.getByRole('checkbox', { name: 'Color resource bars by load' })
  const yellowAt = settings.getByRole('spinbutton', { name: 'Yellow resource threshold' })
  const redAt = settings.getByRole('spinbutton', { name: 'Red resource threshold' })
  const warning = settings.getByRole('checkbox', { name: 'Yellow resource level' })
  const saveButton = settings.getByRole('button', { name: /^Save \(\d+\)$/ })
  const save = async () => {
    const saved = settings.waitForResponse((response) => response.url().endsWith('/api/settings') && response.request().method() === 'POST')
    await saveButton.click()
    expect((await saved).status()).toBe(200)
  }

  try {
    await expect(visibility).toBeChecked()
    await expect(colorful).toBeChecked()
    await expect(yellowAt).toHaveValue('75')
    await expect(redAt).toHaveValue('90')
    await yellowAt.fill('50')
    await redAt.fill('95')
    await save()
    await expect.poll(paint).toEqual([yellow, yellow, yellow, red])
    await warning.uncheck()
    await save()
    await expect.poll(paint).toEqual([green, green, green, red])

    await colorful.uncheck()
    await save()
    await expect.poll(paint).toEqual([gray, gray, gray, gray])
    await visibility.uncheck()
    await save()
    await expect(meter).toHaveCount(0)

    await settings.reload()
    await expect(visibility).not.toBeChecked()
    await expect(colorful).not.toBeChecked()
    await expect(yellowAt).toHaveValue('50')
    await expect(redAt).toHaveValue('95')
    await expect(warning).not.toBeChecked()
    await visibility.check()
    await save()
    await expect(meter).toBeVisible()
    await page.reload()
    await expect.poll(paint).toEqual([gray, gray, gray, gray])
  } finally {
    await server.api.post('/api/settings', { data: { values: {
      'terminal.resource_meter': true, 'terminal.resource_color': true,
      'terminal.resource_yellow': 75, 'terminal.resource_red': 90,
      'terminal.resource_yellow_enabled': true,
    } } })
  }
})
