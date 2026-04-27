import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { PnlChart } from './PnlChart'

describe('PnlChart', () => {
  it('renders empty state when no series', () => {
    const { getByText } = render(<PnlChart series={[]} currentHandIdx={0} />)
    expect(getByText(/no PnL data/i)).toBeDefined()
  })

  it('renders one legend dot per seat', () => {
    const series = [
      { seat: 0, values: [0, 100, 50] },
      { seat: 1, values: [0, -50, 100] },
      { seat: 2, values: [0, -50, -150] },
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    expect(container.querySelectorAll('[data-pnl-seat]').length).toBe(3)
  })

  it('renders chart caption with viewing hand', () => {
    const series = [{ seat: 0, values: [0, 100, 200] }]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    expect(container.textContent).toMatch(/cumulative PnL/i)
    expect(container.textContent).toMatch(/viewing hand 1/i)
  })

  it('shows last cumulative value with formatted sign', () => {
    const series = [
      { seat: 0, values: [0, 50, 200] },
      { seat: 1, values: [0, -100, -300] },
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={2} />)
    const text = container.textContent ?? ''
    // legend label is "s{N}" + signed value (with unicode minus for negatives)
    expect(text).toMatch(/s0\s*\+200/)
    expect(text).toMatch(/s1\s*[-−]300/)
  })
})
