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
    const series = [{ seat: 0, values: [10000, 10100, 10200] }]
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    expect(container.textContent).toMatch(/stack trajectory/i)
    expect(container.textContent).toMatch(/viewing hand 1/i)
    expect(container.textContent).toMatch(/starting 10,?000/i)
  })

  it('shows delta from starting stack with formatted sign in legend', () => {
    const series = [
      { seat: 0, values: [10000, 10050, 10200] },  // +200
      { seat: 1, values: [10000, 9900, 9700] },    // -300
    ]
    const { container } = render(<PnlChart series={series} currentHandIdx={2} />)
    const text = container.textContent ?? ''
    expect(text).toMatch(/s0\s*\+200/)
    expect(text).toMatch(/s1\s*[-−]300/)
  })

  it('legend tracks the currently viewed hand cursor (codex NIT-3)', () => {
    // Legend should reflect mid-session state, not the final outcome,
    // so users scrubbing back through hands see live values.
    const series = [
      { seat: 0, values: [10000, 10050, 10200] },
      { seat: 1, values: [10000, 9900, 9700] },
    ]
    // cursor at hand 1 (the middle): s0 should show +50, s1 -100
    const { container } = render(<PnlChart series={series} currentHandIdx={1} />)
    const text = container.textContent ?? ''
    expect(text).toMatch(/s0\s*\+50/)
    expect(text).toMatch(/s1\s*[-−]100/)
  })

  it('legend cursor clamps when currentHandIdx > numHands-1', () => {
    const series = [{ seat: 0, values: [10000, 10500] }]
    // currentHandIdx=99 (past end) — should clamp to last hand (idx=1)
    const { container } = render(<PnlChart series={series} currentHandIdx={99} />)
    expect(container.textContent).toMatch(/s0\s*\+500/)
  })
})
