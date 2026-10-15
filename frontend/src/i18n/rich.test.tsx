import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { rich } from './rich'

describe('rich', () => {
  it('puts parts into their slots, wherever the translation moved them', () => {
    render(<p>{rich('Вернуться к {link}, затем `код`', { link: <a href="/x">обзору</a> })}</p>)
    expect(screen.getByRole('link', { name: 'обзору' })).toBeTruthy()
    expect(document.querySelector('p')?.textContent).toBe('Вернуться к обзору, затем код')
    expect(document.querySelector('code')?.textContent).toBe('код')
  })
})
