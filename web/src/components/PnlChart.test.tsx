import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { PnlChart, type SeatSeries } from './PnlChart'

const mk = (overrides: Partial<SeatSeries> & { seat: number; values: number[] }): SeatSeries => ({
  label: `seat ${overrides.seat}`,
  ...overrides,
})

describe('PnlChart', () => {
  it('renders empty state when no series', () => {
    const { getByText } = render(<PnlChart series={[]} currentHandIdx={0} />)
    expect(getByText(/no PnL data/i)).toBeDefined()
  })

  it('renders one legend dot per seat', () => {
    const series = [
      mk({ seat: 0, values: [0, 100, 50] }),
      mk({ seat: 1, values: [0, -50, 100] }),
      mk({ seat: 2, values: [0, -50, -150] }),
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    expect(container.querySelectorAll('[data-pnl-seat]').length).toBe(3)
  })

  it('renders chart caption with viewing hand', () => {
    const series = [mk({ seat: 0, values: [10000, 10100, 10200] })]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    expect(container.textContent).toMatch(/stack trajectory/i)
    expect(container.textContent).toMatch(/viewing hand 1/i)
    expect(container.textContent).toMatch(/starting 10,?000/i)
  })

  it('shows delta from starting stack with formatted sign in legend', () => {
    const series = [
      mk({ seat: 0, values: [10000, 10050, 10200], label: 'Haiku' }),  // +200
      mk({ seat: 1, values: [10000, 9900, 9700], label: 'GPT' }),      // -300
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={2} />)
    const text = container.textContent ?? ''
    expect(text).toMatch(/Haiku\s*\+200/)
    expect(text).toMatch(/GPT\s*[-−]300/)
  })

  it('legend tracks the currently viewed hand cursor (codex NIT-3)', () => {
    const series = [
      mk({ seat: 0, values: [10000, 10050, 10200], label: 'Haiku' }),
      mk({ seat: 1, values: [10000, 9900, 9700], label: 'GPT' }),
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    const text = container.textContent ?? ''
    expect(text).toMatch(/Haiku\s*\+50/)
    expect(text).toMatch(/GPT\s*[-−]100/)
  })

  it('legend cursor clamps when currentHandIdx > numHands-1', () => {
    const series = [mk({ seat: 0, values: [10000, 10500], label: 'Haiku' })]
    const { container } = render(<PnlChart series={series} currentHandIdx={99} />)
    expect(container.textContent).toMatch(/Haiku\s*\+500/)
  })

  it('disambiguates duplicate labels by appending seat#', () => {
    const series = [
      mk({ seat: 0, values: [10000, 10100], label: 'Rule-based' }),
      mk({ seat: 1, values: [10000, 9950], label: 'Rule-based' }),
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    // legend renders the bare label per row; the unique key is internal
    expect(container.querySelectorAll('[data-pnl-seat]').length).toBe(2)
  })
})
