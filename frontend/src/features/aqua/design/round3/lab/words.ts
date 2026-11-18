/** Round 3 lab: the names of the «Варианты» switches and their variants, shared by the panel and «Скопировать выбор». */

import { t } from '../../../../../i18n/scope/aqua'
import type { Feature } from '../../round4/compareState'
import type { LabKey } from './live'

/** One line per variant: what it is. */
export const labWords = (): Record<LabKey, { label: string; see: string; compare: Feature; v: Record<string, [string, string]> }> => ({
  tabs: { label: t('Tabs with Alt'), see: t('Hold Alt'), compare: 'tabs', v: {
    a: [t('inline'), t('The title stays; branches, tasks and × are added on the right')],
    b: [t('facts'), t('The title gives way to branches, tasks and minutes waited; × on the left')],
    c: [t('cards'), t('Only × on the tab; a card with the facts under every tab')],
  } },
  strip: { label: t('Strip'), see: t('A line above each tab: it reddens while the agent waits'), compare: 'strip', v: {
    a: [t('segments'), t('Three short bars with gaps')],
    b: [t('one bar'), t('The parts side by side in one bar')],
    c: [t('dots'), t('Five dots per part')],
  } },
  plus: { label: t('Button +'), see: t('After the last tab'), compare: 'plus', v: {
    a: [t('split'), t('+ and ⌄ side by side, as in Windows Terminal')],
    b: [t('empty tab'), t('+ shaped like a tab, as in Ghostty and iTerm2')],
    c: [t('pill'), t('+ with the agent it opens, as in Warp')],
  } },
  plusmenu: { label: t('Menu +'), see: t('Ctrl+click on +'), compare: 'plus', v: {
    a: [t('list'), t('Rows with a hint and a key')],
    b: [t('cards'), t('A grid of cards with keys')],
  } },
})

