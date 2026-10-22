import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, detailOf, getJson, getText, postJson, refused } from './getJson'

const answer = (status: number, body: unknown) =>
  vi.fn(async () => ({ ok: status < 400, status, json: async () => body }))

describe('postJson', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('returns the parsed answer', async () => {
    vi.stubGlobal('fetch', answer(200, { metadata: { id: 'tk_1' }, existing: true }))
    const data = await postJson<{ existing?: boolean }>('/api/tasks', { title: 'x' })
    expect(data.existing).toBe(true)
  })

  it("throws the server's own sentence on a refusal, not the status code", async () => {
    vi.stubGlobal('fetch', answer(422, { detail: "task.status 'Done' is not a known value — use one of: todo, doing" }))
    await expect(postJson('/api/tasks/tk_1/update', { status: 'Done' }))
      .rejects.toThrow("task.status 'Done' is not a known value — use one of: todo, doing")
  })

  it('falls back to the path and status when there is no sentence', async () => {
    vi.stubGlobal('fetch', answer(500, {}))
    await expect(postJson('/api/x', {})).rejects.toThrow('/api/x answered 500')
  })
})

describe('detailOf', () => {
  it('reads a string detail and a validation list alike', () => {
    expect(detailOf({ detail: 'no' })).toBe('no')
    expect(detailOf({ detail: [{ msg: 'a' }, { msg: 'b' }] })).toBe('a; b')
    expect(detailOf(null)).toBe('')
  })
})

describe('getJson', () => {
  afterEach(() => vi.unstubAllGlobals())
  it("throws the server's sentence and keeps the status", async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, text: async () => '{"detail":"task not found: tk_x"}' })))
    await expect(getJson('/api/tasks/tk_x')).rejects.toMatchObject({ message: 'task not found: tk_x', status: 404 })
  })
})

describe('refused', () => {
  it('turns a refused read into the fallback, and lets a network failure through', async () => {
    await expect(Promise.reject(Object.assign(new Error('no'), { status: 404 })).catch(refused([]))).resolves.toEqual([])
    await expect(Promise.reject(new TypeError('Failed to fetch')).catch(refused([]))).rejects.toThrow('Failed to fetch')
  })
})

describe('getText', () => {
  afterEach(() => vi.unstubAllGlobals())
  it('hands back the text of a good answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, text: async () => '## L1 — the document' })))
    await expect(getText('/api/docs/d1/pack')).resolves.toBe('## L1 — the document')
  })
  it('refuses an error page instead of handing it on as the text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, text: async () => '{"detail":"document not found: d1"}' })))
    await expect(getText('/api/docs/d1/pack')).rejects.toMatchObject({ message: 'document not found: d1', status: 404 })
  })
})

describe('postJson with nothing to say', () => {
  afterEach(() => vi.unstubAllGlobals())
  it('sends an empty object, not "undefined"', async () => {
    const fetched = vi.fn(async (_path: string, _init?: { body?: string }) => ({ ok: true, status: 200, json: async () => ({}) }))
    vi.stubGlobal('fetch', fetched)
    await postJson('/api/time/t1/stop')
    expect(fetched.mock.calls[0]![1]!.body).toBe('{}')
  })
})

describe('one error shape', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('a refused write carries its status, as a refused read does', async () => {
    vi.stubGlobal('fetch', answer(409, { detail: 'taken' }))
    await expect(postJson('/api/x', {})).rejects.toMatchObject({ name: 'ApiError', message: 'taken', status: 409 })
  })

  it('the typed client fails the way getJson does', async () => {
    const { api } = await import('./api')
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, text: async () => '{"detail":"warming up"}' })))
    const err = await api.snapshot().catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ message: 'warming up', status: 503, body: { detail: 'warming up' } })
  })
})
