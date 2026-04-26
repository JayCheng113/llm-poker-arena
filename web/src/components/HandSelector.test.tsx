import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { HandSelector } from './HandSelector'

describe('HandSelector', () => {
  it('shows current hand id', () => {
    const { getAllByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={vi.fn()} />
    )
    // "hand 3" appears in both the bold header AND the dropdown option
    expect(getAllByText(/hand 3/i).length).toBeGreaterThanOrEqual(1)
  })

  it('clicking next calls onSelect with current+1', () => {
    const onSelect = vi.fn()
    const { getByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={onSelect} />
    )
    fireEvent.click(getByText(/next/i))
    expect(onSelect).toHaveBeenCalledWith(4)
  })

  it('clicking prev calls onSelect with current-1', () => {
    const onSelect = vi.fn()
    const { getByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={onSelect} />
    )
    fireEvent.click(getByText(/prev/i))
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('next button disabled at last hand', () => {
    const onSelect = vi.fn()
    const { getByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={5} onSelect={onSelect} />
    )
    const nextBtn = getByText(/next/i) as HTMLButtonElement
    expect(nextBtn.disabled).toBe(true)
  })
})
