/** The translators for the pages area: its dictionary (i18n/ru/pages.json) first. */
import { scoped } from '..'

export { LANG_KEY, currentLang, locale, type Lang } from '..'
export const { t, tc, tn } = scoped('pages')
