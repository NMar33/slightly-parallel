import { createServer } from 'node:http'
import { once } from 'node:events'
import { test, expect, request } from '@playwright/test'
import { closeAll } from './fixtures'

test('shell setup reports an unsuccessful close instead of continuing', async () => {
  const server = createServer((req, res) => {
    if (req.method === 'GET') {
      res.setHeader('content-type', 'application/json')
      res.end(JSON.stringify({ sessions: [{ id: 't-test' }] }))
    } else {
      res.writeHead(503)
      res.end('console host failed to close')
    }
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('test server is not listening on TCP')
  const api = await request.newContext({ baseURL: `http://127.0.0.1:${address.port}` })
  try {
    await expect(closeAll(api)).rejects.toThrow('closing terminal t-test: 503 console host failed to close')
  } finally {
    await api.dispose()
    server.close()
  }
})
