/**
 * The lens variant is what the entry pages introduce themselves with: the
 * name with its icon, how many entries are on the page, what narrows the
 * list, and the controls pushed right.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Package } from 'lucide-react'

import { PageHeader } from './PageHeader'

describe('PageHeader, lens', () => {
  it('names the page, counts what is on it, and holds the filter and the controls', () => {
    render(
      <PageHeader variant="lens" icon={Package} title="Artifacts" count={12}
        actions={<button type="button">Add a folder</button>}>
        <span>slightly-parallel</span>
      </PageHeader>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Artifacts' })).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('slightly-parallel')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add a folder' })).toBeInTheDocument()
  })

  it('leaves the count out when a page does not count', () => {
    render(<PageHeader variant="lens" title="Tour" />)
    expect(screen.getByRole('heading', { level: 1, name: 'Tour' })).toBeInTheDocument()
    expect(document.querySelector('.tabular')).toBeNull()
  })
})
