import { useEffect } from 'react'
import { ScansDayBook } from '../features/scans/DayBook'
import { SCANS_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { t } from '../i18n/scope/pages'

/**
 * /scans — the day book, chosen in the Lab on 2026-09-23 (v04). The body is
 * shared with its variant; the product page adds the guide block.
 */
export default function ScansPage() {
  useEffect(() => { document.title = `${t('Scans')} — Slightly Parallel` }, [])
  return <ScansDayBook guide={<PageGuide id="scans" guide={SCANS_GUIDE} examples={0} />} />
}
