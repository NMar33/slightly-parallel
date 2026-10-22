/** The translators for the system area: its dictionary (i18n/ru/system.json) first. */
import { scoped } from '..'

export { LANG_KEY, currentLang, locale, type Lang } from '..'
export const { t, tc, tn } = scoped('system')
