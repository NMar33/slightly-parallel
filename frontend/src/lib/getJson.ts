import { toast } from 'sonner'
import { t } from '../i18n/scope/shell'

/**
 * A request the server refused: its own sentence (`detail`) as the
 * message, else the path and the status; the status and the parsed body
 * ride along. Every read and write in the app fails with this one shape —
 * a network failure stays the browser's own TypeError, with no status.
 */
export class ApiError extends Error {
  status: number
  body: unknown
  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

/**
 * GET a JSON endpoint; a non-2xx answer is an ApiError carrying the
 * server's own sentence (`detail`), as a refused write does.
 */
export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return (await answered(path, signal)).json() as Promise<T>
}

/**
 * GET an endpoint that answers in plain text (a pack, a log). Refused the
 * same way `getJson` is — an error page is never handed on as the text.
 */
export async function getText(path: string, signal?: AbortSignal): Promise<string> {
  return (await answered(path, signal)).text()
}

/** The response of a GET that answered 2xx; an ApiError otherwise. */
export async function answered(path: string, signal?: AbortSignal, headers?: HeadersInit): Promise<Response> {
  const res = await fetch(path, headers ? { signal, headers } : { signal })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let body: unknown = text
    try { body = JSON.parse(text) } catch { /* not JSON: the text is the body */ }
    throw new ApiError(detailOf(body) || t('{path} answered {status}', { path, status: res.status }), res.status, body)
  }
  return res
}

/**
 * A refused read (the server answered, not 2xx) as `fallback`; a network
 * failure still throws. `getJson(url).catch(refused({ items: [] }))`.
 */
export const refused = <F,>(fallback: F) => (e: unknown): F => {
  if ((e as { status?: number } | null)?.status) return fallback
  throw e
}

/**
 * POST a JSON body (an empty object when there is nothing to say); the
 * parsed answer, or an Error carrying the server's own sentence (`detail`)
 * — never a bare status code, which tells nobody anything. The answer is
 * `unknown` until the caller names its shape.
 */
export async function postJson<T = unknown>(path: string, body: unknown = {}, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(detailOf(data) || t('{path} answered {status}', { path, status: res.status }), res.status, data)
  return data as T
}

/** The sentence a refused write carries, whatever shape FastAPI put it in. */
export function detailOf(data: unknown): string {
  const d = (data as { detail?: unknown } | null)?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x) => String((x as { msg?: string })?.msg ?? x)).join('; ')
  return ''
}

/** The one way a failed write is shown: the server's own message, as a toast. */
export const fail = (e: unknown) => toast.error(String((e as Error).message))
