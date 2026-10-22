/**
 * The arithmetic behind the line gutter: a clicked row must keep meaning
 * while the view scrolls and output streams in, so everything anchors to
 * ABSOLUTE line ids — lines counted from the top of the terminal's history
 * (tmux hands out `history`/`scroll`; a plain terminal uses the widget's
 * own buffer positions the same way).
 */

export interface PanePos {
  /** Lines of history above the visible screen. */
  history: number
  /** How far the view is scrolled up into it (0 = at the bottom). */
  scroll: number
  rows: number
}

/** The absolute line id of a visible row. */
export const absOf = (row: number, pos: PanePos): number => pos.history - pos.scroll + row

/** The visible row an absolute line sits on right now (may be off-screen). */
export const rowOf = (abs: number, pos: PanePos): number => abs - pos.history + pos.scroll

/**
 * The number the gutter shows for a row: 0 is the newest line at the
 * bottom, everything above counts back (−1, −2 …) — independent of how
 * much history exists, so it reads as "how far up".
 */
export const relOf = (row: number, pos: PanePos): number => row - (pos.rows - 1) - pos.scroll
