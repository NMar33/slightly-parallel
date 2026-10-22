import '@testing-library/jest-dom/vitest'

import { loadDictionaries } from '../i18n'

// jsdom lacks matchMedia by default; ThemeProvider needs it.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList
}

// The Russian dictionaries load on demand in the app (main.tsx); the tests
// switch languages freely, so they have them from the start.
await loadDictionaries()
