/**
 * The way into a page's own tour.
 *
 * A page teaches two ways: the guide at the top says what the page is, and
 * the tour walks the controls in order. This is the second door, kept quiet
 * — a play mark beside the page's own controls, not a banner. ✕ puts the
 * link away (a synced preference); closing the guide leaves it alone. The
 * way back is "About this page": bringing the guide back brings this back
 * with it. A page whose tour has not been written shows nothing. The link
 * carries the page's own hash into the tour, so what was open stays open.
 */

import { useEffect, useState } from 'react'
import { Play, X } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import { persistPref, removePref } from '../../lib/uiPrefs'
import { tourHref } from './LiveTour'
import { PRESETS } from './script'
import { t, tn } from '../../i18n/scope/shell'

const hiddenKey = (id: string) => `sp-tourlink-${id}-hidden`
const guideKey = (id: string) => `sp-guide-${id}-hidden`

function readHidden(key: string): boolean {
  try { return localStorage.getItem(key) === 'yes' } catch { return false }
}

export function PageTourLink({ script, label = t('How this page works') }: { script: string; label?: string }) {
  const key = hiddenKey(script)
  const location = useLocation()
  const [hidden, setHidden] = useState(() => readHidden(key))

  useEffect(() => {
    const onPref = (e: Event) => {
      const detail = (e as CustomEvent<{ key: string; value: string | null }>).detail
      // The guide came back: so does the tour.
      if (detail?.key === guideKey(script) && detail.value === null) {
        removePref(key)
        setHidden(false)
      }
    }
    window.addEventListener('sp:pref', onPref)
    return () => window.removeEventListener('sp:pref', onPref)
  }, [script, key])

  const found = PRESETS.find((s) => s.id === script)
  if (!found || hidden) return null
  return (
    <span className="inline-flex items-center gap-2">
      <Link
        to={tourHref(found, 0, location.hash)}
        title={tn(found.beats.filter((b) => b.on).length, '{n} step', '{n} steps')}
        className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand"
      >
        <Play size={11} aria-hidden /> {label}
      </Link>
      <button
        type="button"
        aria-label={t('Hide this link')}
        title={t('Hide')}
        onClick={() => { persistPref(key, 'yes'); setHidden(true) }}
        className="p-2 rounded-input text-tertiary hover:text-primary hover:bg-hover"
      >
        <X size={11} aria-hidden />
      </button>
    </span>
  )
}
