import { useEffect } from 'react'
import { SearchPage } from '../features/search/SearchPage'
import { t } from '../i18n/scope/pages'

/**
 * /search — one word over every entry, every part of the program's map and
 * every captured chat turn. Chosen from the Lab on 2026-09-23 (v01, the
 * filter line, with the numbers from v05 under it). The body is shared with
 * the variant.
 */
export default function Search(): JSX.Element {
  useEffect(() => { document.title = `${t('Search')} — Slightly Parallel` }, [])
  return <SearchPage />
}
