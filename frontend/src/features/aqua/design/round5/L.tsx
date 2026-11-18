/**
 * Round 5 (tk_d2e11125): L — K and one new switch, «Состояние вкладки»:
 * quieter ways to show a tab's state than the dots over the tabs (strip c,
 * the operator's pick of 18.11, now in the real window). K (round4/K.tsx)
 * is not changed: L renders it inside a MoreContext (round4/more.ts) that
 * gives every tab the picked look, puts the new row at the top of the
 * «Варианты» panel (the «Полоса» row leaves: «как сейчас» is the dots),
 * opens «Сравнить» on the new feature and adds its line to «Скопировать
 * выбор». The variants and their thresholds: ./tabState.ts.
 *
 * `/aqua?v=l&tabstate=now|a|b|c|d|e|f`, `&pattern=1|2|3` (f's pattern), `&compare=tabstate`.
 */

import { t } from '../../../../i18n/scope/aqua'
import { K } from '../round4/K'
import { MoreContext, type More } from '../round4/more'
import type { Feature } from '../round4/compareState'
import type { Theme } from '../AquaDesign'
import { TabStateCompare, TabStateRow, decorFor } from './TabState'
import { useContextClock, useTabState } from './tabState'
import { usePattern } from './mood'
import { patternLabel, patternWords, tabStateLabel, tabStateWords } from './words'

/** The compare view's features in L: the new one first, the strip's (now the «как сейчас» variant) left out. */
export const L_FEATURES: readonly Feature[] = ['tabstate', 'tabs', 'plus', 'msgmenu', 'scheme', 'health']

export function L({ theme }: { theme: Theme }) {
  useContextClock()
  const [look] = useTabState()
  const [pattern] = usePattern()
  const six = look === 'f' ? `, ${patternLabel().toLowerCase()} f${pattern} — ${patternWords()[pattern][0]}` : ''
  const more: More = {
    v: 'l',
    head: t('Picks in mockup L (/aqua?v=l):'),
    tabDecor: decorFor(look),
    hide: ['strip'],
    rows: <TabStateRow />,
    summary: look === 'f' ? `f${pattern}` : look,
    first: 'tabstate',
    features: L_FEATURES,
    compare: {
      tabstate: {
        word: tabStateLabel(),
        line: t('Each variant on the same tabs at three moments: all calm, one chat waits 25 min, context 80%. On the right, the tab that changes, twice the size.'),
        body: <TabStateCompare />,
      },
    },
    lines: [`${tabStateLabel()}: ${look} — ${tabStateWords()[look][0]}${six}`],
    params: look === 'f' ? { tabstate: look, pattern } : { tabstate: look },
  }
  return <MoreContext.Provider value={more}><K theme={theme} /></MoreContext.Provider>
}
