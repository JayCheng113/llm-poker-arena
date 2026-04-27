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
    expect(container.querySelectorAll('[data-seat]').length).toBe(3)
  })

  it('renders chart wrapper with title and current-hand caption', () => {
    const series = [{ seat: 0, values: [0, 100, 200] }]
    const { getByText } = render(<PnlChart series={series} currentHandIdx={1} />)
    expect(getByText(/cumulative PnL/i)).toBeDefined()
    expect(getByText(/currently viewing hand 1/i)).toBeDefined()
  })

  it('shows last cumulative value with formatted sign', () => {
    const series = [
      { seat: 0, values: [0, 50, 200] },
      { seat: 1, values: [0, -100, -300] },
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={2} />)
    const text = container.textContent ?? ''
    expect(text).toMatch(/seat 0\s*\+200/)
    // formatted with the unicode minus sign for negatives
    expect(text).toMatch(/seat 1\s*[-−]300/)
  })

  it('singularizes "hand" when only one data point', () => {
    const series = [{ seat: 0, values: [0] }]
    const { getByText } = render(<PnlChart series={series} currentHandIdx={0} />)
    expect(getByText(/over 1 hand /i)).toBeDefined()
  })
})
