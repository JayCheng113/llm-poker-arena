import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Chip } from './Chip'

describe('Chip', () => {
  it('renders a circle with denomination label', () => {
    const { getByText } = render(<Chip denomination={100} />)
    expect(getByText('100')).toBeDefined()
  })

  it('different denominations get different colors', () => {
    const small = render(<Chip denomination={1} />)
    const large = render(<Chip denomination={500} />)
    const smallStyle = small.container.firstElementChild!.getAttribute('style') ?? ''
    const largeStyle = large.container.firstElementChild!.getAttribute('style') ?? ''
    expect(smallStyle).not.toEqual(largeStyle)
  })
})
