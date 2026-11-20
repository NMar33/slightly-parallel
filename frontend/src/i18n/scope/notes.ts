/** The translators for the notes area: its dictionary (i18n/ru/notes.json) first. */
import { scoped } from '..'

export { LANG_KEY, currentLang, locale, type Lang } from '..'
export const { t, tc, tn } = scoped('notes')
