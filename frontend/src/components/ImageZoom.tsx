import { useEffect, useState, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'

import { t } from '../i18n/scope/system'
import { letter } from '../lib/typing'

export interface ZoomImage { url: string; label: string }

/** A key, as the hints draw it. */
function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[16px] h-[16px] px-3 rounded-[3px] border border-border-default bg-elevated text-10 font-mono text-secondary leading-none">
      {children}
    </kbd>
  )
}

/**
 * One image large over the page, for every page that shows pictures (the
 * publish board, notes). ← → (or h l, or the side buttons) step through the
 * series; a click on the picture switches between "fits the screen" and its
 * own size, scrolled; Escape, Space or a click beside the picture closes.
 */
export function ImageZoom({ images, index, onIndex, onClose }: {
  images: ZoomImage[]; index: number; onIndex: (i: number) => void; onClose: () => void
}) {
  const img = images[index]
  const n = images.length
  const [full, setFull] = useState(false)
  useEffect(() => { setFull(false) }, [index])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === ' ') { e.preventDefault(); e.stopImmediatePropagation(); onClose() }
      if (e.key === 'ArrowRight' || letter(e) === 'l') { e.preventDefault(); e.stopImmediatePropagation(); onIndex(Math.min(n - 1, index + 1)) }
      if (e.key === 'ArrowLeft' || letter(e) === 'h') { e.preventDefault(); e.stopImmediatePropagation(); onIndex(Math.max(0, index - 1)) }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [n, index, onClose, onIndex])
  if (!img) return null
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation()
  const side = 'absolute top-1/2 -translate-y-1/2 p-8 rounded-pill bg-surface text-secondary hover:text-primary shadow-lg disabled:opacity-30 disabled:pointer-events-none'
  return (
    <div role="dialog" aria-modal="true" aria-label={img.label || t('Image')} onClick={onClose}
      className="fixed inset-0 z-modal flex flex-col items-center justify-center gap-10 p-24"
      style={{ backgroundColor: 'var(--scrim-strong)' }}>
      <div className={full ? 'max-w-[96vw] max-h-[86vh] overflow-auto rounded-card' : 'contents'} onClick={stop}>
        <img src={img.url} alt={img.label} onClick={(e) => { stop(e); setFull((f) => !f) }}
          title={full ? t('Fit to the screen') : t('Actual size')}
          className={full
            ? 'block max-w-none rounded-card bg-base cursor-zoom-out'
            : 'max-w-[92vw] max-h-[82vh] object-contain rounded-card shadow-lg bg-base cursor-zoom-in'} />
      </div>
      {n > 1 && (
        <>
          <button type="button" aria-label={t('Previous picture')} disabled={index === 0} onClick={(e) => { stop(e); onIndex(index - 1) }} className={`${side} left-12`}><ChevronLeft size={18} aria-hidden /></button>
          <button type="button" aria-label={t('Next picture')} disabled={index === n - 1} onClick={(e) => { stop(e); onIndex(index + 1) }} className={`${side} right-12`}><ChevronRight size={18} aria-hidden /></button>
        </>
      )}
      <button type="button" aria-label={t('Close')} onClick={(e) => { stop(e); onClose() }} className="absolute top-12 right-12 p-8 rounded-pill bg-surface text-secondary hover:text-primary shadow-lg"><X size={16} aria-hidden /></button>
      <div className="flex items-center gap-10 text-11 font-mono rounded-pill bg-surface px-12 py-4 text-secondary" onClick={stop}>
        <span className="text-primary truncate max-w-[60vw]">{img.label || t('Image')}</span>
        <span className="tabular">{index + 1} / {n}</span>
        <span className="text-tertiary">{n > 1 && <><Kbd>←</Kbd> <Kbd>→</Kbd> · </>}{t('click: actual size')} · <Kbd>{t('esc')}</Kbd></span>
      </div>
    </div>
  )
}
