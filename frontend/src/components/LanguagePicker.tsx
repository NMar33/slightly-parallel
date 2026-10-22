import { LANG_KEY, currentLang, type Lang } from '../i18n'
import { t } from '../i18n/scope/shell'
import { savePrefNow } from '../lib/uiPrefs'

const LANGS: Array<[Lang, string]> = [['en', 'English'], ['ru', 'Русский']]

/** The interface language. The page reloads in the one picked: the
 *  language is read once, when the app loads (i18n/index.ts). */
export function LanguagePicker() {
  const now = currentLang()
  return (
    <div role="radiogroup" aria-label={t('Language')} className="inline-flex rounded-input border border-border-subtle overflow-hidden">
      {LANGS.map(([id, name]) => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={now === id}
          onClick={() => {
            if (now === id) return
            // The reloaded page reads the server's copy first: it must hold the choice.
            void savePrefNow(LANG_KEY, id).then(() => window.location.reload())
          }}
          className={`h-32 px-14 text-13 ${now === id ? 'bg-brand text-on-brand font-semibold' : 'text-secondary hover:bg-hover'}`}
        >
          {name}
        </button>
      ))}
    </div>
  )
}
