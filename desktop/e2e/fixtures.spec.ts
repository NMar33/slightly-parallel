import { createServer } from 'node:http'
import { once } from 'node:events'
import { expect, request } from '@playwright/test'
import { closeAll, test } from './fixtures'

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

test('shell setup can make its next request after the server stops accepting a socket', async ({ server }) => {
  const sockets = new WeakSet()
  const listener = createServer((req, res) => {
    if (sockets.has(req.socket)) {
      req.socket.destroy()
      return
    }
    sockets.add(req.socket)
    res.end('ok')
  })
  listener.listen(0, '127.0.0.1')
  await once(listener, 'listening')
  const address = listener.address()
  if (!address || typeof address === 'string') throw new Error('test server is not listening on TCP')
  const url = `http://127.0.0.1:${address.port}`
  try {
    expect(await (await server.api.get(url)).text()).toBe('ok')
    expect(await (await server.api.post(url)).text()).toBe('ok')
  } finally {
    listener.closeAllConnections()
    listener.close()
  }
})
