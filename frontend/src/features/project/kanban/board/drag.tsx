/**
 * Drop targets: the slot above a card (reorder) and the column/cell zone
 * (move). Both read the dragged id from text/plain and hand it upward.
 */

import { useState, type ReactNode } from 'react'

/**
 * TaskDropSlot — wraps a single card; on drop, inserts the dragged card ABOVE
 * this card. Uses top-half-of-card sensitivity so the drop stays predictable.
 * Drops outside the card's top half bubble to the parent column zone.
 */
export function TaskDropSlot({
  onDropTask, children,
}: {
  onDropTask: (draggedId: string) => void
  children: ReactNode
}) {
  const [indicator, setIndicator] = useState(false)
  return (
    <div
      className="relative"
      onDragOver={(e) => {
        // Only capture the drop when the pointer is in the upper half of the
        // card — otherwise let the column zone handle it.
        const rect = e.currentTarget.getBoundingClientRect()
        const midY = rect.top + rect.height / 2
        if (e.clientY < midY) {
          e.preventDefault()
          e.stopPropagation()
          e.dataTransfer.dropEffect = 'move'
          if (!indicator) setIndicator(true)
        } else if (indicator) {
          setIndicator(false)
        }
      }}
      onDragLeave={() => setIndicator(false)}
      onDrop={(e) => {
        const rect = e.currentTarget.getBoundingClientRect()
        const midY = rect.top + rect.height / 2
        if (e.clientY < midY) {
          e.preventDefault()
          e.stopPropagation()
          setIndicator(false)
          const id = e.dataTransfer.getData('text/plain')
          if (id) onDropTask(id)
        }
      }}
    >
      {indicator && (
        <div className="absolute -top-1 left-0 right-0 h-[2px] bg-brand rounded-bar pointer-events-none" />
      )}
      {children}
    </div>
  )
}

export function KanbanColumnDropZone({
  onDropTask, className, style, children, title, hint, label,
}: {
  onDropTask: (draggedId: string) => void
  className?: string
  style?: React.CSSProperties
  children: ReactNode
  title?: string
  /** Shown while a card hovers, for a target whose effect is not obvious. */
  hint?: string
  /** Names the column for a screen reader ("To do column"). */
  label?: string
}) {
  const [isOver, setIsOver] = useState(false)
  return (
    <div
      role={label ? 'region' : undefined}
      aria-label={label}
      style={style}
      title={title}
      className={`${className || ''} ${isOver ? 'outline outline-2 outline-brand' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        if (!isOver) setIsOver(true)
      }}
      onDragEnter={(e) => {
        e.preventDefault()
        setIsOver(true)
      }}
      onDragLeave={(e) => {
        // Only unset when actually leaving the container (not entering a child).
        if (e.currentTarget.contains(e.relatedTarget as Node)) return
        setIsOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setIsOver(false)
        const id = e.dataTransfer.getData('text/plain')
        if (id) onDropTask(id)
      }}
    >
      {children}
      {isOver && hint && (
        <span className="ml-auto text-10 font-mono text-brand normal-case tracking-normal" style={{ fontSize: 9 }}>
          {hint}
        </span>
      )}
    </div>
  )
}
