import { QueryClient } from '@tanstack/react-query'

/**
 * TanStack Query client — server-state cache for the dashboard.
 *
 *   - No query polls by default. One small poll of /api/health (see
 *     useFreshness in lib/settings.ts) watches the server's data stamp and
 *     invalidates the active queries of the areas that moved. Every query
 *     used to refetch every 5 s: a page that reads sixty details asked for
 *     all sixty every 5 s, and the server spent its day answering them.
 *     The few queries the stamp cannot see set a `refetchInterval` of
 *     their own (terminal list, monitor, capture health, backups, the
 *     smart timer); they are listed at useFreshness.
 *   - `staleTime: 30s` — a query mounted twice within that window is one
 *     request; the freshness poll invalidates ahead of it when data moves.
 *   - `retry: 1` — one retry then surface the error to the UI. Never blocking
 *     the user with a 30s exponential-backoff cascade.
 *   - `refetchOnWindowFocus: false` — the freshness poll handles it;
 *     refetching every tab-focus is annoying on a dashboard kept open all day.
 *   - Errors go to React Query defaults; feature code composes with `sonner`
 *     toasts as needed.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60 * 1_000,
      refetchInterval: false,
      refetchIntervalInBackground: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      retry: 1,
    },
    mutations: {
      // MVP is read-only (§2 "no write endpoints in v1"); leave a sane default
      // for the eventual mutation footprint.
      retry: 0,
    },
  },
})
