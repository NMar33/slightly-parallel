import { useEffect } from 'react'

import { useVariant } from './variants'

/**
 * Appearance — how the operator's choices reach the page.
 *
 * Three switches, one mechanism: skin and accent become data attributes
 * the token layer reads (`styles/skins.css`, `styles/tokens.css`), and
 * the interface scale becomes a zoom on the root element, so the px-based
 * type and spacing scale grows and shrinks as one piece. All three live
 * in the variant store (localStorage + the server's ui_prefs), so a
 * choice survives reloads, restarts and port changes.
 *
 * A skin is a whole look with its own ground and accent: while one is on,
 * data-accent is dropped and the theme (data-theme) has no effect, since
 * the skin sets every themed token itself (styles/skins.css).
 *
 * Call once from the app shell; the Appearance page just writes variants
 * and this hook repaints.
 */
export function useApplyAppearance(): void {
  const skin = useVariant('skin')
  const accent = useVariant('accent')
  useEffect(() => {
    const root = document.documentElement
    if (skin === 'none' || !skin) delete root.dataset.skin
    else root.dataset.skin = skin
    // A skin carries its own accent: the accent choice is kept, and applies
    // again when the operator returns to the default skin.
    const skinOn = Boolean(skin) && skin !== 'none'
    if (skinOn || accent === 'meridian' || !accent) delete root.dataset.accent
    else root.dataset.accent = accent
  }, [skin, accent])

  const scale = useVariant('scale')
  useEffect(() => {
    const n = Number(scale)
    const root = document.documentElement as HTMLElement & { style: CSSStyleDeclaration }
    if (!Number.isFinite(n) || n === 100) root.style.removeProperty('zoom')
    else root.style.setProperty('zoom', String(n / 100))
  }, [scale])
}
