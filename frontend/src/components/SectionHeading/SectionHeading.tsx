import { type ReactNode } from 'react'

/**
 * SectionHeading — page-section h2 with the standard display tracking.
 * Shared so pages don't each keep a local copy (AgentPage uses it today;
 * Project.tsx still carries a local duplicate slated for migration).
 */
export function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h2
      className="text-20 font-semibold text-primary mb-16"
      style={{ letterSpacing: '-0.022em' }}
    >
      {children}
    </h2>
  )
}
