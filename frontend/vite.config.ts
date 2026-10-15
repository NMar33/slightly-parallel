import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'
import path from 'node:path'

/**
 * Vite config — Slightly Parallel frontend.
 *
 * - React 18 + TS
 * - Tailwind v4 via official plugin (no PostCSS shim)
 * - Dev server on :5173, proxies /api and /ws → FastAPI on :8123
 * - Path alias @ → src/
 * - No sourcemaps in prod (smaller bundle)
 */
// The backend the dev server proxies to: SP_API, else the port the
// launcher was given (sp.py passes SP_PORT / PORT), else 8123.
const API = process.env.SP_API
  ?? `http://127.0.0.1:${process.env.SP_PORT ?? process.env.SCAN_PORT ?? process.env.PORT ?? 8123}`

export default defineConfig({
  plugins: [react(), tailwind()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    host: '127.0.0.1',
    strictPort: true,
    // Never drawn inside another site's frame (clickjacking); the backend
    // sends the same two headers with the built page (server.PAGE_HEADERS).
    headers: { 'X-Frame-Options': 'SAMEORIGIN', 'Content-Security-Policy': "frame-ancestors 'self'" },
    proxy: {
      '/api': {
        target: API,
        changeOrigin: false,
        secure: false,
      },
      // The embedded terminal's WebSocket (Project → Terminals tab).
      '/ws': {
        target: API.replace(/^http/, 'ws'),
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
    // Bundle budget target from architecture §7: <300 KB gz total JS.
    chunkSizeWarningLimit: 300,
    rollupOptions: {
      output: {
        // The libraries every page needs, in chunks of their own: they change
        // far less often than the app, so a release leaves them cached.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react'
          if (/node_modules\/(react-router|react-router-dom|@remix-run)\//.test(id)) return 'router'
          if (id.includes('node_modules/@tanstack/')) return 'query'
          if (/node_modules\/(sonner|lucide-react)\//.test(id)) return 'ui'
          return undefined
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Vitest owns unit/component tests under src/ only. Playwright owns
    // tests/e2e/ (run via `npm run e2e`) — never collect those specs here.
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['node_modules/**', 'dist/**', 'tests/e2e/**'],
  },
})
