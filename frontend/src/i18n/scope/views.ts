/** The translators for the views area: its dictionary (i18n/ru/views.json) first. */
import { scoped } from '..'

export { LANG_KEY, currentLang, locale, type Lang } from '..'
export const { t, tc, tn } = scoped('views')
