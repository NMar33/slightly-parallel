import { useEffect, useState } from 'react'
import { AppWindow } from 'lucide-react'
import { t, tn } from '../../../i18n/scope/winrestore'
import { post, restoreOffer } from './bridge'

/**
 * The main window's question at start (Settings › Terminal › On start: ask):
 * the windows open when the app was last closed, opened again or not. The
 * window (desktop/main.js) holds them until the answer.
 */
export function RestoreOffer({ refocus }: { refocus?: () => void }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    let live = true
    void restoreOffer().then((v) => { if (live) setN(v) })
    return () => { live = false }
  }, [])
  if (!n) return null
  const answer = (open: boolean) => { post({ op: 'restore', open }); setN(0); refocus?.() }
  return (
    <div role="alertdialog" aria-label={t('Windows of last time')}
      className="absolute left-1/2 -translate-x-1/2 top-[76px] z-[46] max-w-[calc(100%-32px)] rounded-[12px] px-12 py-10 flex items-center gap-10 aq-fade"
      style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-lg)' }}>
      <AppWindow size={16} style={{ color: 'var(--brand)' }} aria-hidden />
      <span className="text-13">{tn(n, 'Open the window that was open last time?', 'Open the {n} windows that were open last time?')}</span>
      <button type="button" className="aq-btn solid ml-8" onClick={() => answer(true)}>{t('Yes')}</button>
      <button type="button" className="aq-btn" onClick={() => answer(false)}>{t('No')}</button>
    </div>
  )
}
