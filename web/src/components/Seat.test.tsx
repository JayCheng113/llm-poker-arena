import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Seat } from './Seat'
import type { CardStr } from '../types'

describe('Seat', () => {
  it('renders position label + stack', () => {
    const { getByText } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={10000}
            status="in_hand" holeCards="face-down" />
    )
    expect(getByText('seat 3 (UTG)')).toBeDefined()
    expect(getByText('10000')).toBeDefined()
  })

  it('renders folded status differently', () => {
    const { container } = render(
      <Seat seatIdx={0} positionLabel="BTN" stack={9700}
            status="folded" holeCards="face-down" />
    )
    expect(container.textContent).toContain('folded')
  })

  it('renders revealed hole cards (showdown)', () => {
    const cards: [CardStr, CardStr] = ['Qd', 'Qc']
    const { container } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={9700}
            status="in_hand" holeCards={cards} />
    )
    // Card components render <img> tags (one per hole card); expect 2
    expect(container.querySelectorAll('img').length).toBe(2)
  })
})
