/** Round 5: the words of the «Состояние вкладки» switch, shared by the panel, the compare view and «Скопировать выбор». */

import { t } from '../../../../i18n/scope/aqua'
import type { Moment, TabState } from './tabState'
import type { Pattern } from './mood'

export const tabStateLabel = () => t('Tab state')

/** Per variant: the short word and one line of what it is. */
export const tabStateWords = (): Record<TabState, [string, string]> => ({
  now: [t('as now'), t('Five dots per part over each tab, as in the window now')],
  a: [t('only when it matters'), t('Nothing at rest. A thin line over the tab while the agent waits over 10 min or context is over 70%')],
  b: [t('ring on the dot'), t('No strip. The dot of a waiting tab is a ring that fills as the wait grows. Context over 70% is a mark on the dot')],
  c: [t('tab background'), t('No strip. The tab fills faintly from the left while the agent waits. Amber or red only past a threshold')],
  d: [t('one line below'), t('One 1 px line under the tab, in the colour of the most urgent state: waiting, then context')],
  e: [t('only with Alt'), t('Nothing at rest. The dots show while Alt is held, with the Alt view')],
  f: [t('six dots'), t('Six dots in the middle of the top edge, in the chat\'s own colour: its mood. When the chat needs you, they warm from the right to amber, then red')],
})

export const patternLabel = () => t('Pattern')
/** Per pattern of the six dots: the short word and one line of what it is. */
export const patternWords = (): Record<Pattern, [string, string]> => ({
  1: [t('rhythm'), t('The last six hours, oldest on the left. The more work in an hour, the fuller its dot')],
  2: [t('constellation'), t('The same six hours; a busy hour also sits higher. A small line of dots, its own per chat')],
  3: [t('six properties'), t('Each dot one fact: waiting, context, uncommitted changes, time since the last check, tasks closed, commits today')],
})

/** How to see a variant live. */
export const tabStateSee = (v: TabState) => (v === 'e' ? t('Hold Alt') : v === 'f' ? t('Compare the tabs; press a button below') : t('Wait a minute, or press a button below'))

/** The tile name: letter and word; «as now» has no letter. */
export const tabStateName = (v: TabState) => {
  const word = tabStateWords()[v][0]
  return v === 'now' ? word.charAt(0).toUpperCase() + word.slice(1) : `${v.toUpperCase()} · ${word}`
}

export const momentWord = (m: Moment): string => ({ calm: t('all calm'), wait: t('waits 25 min'), ctx: t('context 80%') })[m]
