import { t } from '../i18n/scope/shell'

export function RadioOption<T extends string>({ value, label, hint, picked, clearable, onChange, className }: {
  value: T
  label: string
  hint?: string
  picked: boolean
  clearable: boolean
  onChange: (value: T) => void
  className: string
}) {
  return (
    <button type="button" role="radio" aria-checked={picked}
      title={hint ?? (picked && clearable ? t('Click again to clear') : undefined)}
      onClick={() => onChange(picked && clearable ? ('' as T) : value)}
      className={className}
    >
      {label}
    </button>
  )
}
