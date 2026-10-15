import { Component, type ReactNode } from 'react'
import { t } from '../i18n/scope/shell'
import { rich } from '../i18n/rich'

/**
 * The last line of defence for a page: a component that throws while
 * rendering must cost the operator one panel, never the whole app. Without
 * this, a single unexpected payload shape white-screens everything —
 * sidebar, navigation, all of it — which is indistinguishable from the
 * dashboard being down.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; resetKey?: string },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error) {
    // The console keeps the stack; the UI keeps the message.
    console.error('page crashed:', error)
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    // Navigating to another page is a fresh start.
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null })
    }
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" data-testid="crash-screen" className="max-w-reading flex flex-col gap-12 p-24">
        <h1 className="text-20 font-semibold text-primary">{t('This page crashed')}</h1>
        <p className="text-13 text-secondary leading-relaxed">
          {rich(t('This page could not be shown. The other pages still work. The error: {error}'), {
            error: <code className="text-12 font-mono text-status-red">{String(this.state.error.message || this.state.error)}</code>,
          })}
        </p>
        <p className="text-12 text-tertiary">
          {t('If it happens again, run the data check on the Internals page.')}
        </p>
        <div className="flex items-center gap-8">
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="h-[28px] px-12 rounded-input bg-brand text-on-brand font-mono text-12 font-semibold"
          >
            {t('Try again')}
          </button>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="h-[28px] px-12 rounded-input border border-border-default text-secondary font-mono text-12"
          >
            {t('Reload the app')}
          </button>
        </div>
      </div>
    )
  }
}

/**
 * The same guard, sized for one panel: a panel that throws says so in its
 * own place, with a retry, and the panels around it keep working. `name`
 * says which panel ("Agent timeline"); `quiet` draws a single line, for
 * the top bar and the sidebar.
 */
export class PanelBoundary extends Component<
  { children: ReactNode; name: string; quiet?: boolean; resetKey?: string },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error(`panel crashed (${this.props.name}):`, error)
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    const message = String(this.state.error.message || this.state.error)
    const retry = (
      <button type="button" onClick={() => this.setState({ error: null })} className="text-brand hover:underline">
        try again
      </button>
    )
    if (this.props.quiet) {
      return (
        <span role="alert" title={message} className="text-11 font-mono text-status-red">
          {this.props.name} failed · {retry}
        </span>
      )
    }
    return (
      <div role="alert" className="rounded-card border border-border-subtle bg-surface px-16 py-12 flex flex-col gap-4">
        <span className="text-13 font-medium text-primary">{this.props.name} failed to draw.</span>
        <span className="text-12 text-secondary">
          The rest of the page still works. The error:{' '}
          <code className="text-12 font-mono text-status-red">{message}</code>
        </span>
        <span className="text-12">{retry}</span>
      </div>
    )
  }
}
