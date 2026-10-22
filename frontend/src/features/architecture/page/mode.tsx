import { useState } from 'react'
import { Segmented } from '../../../components/Segmented'
import { persistPref, readPref } from '../../../lib/uiPrefs'
import { t } from '../../../i18n/scope/system'

/** The Architecture lens has three parts: the page (what the project is),
 *  the map (every part of the program as a row) and the ledger (what each
 *  scan changed). The project tab and /architecture
 *  share this switch and remember the same choice. */
type ArchMode = 'page' | 'map' | 'ledger'

const MODE_KEY = 'sp-architecture-tab-mode'

const MODES: Array<readonly [ArchMode, string, string]> = [
  ['page', t('page'), t('What the project is, as claims with their evidence')],
  ['map', t('map'), t('Every part of the program as a row, and what connects to what')],
  ['ledger', t('changes'), t('What each scan changed: register, stream, codebase')],
]

/** The page is the default; the operator's last choice is remembered. */
export function useArchMode(): [ArchMode, (m: ArchMode) => void] {
  const [mode, setMode] = useState<ArchMode>(() => {
    const kept = readPref(MODE_KEY)
    return kept === 'ledger' || kept === 'map' ? kept : 'page'
  })
  return [mode, (m) => { setMode(m); persistPref(MODE_KEY, m) }]
}

export function ArchModeSwitch({ value, onChange }: { value: ArchMode; onChange: (m: ArchMode) => void }) {
  return (
    <Segmented label={t('Architecture mode')} shape="pill" value={value} onChange={onChange} options={MODES} />
  )
}
