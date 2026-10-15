/** The translators for the shell area: its dictionary (i18n/ru/shell.json) first. */
import { scoped } from '..'

export { LANG_KEY, currentLang, locale, type Lang } from '..'
export const { t, tc, tn } = scoped('shell')
