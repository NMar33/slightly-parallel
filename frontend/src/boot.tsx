import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'

import { App } from './App'
import { ThemeProvider } from './providers/ThemeProvider'
import { queryClient } from './lib/queryClient'
import { Toaster } from './components/primitives'

/**
 * The app itself, imported by main.tsx only once the language is settled:
 * modules here call t() at import time (catalogs, guide texts), so the
 * Russian dictionaries must be in place before this file loads.
 */
export function boot(rootEl: HTMLElement): void {
  createRoot(rootEl).render(
    <StrictMode>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
            <Toaster />
          </BrowserRouter>
        </QueryClientProvider>
      </ThemeProvider>
    </StrictMode>,
  )
}
