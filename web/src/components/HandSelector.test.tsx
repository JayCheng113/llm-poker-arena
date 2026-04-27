import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { HandSelector } from './HandSelector'

describe('HandSelector', () => {
  it('shows current hand id', () => {
    const { getAllByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={vi.fn()} />
    )
    // "hand 3" appears in the dropdown option
    expect(getAllByText(/hand 3/i).length).toBeGreaterThanOrEqual(1)
  })

  it('clicking next calls onSelect with current+1', () => {
    const onSelect = vi.fn()
    const { getByLabelText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={onSelect} />
    )
    fireEvent.click(getByLabelText('next hand'))
    expect(onSelect).toHaveBeenCalledWith(4)
  })

  it('clicking prev calls onSelect with current-1', () => {
    const onSelect = vi.fn()
    const { getByLabelText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={onSelect} />
    )
    fireEvent.click(getByLabelText('previous hand'))
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('next button disabled at last hand', () => {
    const onSelect = vi.fn()
    const { getByLabelText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={5} onSelect={onSelect} />
    )
    const nextBtn = getByLabelText('next hand') as HTMLButtonElement
    expect(nextBtn.disabled).toBe(true)
  })

  it('shows brand title', () => {
    const { getByText } = render(
      <HandSelector handIds={[0, 1, 2]} currentHandId={0} onSelect={vi.fn()} />
    )
    expect(getByText(/LLM Poker Arena/i)).toBeDefined()
  })
})
