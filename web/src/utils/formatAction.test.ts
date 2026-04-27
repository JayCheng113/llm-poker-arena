import { describe, it, expect } from 'vitest'
import { formatActionLabel } from './formatAction'

describe('formatActionLabel', () => {
  it('formats fold as "Fold"', () => {
    expect(formatActionLabel({ type: 'fold' })).toBe('Fold')
  })

  it('formats check as "Check"', () => {
    expect(formatActionLabel({ type: 'check' })).toBe('Check')
  })

  it('formats call as "Call"', () => {
    expect(formatActionLabel({ type: 'call' })).toBe('Call')
  })

  it('formats bet with amount as "Bet 250"', () => {
    expect(formatActionLabel({ type: 'bet', amount: 250 })).toBe('Bet 250')
  })

  it('formats raise_to with amount as "Raise to 900"', () => {
    expect(formatActionLabel({ type: 'raise_to', amount: 900 })).toBe('Raise to 900')
  })

  it('formats large amounts with thousands separator', () => {
    expect(formatActionLabel({ type: 'raise_to', amount: 10000 })).toBe('Raise to 10,000')
  })

  it('drops the amount on all_in (already implied by the label)', () => {
    expect(formatActionLabel({ type: 'all_in', amount: 9700 })).toBe('All-in')
  })

  it('drops zero amounts (no "Bet 0")', () => {
    expect(formatActionLabel({ type: 'bet', amount: 0 })).toBe('Bet')
  })

  it('omits amount when undefined', () => {
    expect(formatActionLabel({ type: 'raise_to' })).toBe('Raise to')
  })
})
