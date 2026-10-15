import { Toaster as SonnerToaster, toast as sonnerToast } from 'sonner'

/**
 * Toast — thin wrapper around `sonner` that pins design tokens instead of
 * sonner's default palette. Import and render <Toaster /> once at App root;
 * call `toast.success(...)`, `toast.error(...)`, etc. from anywhere.
 *
 * We map sonner's four intents to our status tokens via `toastOptions.classNames`
 * — this way toasts read in both themes and never introduce a raw hex.
 *
 * Position: bottom-right (Cal.com pattern, cited in architecture §2 Frontend).
 */

interface ToasterProps {
  position?:
    | 'top-left'
    | 'top-center'
    | 'top-right'
    | 'bottom-left'
    | 'bottom-center'
    | 'bottom-right'
  richColors?: boolean
}

const styleBase =
  'font-sans text-13 rounded-card border shadow-md px-16 py-12'

export function Toaster({ position = 'bottom-right' }: ToasterProps = {}) {
  return (
    <SonnerToaster
      position={position}
      // Respect user OS setting; our tokens handle both.
      theme="system"
      // Reasonable defaults; individual calls can override.
      duration={4000}
      closeButton
      toastOptions={{
        // Sonner accepts className strings — we consume Tailwind utilities that
        // resolve to CSS vars, so light/dark swap for free.
        classNames: {
          toast: `${styleBase} bg-elevated border-border-default text-primary`,
          title: 'font-medium text-primary',
          description: 'text-secondary text-12',
          success: '!border-status-green',
          error:   '!border-status-red',
          warning: '!border-status-amber',
          info:    '!border-brand',
          actionButton: 'bg-brand text-on-brand rounded-input px-8 py-4 text-12',
          cancelButton: 'text-secondary text-12',
        },
      }}
    />
  )
}

/** Re-exported for one-import ergonomics in feature code. */
export const toast = sonnerToast
