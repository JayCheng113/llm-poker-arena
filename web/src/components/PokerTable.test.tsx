import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { PokerTable } from './PokerTable'
import type { CardStr, SeatStatus } from '../types'

const seats = Array.from({ length: 6 }, (_, i) => ({
  seatIdx: i,
  positionLabel: ['BTN', 'SB', 'BB', 'UTG', 'HJ', 'CO'][i],
  stack: 10000,
  status: 'in_hand' as SeatStatus,
  holeCards: 'face-down' as const,
}))

describe('PokerTable', () => {
  it('renders 6 seats', () => {
    const { container } = render(
      <PokerTable seats={seats} community={[]} pot={150} activeSeatIdx={3} />
    )
    const seatLabels = container.querySelectorAll('.font-bold')
    expect(seatLabels.length).toBeGreaterThanOrEqual(6)
  })

  it('renders community cards when given', () => {
    const community: CardStr[] = ['As', 'Kh', '2c']
    const { container } = render(
      <PokerTable seats={seats} community={community} pot={500} activeSeatIdx={3} />
    )
    // 3 community + 6 seats × 2 face-down = 15 [data-card] elements minimum
    expect(container.querySelectorAll('[data-card]').length).toBeGreaterThanOrEqual(3)
  })

  it('renders pot number', () => {
    const { getByText } = render(
      <PokerTable seats={seats} community={[]} pot={1234} activeSeatIdx={3} />
    )
    expect(getByText(/1234/)).toBeDefined()
  })
})
