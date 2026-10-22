import { t, locale } from '../i18n/scope/shell';
/**
 * YYMM-DD date utilities for PDR dashboard (TypeScript mirror of `date_utils.py`).
 *
 * Slightly Parallel's convention: `2608-06` means year 2026, month 08, day 06.
 * Format: `YYMM-DD` where YY is the 2-digit year within the 21st century,
 * MM is the 2-digit month, DD is the 2-digit day.
 *
 * The primary format is `YYMM-DD`. Also accepted are `YYMM-DDTHH:MM:SS` and
 * `YYMM-DDTHH:MM:SS±HH:MM` for `last_active` timestamps.
 *
 * This module is the ONE place YYMM-DD gets parsed in the frontend. Every
 * other module must import from here. Contract-tested against the Python
 * canonical implementation.
 */

/** Regex mirrors Python: 4 digits, dash, 2 digits, end-or-time-delim. */
const YYMM_DD_RE = /^(\d{4})-(\d{2})(?:$|[T ])/;

/** Century base — see Python module for rationale. */
const CENTURY_BASE = 2000;

/** Raised when a YYMM-DD string cannot be parsed (strict mode). */
export class InvalidYYMMDD extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidYYMMDD";
  }
}

// ---------------------------------------------------------------------------
// Core parsers
// ---------------------------------------------------------------------------

/**
 * Parse a YYMM-DD string into a `Date` at local midnight (strict).
 *
 * Accepts:
 *  - `"2608-06"`                       → 2026-08-06 00:00 local
 *  - `"2608-06T14:30:00"`              → 2026-08-06 00:00 local  (time stripped)
 *  - `"2608-06T14:30:00+03:00"`        → 2026-08-06 00:00 local
 *  - `"2608-06 14:30:00"`              → 2026-08-06 00:00 local
 *
 * Throws `InvalidYYMMDD` on invalid input (null, wrong shape, bad calendar
 * values like month 13 or Feb 30, non-string input).
 *
 * Performance: hot path — called per activity row for the heatmap.
 */
export function parseYYMMDD(s: unknown): Date {
  if (typeof s !== "string") {
    throw new InvalidYYMMDD(
      `expected string, got ${s === null ? "null" : typeof s}: ${String(s)}`,
    );
  }
  const m = YYMM_DD_RE.exec(s);
  if (!m) {
    throw new InvalidYYMMDD(`not YYMM-DD format: ${JSON.stringify(s)}`);
  }
  const yymmStr = m[1];
  const ddStr = m[2];
  const yy = parseInt(yymmStr.slice(0, 2), 10);
  const mm = parseInt(yymmStr.slice(2, 4), 10);
  const dd = parseInt(ddStr, 10);
  const year = CENTURY_BASE + yy;

  // Strict validation: JS `new Date(2026, 13, 1)` silently overflows.
  // Construct then verify components round-trip.
  const d = new Date(year, mm - 1, dd);
  if (
    d.getFullYear() !== year ||
    d.getMonth() !== mm - 1 ||
    d.getDate() !== dd
  ) {
    throw new InvalidYYMMDD(`invalid calendar date in ${JSON.stringify(s)}`);
  }
  return d;
}

/**
 * Format a `Date` as a YYMM-DD string.
 * Returns `""` for null/undefined (loose contract for CSV cells).
 */
export function formatYYMMDD(d: Date | null | undefined): string {
  if (d == null) return "";
  if (!(d instanceof Date) || isNaN(d.getTime())) {
    throw new TypeError(`expected Date, got ${typeof d}`);
  }
  const yy = d.getFullYear() - CENTURY_BASE;
  if (yy < 0 || yy > 99) {
    throw new RangeError(
      `year ${d.getFullYear()} out of range for YYMM-DD ` +
        `(must be ${CENTURY_BASE}..${CENTURY_BASE + 99})`,
    );
  }
  const mm = d.getMonth() + 1;
  const dd = d.getDate();
  return `${pad2(yy)}${pad2(mm)}-${pad2(dd)}`;
}

/** A local day as YYYY-MM-DD — the key the timer, the board's "today" and the calendars share. */
export function isoDay(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** Today as YYMM-DD. */
export function todayYYMMDD(now: Date = new Date()): string {
  return formatYYMMDD(new Date(now.getFullYear(), now.getMonth(), now.getDate()));
}

// ---------------------------------------------------------------------------
// ISO-local timestamps (meta.json `last_active`)
// ---------------------------------------------------------------------------

/**
 * Parse the `last_active` field: `YYMM-DDTHH:MM:SS[±HH:MM]`.
 *
 * The YYMM-DD prefix is the Slightly Parallel convention; the time portion is standard ISO.
 * Returns a `Date` interpreted as *local* time. Any trailing timezone is
 * stripped — MVP is single-user-single-machine.
 */
export function parseISOLocal(s: unknown): Date {
  if (typeof s !== "string") {
    throw new InvalidYYMMDD(
      `expected string, got ${s === null ? "null" : typeof s}`,
    );
  }

  let datePart: string;
  let timePart: string;
  if (s.includes("T")) {
    [datePart, timePart] = s.split("T", 2) as [string, string];
  } else if (s.includes(" ")) {
    const idx = s.indexOf(" ");
    datePart = s.slice(0, idx);
    timePart = s.slice(idx + 1);
  } else {
    const d = parseYYMMDD(s);
    return d;
  }

  const dateOnly = parseYYMMDD(datePart);

  // Strip trailing timezone (Z, +HH:MM, -HHMM, ...)
  timePart = timePart.replace(/([+-]\d{2}:?\d{2}|Z)$/, "");

  const parts = timePart.split(":");
  try {
    const hh = parseIntStrict(parts[0]);
    const mm = parts.length > 1 ? parseIntStrict(parts[1]) : 0;
    const ssRaw = parts.length > 2 ? parts[2] : "0";
    let ss = 0;
    let ms = 0;
    if (ssRaw.includes(".")) {
      const [ssInt, usStr] = ssRaw.split(".", 2) as [string, string];
      ss = parseIntStrict(ssInt);
      // Match Python: first 6 digits = microseconds, then /1000 for JS ms.
      const us = parseInt((usStr + "000000").slice(0, 6), 10);
      ms = Math.floor(us / 1000);
    } else {
      ss = parseIntStrict(ssRaw);
    }
    return new Date(
      dateOnly.getFullYear(),
      dateOnly.getMonth(),
      dateOnly.getDate(),
      hh,
      mm,
      ss,
      ms,
    );
  } catch (exc) {
    throw new InvalidYYMMDD(
      `invalid time portion in ${JSON.stringify(s)}: ${(exc as Error).message}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Derived helpers
// ---------------------------------------------------------------------------

/**
 * Days between `today` and the given date. Positive = past, negative = future.
 * Accepts YYMM-DD, ISO-local timestamp, or `Date`.
 */
export function daysAgo(
  s: string | Date | null | undefined,
  opts: { today?: Date } = {},
): number {
  const today = opts.today ?? new Date();
  const todayMidnight = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate(),
  );

  let d: Date;
  if (typeof s === "string") {
    try {
      d = parseYYMMDD(s);
    } catch (_err) {
      d = parseISOLocal(s);
      d = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    }
  } else if (s instanceof Date) {
    d = new Date(s.getFullYear(), s.getMonth(), s.getDate());
  } else {
    throw new InvalidYYMMDD(`expected string or Date, got ${typeof s}`);
  }

  const ms = todayMidnight.getTime() - d.getTime();
  // Use round to defuse DST off-by-one (spring-forward/fall-back).
  return Math.round(ms / 86_400_000);
}

/**
 * Human-readable relative-time. Buckets match the Python implementation
 * exactly (contract-tested):
 *
 *   < 45 s     → "just now"
 *   < 90 s     → "1m ago"
 *   < 60 min   → "Nm ago"
 *   < 24 h     → "Nh ago"
 *   <  7 d     → "Nd ago"
 *   <  5 w     → "Nw ago"
 *   < 12 mo    → "Nmo ago"
 *   else       → "Ny ago"
 *
 * Future timestamps mirror as `in Nd`.
 */
export function relativeTime(
  iso: string | Date | null | undefined,
  opts: { now?: Date } = {},
): string {
  const now = opts.now ?? new Date();

  let dt: Date;
  if (typeof iso === "string") {
    try {
      dt = parseISOLocal(iso);
    } catch (_err) {
      const d = parseYYMMDD(iso);
      dt = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    }
  } else if (iso instanceof Date) {
    dt = iso;
  } else {
    throw new InvalidYYMMDD(`expected string or Date, got ${typeof iso}`);
  }

  const seconds = Math.trunc((now.getTime() - dt.getTime()) / 1000);
  const future = seconds < 0;
  const abs = Math.abs(seconds);

  const fmt = (value: number, unit: string): string =>
    future ? t(`in {n}${unit}`, { n: value }) : t(`{n}${unit} ago`, { n: value });

  if (abs < 45) return future ? t("in a moment") : t("just now");
  if (abs < 90) return fmt(1, "m");
  const minutes = Math.floor(abs / 60);
  if (minutes < 60) return fmt(minutes, "m");
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return fmt(hours, "h");
  const days = Math.floor(hours / 24);
  if (days < 7) return fmt(days, "d");
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return fmt(weeks, "w");
  const months = Math.floor(days / 30);
  if (months < 12) return fmt(months, "mo");
  const years = Math.floor(days / 365);
  return fmt(years, "y");
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Two digits: 7 → "07". */
export function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function parseIntStrict(s: string): number {
  if (!/^\d+$/.test(s)) {
    throw new Error(`not an integer: ${JSON.stringify(s)}`);
  }
  return parseInt(s, 10);
}

/**
 * Parse a YYMM-DD string to epoch ms, or null when absent/malformed.
 * The tolerant twin of `parseYYMMDD` for render paths that must not throw.
 */
export function safeParseMs(s: unknown): number | null {
  try {
    if (typeof s !== 'string' || s === '') return null
    return parseYYMMDD(s).getTime()
  } catch {
    return null
  }
}

/**
 * An ISO stamp as the pages print it: `2026-09-17T13:31:05` → `2026-09-17 13:31`.
 * To the minute, in the stamp's own clock (no timezone maths: the server
 * writes local time and the page shows what was written). Empty in, empty out.
 */
export function formatStamp(iso: unknown): string {
  return String(iso ?? '').replace('T', ' ').slice(0, 16)
}

/**
 * A day and a time as milliseconds: `'2609-20'` + `'11:42'`. 0 when the day
 * is not a YYMM-DD. The one reading of an entry's stamp for sorting and for
 * naming a day.
 */
export function stampMs(date: string, time: string): number {
  const m = /^(\d{2})(\d{2})-(\d{2})$/.exec(date || '')
  if (!m) return 0
  const [hh, mm] = (time || '00:00').split(':').map((n) => Number(n) || 0)
  return new Date(2000 + Number(m[1]), Number(m[2]) - 1, Number(m[3]), hh, mm).getTime()
}

/**
 * A day as a heading: `'2609-21'` → `'21 September'`.
 *
 * The big date over a day's entries — in a day book, the month is already
 * on screen above it, so the year would be noise. The day itself, nothing
 * else. Malformed in, the input back.
 */
export function dayHeading(day: string): string {
  const ms = stampMs(day, '12:00')
  return ms ? new Date(ms).toLocaleDateString(locale(), { day: 'numeric', month: 'long' }) : day
}

/**
 * A day as a stamp inside an entry: `'2609-21'` → `'21 Sep 2026'`, and with
 * a time `'21 Sep 2026, 17:46'`.
 *
 * The quiet line that says when a thing was written, wherever it is read —
 * a decision's meta line, a standup's "written", a row in a list. It says
 * the year, because an entry can be read far from its month.
 */
export function dayStamp(day: string, time = ''): string {
  const ms = stampMs(day, '12:00')
  if (!ms) return ''
  const date = new Date(ms).toLocaleDateString(locale(), { day: 'numeric', month: 'short', year: 'numeric' })
  return time ? `${date}, ${time}` : date
}
