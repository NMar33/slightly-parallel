/**
 * Dates and names the kept pages print. Pure functions, so they are tested
 * without the components that show them (parts.tsx re-exports them).
 */

import type { Version } from './data'
import { monthShort } from '../../lib/months'
import { t } from '../../i18n/scope/shell'

/**
 * "2609-14 13:40" or an ISO stamp → "14 Sep, 13:40". A stamp with a zone
 * is read in local time, its day and its hour alike; one without is the
 * local time already, read as written.
 */
export function stamp(at: string): string {
  const iso = /^\d{4}-(\d{2})-(\d{2})T(\d{2}:\d{2})(?::[\d.]+)?(Z|[+-]\d{2}:?\d{2})?$/.exec(at)
  if (iso) {
    if (!iso[4]) return `${Number(iso[2])} ${monthShort(Number(iso[1]) - 1)}, ${iso[3]}`
    const d = new Date(at)
    const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    return `${d.getDate()} ${monthShort(d.getMonth())}, ${hm}`
  }
  const m = /^(\d{2})(\d{2})-(\d{2})(?:\s+(\d{2}:\d{2}))?/.exec(at)
  if (!m) return at
  return `${Number(m[3])} ${monthShort(Number(m[2]) - 1)}${m[4] ? `, ${m[4]}` : ''}`
}

/** Who wrote a version, in the page's words. */
export function whoOf(v: Pick<Version, 'how'>): string {
  return v.how === 'edited' ? t('you') : t('agent')
}
