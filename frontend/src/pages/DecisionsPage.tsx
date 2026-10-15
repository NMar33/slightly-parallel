import { useEffect } from 'react'
import { DecisionsDayBook } from '../features/decisions/DayBook'
import { DECISIONS_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { t } from '../i18n/scope/pages'

/**
 * /decisions — the day book, chosen in the Lab on 2026-09-23 (v04). The body
 * is shared with its variant; the product page adds the guide block.
 */
export default function DecisionsPage() {
  useEffect(() => { document.title = `${t('Decisions')} — Slightly Parallel` }, [])
  return <DecisionsDayBook guide={<PageGuide id="decisions" guide={DECISIONS_GUIDE} examples={0} />} />
}
