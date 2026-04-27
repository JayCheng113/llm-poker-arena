import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboardNav } from './useKeyboardNav'

function fire(key: string, target?: EventTarget) {
  const evt = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
  if (target) {
    Object.defineProperty(evt, 'target', { value: target })
  }
  window.dispatchEvent(evt)
  return evt
}

function makeTargets() {
  return {
    onPrevTurn: vi.fn(),
    onNextTurn: vi.fn(),
    onPrevHand: vi.fn(),
    onNextHand: vi.fn(),
    onTogglePlay: vi.fn(),
  }
}

describe('useKeyboardNav', () => {
  it('ArrowLeft triggers onPrevTurn', () => {
    const t = makeTargets()
    renderHook(() => useKeyboardNav(t))
    fire('ArrowLeft')
    expect(t.onPrevTurn).toHaveBeenCalledTimes(1)
  })

  it('ArrowRight triggers onNextTurn', () => {
    const t = makeTargets()
    renderHook(() => useKeyboardNav(t))
    fire('ArrowRight')
    expect(t.onNextTurn).toHaveBeenCalledTimes(1)
  })

  it('ArrowUp/Down triggers prev/next hand', () => {
    const t = makeTargets()
    renderHook(() => useKeyboardNav(t))
    fire('ArrowUp')
    fire('ArrowDown')
    expect(t.onPrevHand).toHaveBeenCalledTimes(1)
    expect(t.onNextHand).toHaveBeenCalledTimes(1)
  })

  it('Space triggers onTogglePlay', () => {
    const t = makeTargets()
    renderHook(() => useKeyboardNav(t))
    fire(' ')
    expect(t.onTogglePlay).toHaveBeenCalledTimes(1)
  })

  it('ignores keys when typing in input field', () => {
    const t = makeTargets()
    renderHook(() => useKeyboardNav(t))
    const input = document.createElement('input')
    document.body.appendChild(input)
    fire('ArrowLeft', input)
    expect(t.onPrevTurn).not.toHaveBeenCalled()
    document.body.removeChild(input)
  })

  it('cleans up listener on unmount', () => {
    const t = makeTargets()
    const { unmount } = renderHook(() => useKeyboardNav(t))
    unmount()
    fire('ArrowLeft')
    expect(t.onPrevTurn).not.toHaveBeenCalled()
  })

  it('does nothing when disabled', () => {
    const t = makeTargets()
    renderHook(() => useKeyboardNav(t, false))
    fire('ArrowLeft')
    expect(t.onPrevTurn).not.toHaveBeenCalled()
  })
})
