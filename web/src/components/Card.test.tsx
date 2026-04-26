import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Card } from './Card'

describe('Card', () => {
  it('renders a face-up card (img tag with SVG data URI)', () => {
    const { container } = render(<Card card="As" />)
    // react-free-playing-cards renders <img src="data:image/svg+xml,...">
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
  })

  it('renders face-down differently from face-up', () => {
    const faceDown = render(<Card card="face-down" />)
    const faceUp = render(<Card card="As" />)
    const imgDown = faceDown.container.querySelector('img')
    const imgUp = faceUp.container.querySelector('img')
    expect(imgDown).not.toBeNull()
    expect(imgUp).not.toBeNull()
    expect(imgDown!.outerHTML).not.toEqual(imgUp!.outerHTML)
  })
})
