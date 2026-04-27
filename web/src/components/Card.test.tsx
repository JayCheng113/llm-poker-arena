import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Card } from './Card'

describe('Card', () => {
  it('renders a face-up card with rank + suit chars', () => {
    const { container } = render(<Card card="As" />)
    expect(container.textContent).toContain('A')
    expect(container.textContent).toContain('♠')
  })

  it('renders T as "10"', () => {
    const { container } = render(<Card card="Th" />)
    expect(container.textContent).toContain('10')
    expect(container.textContent).toContain('♥')
  })

  it('renders face-down with no text', () => {
    const { container } = render(<Card card="face-down" />)
    expect(container.textContent).toBe('')
    expect(container.querySelector('[data-card="face-down"]')).not.toBeNull()
  })

  it('hearts and diamonds get red color', () => {
    const heart = render(<Card card="Ah" />)
    const diamond = render(<Card card="Ad" />)
    const spade = render(<Card card="As" />)
    expect(heart.container.firstElementChild!.getAttribute('style')).toContain('#dc2626')
    expect(diamond.container.firstElementChild!.getAttribute('style')).toContain('#dc2626')
    expect(spade.container.firstElementChild!.getAttribute('style')).toContain('#000')
  })
})
