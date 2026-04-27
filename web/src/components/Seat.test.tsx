import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Seat } from './Seat'
import type { CardStr } from '../types'

describe('Seat', () => {
  it('renders position label + seat index + stack', () => {
    const { getByText } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={10000}
            status="in_hand" holeCards="face-down" />
    )
    expect(getByText(/UTG/)).toBeDefined()
    expect(getByText(/s3/)).toBeDefined()
    expect(getByText('10,000')).toBeDefined()
  })

  it('renders folded status as a label', () => {
    const { getByText } = render(
      <Seat seatIdx={0} positionLabel="BTN" stack={9700}
            status="folded" holeCards="face-down" />
    )
    expect(getByText(/folded/i)).toBeDefined()
  })

  it('renders revealed hole cards (showdown)', () => {
    const cards: [CardStr, CardStr] = ['Qd', 'Qc']
    const { container } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={9700}
            status="in_hand" holeCards={cards} />
    )
    expect(container.querySelectorAll('[data-card]').length).toBe(2)
  })

  it('renders lastAction text in a badge', () => {
    const { container, getByText } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={9100}
            status="in_hand" holeCards="face-down"
            lastAction="raise_to 900" lastActionAmount={900} />
    )
    expect(getByText('raise_to 900')).toBeDefined()
    expect(container.textContent).toContain('900')
  })

  it('renders provider badge when agentId provided', () => {
    const { container, getByText } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={10000}
            status="in_hand" holeCards="face-down"
            agentId="anthropic:claude-haiku-4-5" />
    )
    expect(container.querySelector('svg')).not.toBeNull()
    expect(getByText(/Haiku 4.5/)).toBeDefined()
  })

  it('shows "unknown" label when agentId omitted', () => {
    const { getByText } = render(
      <Seat seatIdx={0} positionLabel="BTN" stack={10000}
            status="in_hand" holeCards="face-down" />
    )
    expect(getByText('unknown')).toBeDefined()
  })

  it('marks active seat via data-active attribute', () => {
    const { container } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={10000}
            status="in_hand" holeCards="face-down" isActive />
    )
    expect(container.querySelector('[data-active="1"]')).not.toBeNull()
  })
})
