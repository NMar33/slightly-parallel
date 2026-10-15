import { hydratePrefs } from './lib/uiPrefs'
import { currentLang, loadDictionaries, setLang, watchLanguage } from './i18n'

import './styles/tokens.css'
import './styles/index.css'
import './styles/skins.css'

const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('PDR: #root element missing from index.html')
}

// Prefs live on the server (ui_prefs.json); localStorage is a per-origin
// cache. Hydrate before the first render so every synchronous pref read
// sees the durable values — bounded, so a dead backend never blanks the UI.
// The Russian dictionaries are fetched only for a Russian interface, and
// before the app's modules load: they call t() at import time. Their fetch
// starts with the hydration, on the language this tab read from its storage;
// a server copy that names another language reloads the tab (watchLanguage).
// The app's modules cannot start early the same way: importing them runs
// them, and they read the dictionaries and the prefs as they load.
const dictionaries = currentLang() === 'ru'
  // Dictionaries that fail to arrive switch the interface to English, dates
  // and months with it, rather than English text with Russian dates.
  ? loadDictionaries().catch(() => { setLang('en') })
  : Promise.resolve()

void hydratePrefs().finally(async () => {
  watchLanguage()
  await dictionaries
  const { boot } = await import('./boot')
  boot(rootEl)
})
