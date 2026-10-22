/** The translators for the project area: its dictionary (i18n/ru/project.json) first. */
import { scoped } from '..'

export { LANG_KEY, currentLang, locale, type Lang } from '..'
export const { t, tc, tn } = scoped('project')
