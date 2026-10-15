/**
 * The class strings every page shares, so a label or a table head looks
 * the same wherever it is drawn. Tailwind reads class names from source,
 * so these are whole strings, never composed.
 */

/** A section or field label: mono 10px, uppercase, letter-spaced, quiet. */
export const LABEL = 'text-10 uppercase tracking-wide font-mono text-tertiary'

/** A table's head row (put it on <thead> or its <tr>): the label style, cells not bold. */
export const TH = 'text-10 uppercase tracking-wide font-mono text-tertiary [&_th]:font-normal'

/**
 * A sort button inside a head cell. Buttons do not inherit text-transform,
 * so the button says uppercase itself.
 */
export const TH_BUTTON = 'uppercase tracking-wide hover:text-primary'
