import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { PnlChart } from './PnlChart'

describe('PnlChart', () => {
  it('renders empty state when no series', () => {
    const { container, getByText } = render(
      <PnlChart series={[]} currentHandIdx={0} />
    )
    expect(getByText(/no PnL data/i)).toBeDefined()
    expect(container.querySelector('[data-pnl-chart]')).toBeNull()
  })

  it('renders one polyline per seat', () => {
    const series = [
      { seat: 0, values: [0, 100, 50] },
      { seat: 1, values: [0, -50, 100] },
      { seat: 2, values: [0, -50, -150] },
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    expect(container.querySelectorAll('polyline[data-seat]').length).toBe(3)
  })

  it('renders the current-hand vertical marker', () => {
    const series = [{ seat: 0, values: [0, 100, 200] }]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    expect(container.querySelector('[data-current-marker]')).not.toBeNull()
  })

  it('shows last cumulative value in legend with sign', () => {
    const series = [
      { seat: 0, values: [0, 50, 200] },
      { seat: 1, values: [0, -100, -300] },
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={2} />)
    const text = container.textContent ?? ''
    expect(text).toContain('s0 +200')
    expect(text).toContain('s1 -300')
  })
})
