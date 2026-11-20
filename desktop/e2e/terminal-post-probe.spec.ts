import { expect, openShell, sessions, test } from './fixtures'

for (const width of [1, 2, 4]) {
  test(`the Windows API can repeatedly open and close ${width} shell(s) without a renderer`, async ({ server }) => {
    test.setTimeout(180_000)
    for (let cycle = 0; cycle < 20; cycle++) {
      const shells = await test.step(`Open cycle ${cycle + 1}`, () => Promise.all(
        Array.from({ length: width }, (_, i) => openShell(server.api, `probe ${cycle + 1}.${i + 1}`)),
      ), { timeout: 25_000 })
      await test.step(`Close cycle ${cycle + 1}`, async () => {
        await Promise.all(shells.map(async ({ id }) => {
          const response = await server.api.post(`/api/terminal/sessions/${id}/close`, { data: { actor: 'operator' } })
          expect(response.ok(), await response.text()).toBe(true)
        }))
      }, { timeout: 25_000 })
    }
    expect(await sessions(server.api)).toEqual([])
  })
}
