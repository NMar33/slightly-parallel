import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// The editor reads its task into state once, like the real one.
vi.mock('./TaskEditor', () => ({
  TaskAddModal: ({ existingTask }: { existingTask?: { id: string; title: string } | null }) => {
    const [title] = useState(existingTask?.title ?? '')
    return <div>{`editing ${existingTask?.id ?? 'new'}: ${title}`}</div>
  },
}))

import { TaskAddModal } from './TaskWindow'

const props = { projectCode: 'alpha', initialStatus: 'todo', onClose: () => {}, onSaved: () => {} }

describe('TaskAddModal', () => {
  it('reads the new task when an open window is handed another one', async () => {
    const { rerender } = render(<TaskAddModal {...props} existingTask={{ id: 'tk_a', title: 'A' } as never} />)
    expect(await screen.findByText('editing tk_a: A')).toBeInTheDocument()
    rerender(<TaskAddModal {...props} existingTask={{ id: 'tk_b', title: 'B' } as never} />)
    expect(await screen.findByText('editing tk_b: B')).toBeInTheDocument()
  })
})
