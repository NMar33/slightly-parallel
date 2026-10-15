/**
 * Tests for src/utils/dateUtils.ts.
 *
 * Contract note: every case here must have a matching case in the Python
 * test suite (backend/tests/test_date_utils.py). Same input, same output.
 */

import { describe, expect, it } from "vitest";

import {
  daysAgo,
  formatYYMMDD,
  InvalidYYMMDD,
  parseISOLocal,
  parseYYMMDD,
  relativeTime,
  todayYYMMDD,
} from "./dateUtils";

// ---------------------------------------------------------------------------
// parseYYMMDD
// ---------------------------------------------------------------------------

describe("parseYYMMDD", () => {
  it("parses basic YYMM-DD", () => {
    const d = parseYYMMDD("2608-06");
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(7); // Aug = 7
    expect(d.getDate()).toBe(6);
  });

  it("handles earliest and latest years", () => {
    expect(parseYYMMDD("0001-01").getFullYear()).toBe(2000);
    expect(parseYYMMDD("9912-31").getFullYear()).toBe(2099);
  });

  it("accepts leap day", () => {
    const d = parseYYMMDD("2402-29");
    expect(d.getFullYear()).toBe(2024);
    expect(d.getMonth()).toBe(1);
    expect(d.getDate()).toBe(29);
  });

  it("rejects non-leap Feb 29", () => {
    expect(() => parseYYMMDD("2302-29")).toThrow(InvalidYYMMDD);
  });

  it("rejects month 0 and 13", () => {
    expect(() => parseYYMMDD("2600-01")).toThrow(InvalidYYMMDD);
    expect(() => parseYYMMDD("2613-01")).toThrow(InvalidYYMMDD);
  });

  it("rejects Feb 30 and day 0", () => {
    expect(() => parseYYMMDD("2602-30")).toThrow(InvalidYYMMDD);
    expect(() => parseYYMMDD("2608-00")).toThrow(InvalidYYMMDD);
  });

  it.each([
    "",
    "26-08-06",
    "260806",
    "2608-6",
    "2608-006",
    "26/08/06",
    "not-a-date",
    "2026-08-06", // ISO — reject (ambiguous with 5-digit YYMM prefix)
  ])("rejects bad shape %j", (bad) => {
    expect(() => parseYYMMDD(bad)).toThrow(InvalidYYMMDD);
  });

  it.each([null, undefined, 20260806, 3.14, [], {}])(
    "rejects non-string %j",
    (bad) => {
      expect(() => parseYYMMDD(bad as unknown)).toThrow(InvalidYYMMDD);
    },
  );

  it("accepts ISO-local prefix", () => {
    expect(parseYYMMDD("2608-06T14:30:00").getDate()).toBe(6);
    expect(parseYYMMDD("2608-06T14:30:00+03:00").getDate()).toBe(6);
    expect(parseYYMMDD("2608-06 14:30:00").getDate()).toBe(6);
  });
});

// ---------------------------------------------------------------------------
// formatYYMMDD
// ---------------------------------------------------------------------------

describe("formatYYMMDD", () => {
  it("formats basic date", () => {
    expect(formatYYMMDD(new Date(2026, 7, 6))).toBe("2608-06");
  });

  it("pads single digits", () => {
    expect(formatYYMMDD(new Date(2001, 0, 2))).toBe("0101-02");
  });

  it("returns empty for null/undefined", () => {
    expect(formatYYMMDD(null)).toBe("");
    expect(formatYYMMDD(undefined)).toBe("");
  });

  it("rejects out-of-range years", () => {
    expect(() => formatYYMMDD(new Date(1999, 0, 1))).toThrow(RangeError);
    expect(() => formatYYMMDD(new Date(2100, 0, 1))).toThrow(RangeError);
  });

  it("round-trips through parseYYMMDD", () => {
    for (const d of [
      new Date(2001, 0, 1),
      new Date(2026, 7, 6),
      new Date(2099, 11, 31),
    ]) {
      const s = formatYYMMDD(d);
      const parsed = parseYYMMDD(s);
      expect(parsed.getFullYear()).toBe(d.getFullYear());
      expect(parsed.getMonth()).toBe(d.getMonth());
      expect(parsed.getDate()).toBe(d.getDate());
    }
  });
});

// ---------------------------------------------------------------------------
// daysAgo
// ---------------------------------------------------------------------------

describe("daysAgo", () => {
  const today = new Date(2026, 7, 6);

  it("today is zero", () => {
    expect(daysAgo("2608-06", { today })).toBe(0);
  });

  it("past positive", () => {
    expect(daysAgo("2608-01", { today })).toBe(5);
  });

  it("future negative", () => {
    expect(daysAgo("2608-10", { today })).toBe(-4);
  });

  it("accepts Date input", () => {
    expect(daysAgo(new Date(2026, 7, 1), { today })).toBe(5);
  });

  it("accepts ISO-local input", () => {
    expect(daysAgo("2608-01T14:30:00", { today })).toBe(5);
  });
});

// ---------------------------------------------------------------------------
// parseISOLocal
// ---------------------------------------------------------------------------

describe("parseISOLocal", () => {
  it("full timestamp", () => {
    const d = parseISOLocal("2608-06T14:30:00");
    expect(d.getHours()).toBe(14);
    expect(d.getMinutes()).toBe(30);
  });

  it("strips timezone suffix", () => {
    const d = parseISOLocal("2608-06T14:30:00+03:00");
    expect(d.getHours()).toBe(14);
    expect(d.getMinutes()).toBe(30);
    const z = parseISOLocal("2608-06T14:30:00Z");
    expect(z.getHours()).toBe(14);
  });

  it("microseconds parsed as milliseconds", () => {
    const d = parseISOLocal("2608-06T14:30:00.123456");
    expect(d.getMilliseconds()).toBe(123);
  });

  it("HH:MM only", () => {
    const d = parseISOLocal("2608-06T14:30");
    expect(d.getSeconds()).toBe(0);
  });

  it("date-only falls back to midnight", () => {
    const d = parseISOLocal("2608-06");
    expect(d.getHours()).toBe(0);
    expect(d.getMinutes()).toBe(0);
  });

  it("space separator accepted", () => {
    const d = parseISOLocal("2608-06 14:30:00");
    expect(d.getHours()).toBe(14);
  });
});

// ---------------------------------------------------------------------------
// relativeTime
// ---------------------------------------------------------------------------

describe("relativeTime", () => {
  const now = new Date(2026, 7, 6, 12, 0, 0);

  it("just now (<45s)", () => {
    expect(relativeTime(new Date(2026, 7, 6, 11, 59, 30), { now })).toBe(
      "just now",
    );
  });

  it("60s → 1m ago (<90s bucket)", () => {
    expect(relativeTime(new Date(2026, 7, 6, 11, 59, 0), { now })).toBe(
      "1m ago",
    );
  });

  it("minutes", () => {
    expect(relativeTime(new Date(2026, 7, 6, 11, 30, 0), { now })).toBe(
      "30m ago",
    );
  });

  it("hours", () => {
    expect(relativeTime(new Date(2026, 7, 6, 9, 0, 0), { now })).toBe("3h ago");
  });

  it("days", () => {
    expect(relativeTime(new Date(2026, 7, 3, 12, 0, 0), { now })).toBe(
      "3d ago",
    );
  });

  it("weeks", () => {
    expect(relativeTime(new Date(2026, 6, 16, 12, 0, 0), { now })).toBe(
      "3w ago",
    );
  });

  it("months", () => {
    expect(relativeTime(new Date(2026, 4, 1, 12, 0, 0), { now })).toBe(
      "3mo ago",
    );
  });

  it("years", () => {
    expect(relativeTime(new Date(2023, 7, 6, 12, 0, 0), { now })).toBe(
      "3y ago",
    );
  });

  it("future mirrors as 'in Nd'", () => {
    expect(relativeTime(new Date(2026, 7, 9, 12, 0, 0), { now })).toBe(
      "in 3d",
    );
  });

  it("YYMM-DD string input", () => {
    expect(relativeTime("2608-03", { now })).toBe("3d ago");
  });

  it("ISO string input", () => {
    expect(relativeTime("2608-06T09:00:00", { now })).toBe("3h ago");
  });
});

// ---------------------------------------------------------------------------
// todayYYMMDD
// ---------------------------------------------------------------------------

describe("todayYYMMDD", () => {
  it("emits a parseable YYMM-DD", () => {
    const s = todayYYMMDD();
    expect(s).toMatch(/^\d{4}-\d{2}$/);
    expect(() => parseYYMMDD(s)).not.toThrow();
  });

  it("respects the injected 'now'", () => {
    expect(todayYYMMDD(new Date(2026, 7, 6))).toBe("2608-06");
  });
});
