/**
 * Settings › Terminal, the window's part (tk_a9306fb1): the status strip on
 * the tabs, and health and time. The same rows the window's own popovers
 * show; the values are the operator's preferences, shared with the window
 * through the server (ui_prefs).
 */

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import '../../design/aqua.css'
import { t } from '../../../../i18n/scope/aqua'
import { StripSettingsRows } from './Tab'
import { HealthSettings } from '../health'

export function TermWindowSettings() {
  const [open, setOpen] = useState<'' | 'strip' | 'health'>('')
  const head = (k: 'strip' | 'health', label: string) => (
    <button type="button" className="flex items-center gap-6 h-[26px] text-12 text-primary w-full text-left" aria-expanded={open === k} onClick={() => setOpen(open === k ? '' : k)}>
      {open === k ? <ChevronDown size={12} /> : <ChevronRight size={12} />}{label}
    </button>
  )
  return (
    <div className="aq flex flex-col gap-2 py-4" data-v="j" style={{ background: 'transparent' }} data-term-window-settings>
      {head('strip', t('Status strip on the tabs'))}
      {open === 'strip' && <div className="pl-[18px] pb-6"><StripSettingsRows /></div>}
      {head('health', t('Health and time'))}
      {open === 'health' && <div className="pl-[18px] pb-6"><HealthSettings /></div>}
    </div>
  )
}
