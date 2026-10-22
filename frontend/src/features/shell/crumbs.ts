import { matchPath } from 'react-router-dom'

import { LENS_HEADS } from '../../lenses/heads'
import { CATALOG_BY_KEY } from '../sidebar/catalog'
import { t } from '../../i18n/scope/shell'

/**
 * The topbar's breadcrumbs, read from the path. The bar sits outside the
 * page's <Routes>, where useParams() is empty, so the routes that carry a
 * value (a project code, an agent id, a prompt id) are matched here.
 */
const PARAM_ROUTES = ['/project/:code', '/agent/:id', '/prompts/:id']

/** Path prefixes with no page of their own: shown, never linked. */
const NO_PAGE = new Set(['/project'])

export type Crumb = { label: string; to: string | null }

/** A path segment as text; a malformed escape (%E0%A4%A) stays as typed. */
export function decodeSegment(seg: string): string {
  try { return decodeURIComponent(seg) } catch { return seg }
}

function paramValues(pathname: string): Set<string> {
  const out = new Set<string>()
  for (const pattern of PARAM_ROUTES) {
    const m = matchPath(pattern, pathname)
    if (!m) continue
    for (const v of Object.values(m.params)) if (v) out.add(v)
  }
  return out
}

function label(raw: string, params: Set<string>): string {
  // Param values (project codes, agent ids) are shown as-is.
  if (params.has(raw)) return raw
  const lens = LENS_HEADS[raw]
  if (lens) return lens.title
  // A top-level page wears its sidebar name ("Statistics", not "Stats").
  const entry = CATALOG_BY_KEY.get(`/${raw}`)
  if (entry) return entry.label
  if (raw === 'mcp') return 'MCP'
  return t(raw.charAt(0).toUpperCase() + raw.slice(1))
}

export function crumbsOf(pathname: string): Crumb[] {
  const home: Crumb = { label: t('Overview'), to: '/' }
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length === 0) return [home]
  const params = paramValues(pathname)
  const out: Crumb[] = [home]
  let acc = ''
  for (const seg of segments) {
    acc += `/${seg}`
    out.push({ label: label(decodeSegment(seg), params), to: NO_PAGE.has(acc) ? null : acc })
  }
  return out
}
