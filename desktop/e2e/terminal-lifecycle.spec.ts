import { closeAll, expect, openShell, sessions, test } from './fixtures'

for (const width of [2, 4]) {
  test(`repeated terminal lifecycle requests return with ${width} concurrent shells`, async ({ server }) => {
    test.setTimeout(180_000)
    await test.step('Close terminals from the preceding test', () => closeAll(server.api), { timeout: 25_000 })

    for (let cycle = 1; cycle <= 20; cycle++) {
      const shells = await test.step(`Open batch ${cycle}`, () => Promise.all(
        Array.from({ length: width }, (_, index) => openShell(server.api, `lifecycle ${cycle}.${index + 1}`)),
      ), { timeout: 25_000 })
      await test.step(`Close batch ${cycle}`, async () => {
        await Promise.all(shells.map(async ({ id }) => {
          const response = await server.api.post(`/api/terminal/sessions/${id}/close`, { data: { actor: 'operator' } })
          expect(response.status(), `closing terminal ${id}: ${await response.text()}`).toBe(200)
          expect(await response.json()).toEqual({ closed: id })
        }))
      }, { timeout: 25_000 })
    }

    expect(await sessions(server.api)).toEqual([])
  })
}
