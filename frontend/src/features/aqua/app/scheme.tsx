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
 * `SchemeButton` is the quick switch in the title row: the same grid as
 * Settings › Terminal › Colour scheme, in a dialog; Esc closes it.
 */

import { useEffect, useState, type CSSProperties } from 'react'
import { Palette, X } from 'lucide-react'

import { t } from '../../../i18n/scope/aqua'
import { windowTermVars, windowVars } from '../../terminal/schemes'
import { SchemePicker } from '../../terminal/SchemePicker'
import { useTermScheme } from '../../terminal/useScheme'

export function useWindowScheme(): { style: CSSProperties; id: string; scope: 'terminal' | 'window' } {
  const { scheme, scope } = useTermScheme()
  const vars = scope === 'window' ? windowVars(scheme) : windowTermVars(scheme)
  return { style: vars as CSSProperties, id: scheme.id, scope }
}

export function SchemeButton({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false)
  const close = () => { setOpen(false); onClose?.() }
  useEffect(() => {
    if (!open) return
    // First, before the window's own keys: Esc closes this and does nothing else.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault(); e.stopImmediatePropagation()
      setOpen(false); onClose?.()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, onClose])
  return (
    <>
      <button type="button" data-nodrag className="aq-btn icon" aria-label={t('Colour scheme')} title={t('Colour scheme')} aria-haspopup="dialog" aria-expanded={open}
        onClick={() => setOpen(!open)}><Palette size={13} /></button>
      {open && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center" role="dialog" aria-label={t('Colour scheme')} data-nodrag>
          <button type="button" aria-label={t('Close')} tabIndex={-1} className="absolute inset-0 cursor-default" style={{ background: 'oklch(0 0 0 / 0.28)' }} onClick={close} />
          <div className="relative rounded-[12px] p-16 aq-fade w-[720px] max-w-[94%] overflow-y-auto" style={{ maxHeight: 'calc(100vh - 48px)', background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-lg)', color: 'var(--text-primary)' }}>
            <div className="flex items-center mb-10">
              <b className="text-14">{t('Colour scheme')}</b>
              <span className="ml-8 text-11 aq-ink3">{t('also in Settings › Terminal')}</span>
              <button type="button" autoFocus className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={close}><X size={14} /></button>
            </div>
            <SchemePicker />
          </div>
        </div>
      )}
    </>
  )
}
