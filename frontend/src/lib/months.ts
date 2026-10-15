import { currentLang, locale } from '../i18n/scope/shell'

/**
 * Month names in the interface language. English as before; Russian takes
 * the genitive for a short date ("14 сен") and the nominative for a month
 * heading ("Сентябрь 2026") — which Intl does not give for short forms.
 */
const EN_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const EN_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const RU_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const RU_LONG = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

/** "Sep" · "сен" — for a day and month: `14 Sep`. `i` is 0–11. */
export const monthShort = (i: number): string => ((currentLang() === 'ru' ? RU_SHORT : EN_SHORT)[i] ?? '')

const EN_WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const RU_WD = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

/** "Mon" · "пн" — `i` is 0 (Monday) to 6 (Sunday). */
export const weekdayShort = (i: number): string => ((currentLang() === 'ru' ? RU_WD : EN_WD)[i] ?? '')

/** "September" · "Сентябрь" — for a heading. `i` is 0–11. */
export const monthLong = (i: number): string => ((currentLang() === 'ru' ? RU_LONG : EN_LONG)[i] ?? '')

/**
 * A month on its own for a label (an axis, the year's row): "Sep" in
 * English, where en-GB's Intl writes "Sept"; Russian as Intl writes it.
 */
export const monthLabel = (d: Date): string =>
  (currentLang() === 'ru' ? d.toLocaleDateString(locale(), { month: 'short' }) : EN_SHORT[d.getMonth()] ?? '')

/** A day and month for a label: "14 Sep"; Russian as Intl writes it ("14 сент."). */
export const dayMonth = (d: Date): string =>
  (currentLang() === 'ru' ? d.toLocaleDateString(locale(), { day: 'numeric', month: 'short' }) : `${d.getDate()} ${EN_SHORT[d.getMonth()] ?? ''}`)
