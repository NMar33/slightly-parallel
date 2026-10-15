/** Small shared controls for the studio panels. */

import type { ReactNode } from 'react'

function Label({ children }: { children: ReactNode }) {
  return <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{children}</div>
}

export function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-8 border-t border-border-subtle pt-12 first:border-0 first:pt-0">
      <Label>{title}</Label>
      {children}
    </section>
  )
}

export function Seg<T extends string | number>({
  value, options, onChange, format, title,
}: {
  value: T
  options: readonly T[]
  onChange: (v: T) => void
  format?: (v: T) => string
  title?: (v: T) => string
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={String(o)}
          type="button"
          title={title?.(o)}
          onClick={() => onChange(o)}
          className={`rounded-input border px-8 py-2 text-11 font-mono transition-colors ${
            o === value
              ? 'border-brand text-primary bg-elevated'
              : 'border-border-subtle text-tertiary hover:text-primary'
          }`}
        >
          {format ? format(o) : String(o)}
        </button>
      ))}
    </div>
  )
}

export function Check({
  on, onChange, children, hint,
}: {
  on: boolean
  onChange: (v: boolean) => void
  children: ReactNode
  hint?: string
}) {
  return (
    <label className="flex items-start gap-6 text-12 cursor-pointer">
      <input
        type="checkbox"
        checked={on}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-2 accent-[var(--brand)]"
      />
      <span>
        <span className="text-primary">{children}</span>
        {hint ? <span className="block text-10 text-tertiary">{hint}</span> : null}
      </span>
    </label>
  )
}

export function Field({
  label, value, onChange, placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-input border border-border-subtle bg-base px-8 py-4 text-12 text-primary placeholder:text-tertiary"
      />
    </label>
  )
}
