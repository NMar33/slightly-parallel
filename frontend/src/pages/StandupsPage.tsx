import { useEffect } from 'react'
import { StandupsDayBook } from '../features/standups/DayBook'
import { STANDUPS_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { t } from '../i18n/scope/pages'

/**
 * /standups — the day book, chosen in the Lab on 2026-09-23 (v04). The body is
 * shared with its variant; the product page adds the guide block.
 */
export default function StandupsPage() {
  useEffect(() => { document.title = `${t('Standups')} — Slightly Parallel` }, [])
  return <StandupsDayBook guide={<PageGuide id="standups" guide={STANDUPS_GUIDE} examples={0} />} />
}
