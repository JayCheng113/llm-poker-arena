import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { ActionTimeline } from './ActionTimeline'

const turns = [
  { actor: 3, actionLabel: 'raise 300' },
  { actor: 4, actionLabel: 'fold' },
  { actor: 5, actionLabel: 'call' },
]

describe('ActionTimeline', () => {
  it('renders one card per turn', () => {
    const { getByText } = render(
      <ActionTimeline turns={turns} currentTurnIdx={0} onSeek={vi.fn()} />
    )
    expect(getByText(/raise 300/)).toBeDefined()
    expect(getByText(/fold/)).toBeDefined()
    expect(getByText(/call/)).toBeDefined()
  })

  it('highlights current turn', () => {
    const { container } = render(
      <ActionTimeline turns={turns} currentTurnIdx={1} onSeek={vi.fn()} />
    )
    const items = container.querySelectorAll('[data-turn-idx]')
    expect(items[1].className).toContain('ring-')
  })

  it('clicking a card calls onSeek with that index', () => {
    const onSeek = vi.fn()
    const { container } = render(
      <ActionTimeline turns={turns} currentTurnIdx={0} onSeek={onSeek} />
    )
    const items = container.querySelectorAll('[data-turn-idx]')
    fireEvent.click(items[2])
    expect(onSeek).toHaveBeenCalledWith(2)
  })
})
