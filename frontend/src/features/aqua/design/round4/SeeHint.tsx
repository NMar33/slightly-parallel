/** Round 4: how to see a variant live, in one line («Зажмите Alt»), under a switch of the «Варианты» and «Схема» panels. */

import { Eye } from 'lucide-react'

export function SeeHint({ text }: { text: string }) {
  return (
    <span className="inline-flex items-start gap-4 text-11 leading-[1.35]" style={{ color: 'var(--brand)' }} data-see>
      <Eye size={11} className="shrink-0 mt-[2px]" />{text}
    </span>
  )
}
