/**
 * Round 3 — the line between two columns; moved to the shared module
 * (../../render/Divider). The keys line J and L print stays here.
 */

import { t } from '../../../../i18n/scope/notes'
import { Key } from '../round2/columns'

export { Divider, ListBar } from '../../render/Divider'

/** The keys of the page in one line. */
export function KeysLine3({ tiles }: { tiles: string }) {
  return (
    <span className="inline-flex items-center gap-6 flex-wrap text-11 text-tertiary max-sm:hidden">
      <Key>l</Key>{t('list')}<Key>r</Key>{t('outline')}<Key>o</Key>{tiles}<Key>j</Key><Key>k</Key>{t('next, previous note')}
    </span>
  )
}
