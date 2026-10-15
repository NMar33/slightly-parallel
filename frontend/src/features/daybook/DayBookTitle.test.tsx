import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Telescope } from 'lucide-react'

import { DayBookTitle } from './DayBookTitle'
import { NoEntriesYet } from './NoEntriesYet'

describe('the day book title row', () => {
  it('names the page, counts what is on show, and asks in the page words', () => {
    render(<DayBookTitle icon={Telescope} name="Scans" count={7} projects={['slightly-parallel']} project="slightly-parallel"
      onProject={() => {}} q="" onFind={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Scans' })).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByLabelText('Find in scans')).toBeInTheDocument()
  })

  it('offers the projects that have an entry, and no All', () => {
    const onProject = vi.fn()
    render(<DayBookTitle icon={Telescope} name="Scans" count={2} projects={['slightly-parallel', 'atlas']} project="slightly-parallel"
      onProject={onProject} q="" onFind={() => {}} />)
    const picks = screen.getAllByRole('radio').map((b) => b.textContent)
    expect(picks).toEqual(['slightly-parallel', 'atlas'])
    screen.getByRole('radio', { name: 'atlas' }).click()
    expect(onProject).toHaveBeenCalledWith('atlas')
  })

  it('hides the picker when one project has every entry', () => {
    render(<DayBookTitle icon={Telescope} name="Scans" count={2} projects={['slightly-parallel']} project="slightly-parallel"
      onProject={() => {}} q="" onFind={() => {}} />)
    expect(screen.queryByRole('radio')).toBeNull()
  })
})

describe('a day book with nothing in it', () => {
  it('says there is none, when one appears, and the command that writes one', () => {
    render(<NoEntriesYet name="scans" project="orchard" command="#scan" verb="make one"
      when="When an agent makes a scan in this project" />)
    expect(screen.getByText('There are no scans in orchard.')).toBeInTheDocument()
    expect(screen.getByText(/you will see it here/)).toBeInTheDocument()
    expect(screen.getByText('#scan')).toBeInTheDocument()
  })
})
