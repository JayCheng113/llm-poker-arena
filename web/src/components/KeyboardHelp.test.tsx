import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { KeyboardHelp } from './KeyboardHelp'

describe('KeyboardHelp', () => {
  it('renders all shortcuts', () => {
    const { getByText } = render(<KeyboardHelp onClose={() => {}} />)
    expect(getByText('previous turn')).toBeDefined()
    expect(getByText('next turn')).toBeDefined()
    expect(getByText('previous hand')).toBeDefined()
    expect(getByText('next hand')).toBeDefined()
    expect(getByText('play / pause auto-advance')).toBeDefined()
  })

  it('calls onClose on backdrop click', () => {
    const onClose = vi.fn()
    const { container } = render(<KeyboardHelp onClose={onClose} />)
    fireEvent.click(container.querySelector('[data-keyboard-help]')!)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not close on inner card click', () => {
    const onClose = vi.fn()
    const { getByText } = render(<KeyboardHelp onClose={onClose} />)
    fireEvent.click(getByText('keyboard shortcuts'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('calls onClose when × button clicked', () => {
    const onClose = vi.fn()
    const { getByLabelText } = render(<KeyboardHelp onClose={onClose} />)
    fireEvent.click(getByLabelText('close keyboard help'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose on Esc key', () => {
    const onClose = vi.fn()
    render(<KeyboardHelp onClose={onClose} />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })
})
