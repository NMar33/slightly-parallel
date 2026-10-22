/**
 * The rollups the sheet reads from.
 *
 * The server counts the rows. This file only ranks them, scales them into
 * bar widths, and works out the two numbers the server does not send: the
 * median turn length, and a day's share of the whole index.
 *
 * Everything here is a plain function of its input, so the page draws and
 * the tests check the same arithmetic.
 */

import type { Pair } from './api'
import { locale } from '../../../i18n/scope/system'

/* ------------------------------------------------------------- numbers */

/** A count, written the way a table writes it. */
export function num(n: number): string {
  return n.toLocaleString(locale())
}

/** A share, to one decimal. Under a tenth of a percent reads as `<0.1%`,
 *  and a share short of the whole never rounds up to `100.0%`. */
export function pct(part: number, whole: number): string {
  if (!whole) return '0%'
  const share = (part / whole) * 100
  if (share > 0 && share < 0.05) return '<0.1%'
  if (share < 100 && share >= 99.95) return '>99.9%'
  return `${share.toFixed(1)}%`
}

/* -------------------------------------------------------------- ranking */

export interface Ranked {
  /** 1 for the largest. */
  rank: number
  label: string
  n: number
  /** Of the whole set of pairs. */
  share: number
  /** Of the largest, so a bar can be drawn. */
  scale: number
}

/**
 * The pairs largest first, each with its share and its bar width.
 *
 * Ties keep alphabetical order, so the table is stable between reads.
 */
export function ranked(pairs: Pair[], limit?: number): Ranked[] {
  const sorted = [...pairs].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  const total = sorted.reduce((sum, [, n]) => sum + n, 0)
  const max = sorted[0]?.[1] ?? 0
  return sorted.slice(0, limit ?? sorted.length).map(([label, n], i) => ({
    rank: i + 1,
    label,
    n,
    share: total ? n / total : 0,
    scale: max ? n / max : 0,
  }))
}

/* ------------------------------------------------------- turn lengths */

export interface Bucket {
  bucket: string
  n: number
  scale: number
  share: number
  /** True for the bucket the middle turn falls in. */
  median: boolean
}

/**
 * The distribution, with the median bucket marked.
 *
 * The server sends counts per bucket, not the lengths themselves, so the
 * median is the bucket the middle turn falls in: the first bucket where
 * the running total reaches half of the turns.
 */
export function distribution(buckets: Array<{ bucket: string; n: number }>): Bucket[] {
  const total = buckets.reduce((sum, b) => sum + b.n, 0)
  const max = buckets.reduce((m, b) => Math.max(m, b.n), 0)
  const half = total / 2
  let running = 0
  let found = false
  return buckets.map((b) => {
    running += b.n
    const median = !found && total > 0 && b.n > 0 && running >= half
    if (median) found = true
    return {
      bucket: b.bucket,
      n: b.n,
      scale: max ? b.n / max : 0,
      share: total ? b.n / total : 0,
      median,
    }
  })
}

/** The name of the median bucket, or an empty string when there are none. */
export function medianBucket(buckets: Array<{ bucket: string; n: number }>): string {
  return distribution(buckets).find((b) => b.median)?.bucket ?? ''
}

/* -------------------------------------------------------------- the days */

export interface DayBar {
  day: string
  /** The rows of this day in the set being drawn. */
  n: number
  /** The rows of this day in the whole index. */
  base: number
  /** The bar width for `n`, against the busiest day of the whole index. */
  scale: number
  /** The bar width for `base`. */
  baseScale: number
  /** `n` against this day's own rows. With no word this is 1. */
  shareOfDay: number
  /** `n` against every row of the set being drawn. */
  shareOfAll: number
}

/**
 * One bar per day of the index, in date order.
 *
 * `base` is always every row of that day, so a word's bar is read inside
 * the day it was said in. Days the word does not appear on stay in the
 * row, at zero.
 */
export function dayBars(base: Pair[], word?: Pair[] | null): DayBar[] {
  const days = [...base].sort((a, b) => a[0].localeCompare(b[0]))
  const found = new Map(word ?? [])
  const maxBase = days.reduce((m, [, n]) => Math.max(m, n), 0)
  const totalN = word
    ? (word ?? []).reduce((sum, [, n]) => sum + n, 0)
    : days.reduce((sum, [, n]) => sum + n, 0)
  return days.map(([day, baseN]) => {
    const n = word ? (found.get(day) ?? 0) : baseN
    return {
      day,
      n,
      base: baseN,
      scale: maxBase ? n / maxBase : 0,
      baseScale: maxBase ? baseN / maxBase : 0,
      shareOfDay: baseN ? n / baseN : 0,
      shareOfAll: totalN ? n / totalN : 0,
    }
  })
}

/** The day that carries the most of what is drawn. */
export function busiest(bars: DayBar[]): DayBar | null {
  return bars.reduce<DayBar | null>((best, b) => (best && best.n >= b.n ? best : b), null)
}

/** How many of the days carry anything at all. */
export function daysWith(bars: DayBar[]): number {
  return bars.filter((b) => b.n > 0).length
}

/* ------------------------------------------------------------- the words */

export interface NearWord {
  rank: number
  word: string
  n: number
  lift: number
  /** The bar width, against the most rows on the list. Lift ties near the
   * top of this list, so the bar carries the count instead. */
  scale: number
}

/** The words that keep the searched word company, strongest lift first. */
export function nearWords(
  near: Array<{ word: string; n: number; lift: number }>,
  limit?: number,
): NearWord[] {
  const sorted = [...near].sort((a, b) => b.lift - a.lift || b.n - a.n)
  const max = sorted.reduce((m, w) => Math.max(m, w.n), 0)
  return sorted.slice(0, limit ?? sorted.length).map((w, i) => ({
    rank: i + 1,
    word: w.word,
    n: w.n,
    lift: w.lift,
    scale: max ? w.n / max : 0,
  }))
}

/** A count from a list of pairs, by name. */
export function countOf(pairs: Pair[], name: string): number {
  return pairs.find(([label]) => label === name)?.[1] ?? 0
}

