import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { WithContents } from './WithContents'

describe('the contents rail', () => {
  it('lists every item and points each link at its section', () => {
    render(
      <WithContents
        label="On this page"
        items={[
          { id: 'capture', text: 'How capture works' },
          { id: 'files', text: 'Where the data lives', note: '4' },
        ]}
      >
        <section id="capture">the hook</section>
        <section id="files">the files</section>
      </WithContents>,
    )
    const rail = screen.getByRole('navigation', { name: 'On this page' })
    const links = rail.querySelectorAll('a')
    expect([...links].map((a) => a.getAttribute('href'))).toEqual(['#capture', '#files'])
    expect(rail).toHaveTextContent('How capture works')
    expect(rail).toHaveTextContent('Where the data lives')
    expect(rail).toHaveTextContent('4')
    expect(screen.getByText('the hook')).toBeInTheDocument()
  })

  it('renders the document when nothing is listed', () => {
    render(<WithContents label="On this page" items={[]}><p>only prose</p></WithContents>)
    expect(screen.getByText('only prose')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'On this page' }).querySelectorAll('a')).toHaveLength(0)
  })
})
