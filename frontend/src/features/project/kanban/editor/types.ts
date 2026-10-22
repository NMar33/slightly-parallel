/*
 * Small shapes the task window's pieces share, kept here so no editor/*
 * file has to import TaskEditor.tsx (which imports them all).
 */

/** One asking row: what would be lost, and the act. */
export type Asking = { text: string; action: string; run: () => void }

/** A sprint as the picker's chips need it. */
export type SprintChip = { id: string; name: string }

/** A milestone as the window's picker reads it. */
export type MilestoneOption = { id: string; title: string; status: string; tasks: string[]; project: string }
