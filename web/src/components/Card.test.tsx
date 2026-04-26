import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Card } from './Card'

describe('Card', () => {
  it('renders a face-up card with the right unicode char', () => {
    const { container } = render(<Card card="As" />)
    // Ace of spades = U+1F0A1 = 🂡
    expect(container.textContent).toBe('\u{1F0A1}')
  })

  it('renders face-down with card back char', () => {
    const { container } = render(<Card card="face-down" />)
    // Card back = U+1F0A0 = 🂠
    expect(container.textContent).toBe('\u{1F0A0}')
  })

  it('hearts and diamonds get red color', () => {
    const heart = render(<Card card="Ah" />)
    const diamond = render(<Card card="Ad" />)
    const spade = render(<Card card="As" />)
    const heartStyle = heart.container.firstElementChild!.getAttribute('style') ?? ''
    const diamondStyle = diamond.container.firstElementChild!.getAttribute('style') ?? ''
    const spadeStyle = spade.container.firstElementChild!.getAttribute('style') ?? ''
    expect(heartStyle).toContain('#dc2626') // red
    expect(diamondStyle).toContain('#dc2626')
    expect(spadeStyle).toContain('#000') // black
  })
})
