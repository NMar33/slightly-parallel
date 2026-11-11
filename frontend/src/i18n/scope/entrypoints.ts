/** The translators for the entry points area: its dictionary (i18n/ru/entrypoints.json) first. */
import { scoped } from '..'

export { LANG_KEY, currentLang, locale, type Lang } from '..'
export const { t, tc, tn } = scoped('entrypoints')
