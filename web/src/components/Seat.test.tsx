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
    // Card components render <span data-card="..."> (one per hole card)
    expect(container.querySelectorAll('[data-card]').length).toBe(2)
  })

  it('renders a chip beside lastAction when amount provided', () => {
    const { container } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={9100}
            status="in_hand" holeCards="face-down"
            lastAction="raise_to 900" lastActionAmount={900} />
    )
    expect(container.querySelector('[data-chip]')).not.toBeNull()
    expect(container.textContent).toContain('900')
  })

  it('does not render a chip for fold (no amount)', () => {
    const { container } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={9100}
            status="folded" holeCards="face-down"
            lastAction="fold" />
    )
    expect(container.querySelector('[data-chip]')).toBeNull()
  })
})
