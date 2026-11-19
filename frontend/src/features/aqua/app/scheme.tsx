/**
 * The terminal window in the operator's colour scheme (tk_83077846).
 *
 * `useWindowScheme` gives the window's root its CSS tokens: with the scheme
 * applying to the terminal only, the terminal's own (its ground, its tab in
 * front); with "whole window", the title row, the tab strip, the sidebars,
 * the menus and the strips too (schemes.ts windowVars, every ink lifted to
 * read at 4.5:1 on each chrome surface). sp-now on the terminal only gives
 * nothing: the window is as it was.
 *
 */
import type { CSSProperties } from 'react'

import { windowTermVars, windowVars } from '../../terminal/schemes'
import { useTermScheme } from '../../terminal/useScheme'

export function useWindowScheme(): { style: CSSProperties; id: string; scope: 'terminal' | 'window' } {
  const { scheme, scope } = useTermScheme()
  const vars = scope === 'window' ? windowVars(scheme) : windowTermVars(scheme)
  return { style: vars as CSSProperties, id: scheme.id, scope }
}
