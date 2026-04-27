import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useAutoPlay } from './useAutoPlay'

describe('useAutoPlay', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('does not tick when isPlaying=false', () => {
    const onTick = vi.fn()
    renderHook(() => useAutoPlay({ isPlaying: false, intervalMs: 100, onTick }))
    vi.advanceTimersByTime(500)
    expect(onTick).not.toHaveBeenCalled()
  })

  it('ticks at intervalMs while playing', () => {
    const onTick = vi.fn()
    renderHook(() => useAutoPlay({ isPlaying: true, intervalMs: 100, onTick }))
    vi.advanceTimersByTime(350)
    expect(onTick).toHaveBeenCalledTimes(3)
  })

  it('clears interval on unmount', () => {
    const onTick = vi.fn()
    const { unmount } = renderHook(
      () => useAutoPlay({ isPlaying: true, intervalMs: 100, onTick })
    )
    unmount()
    vi.advanceTimersByTime(500)
    expect(onTick).not.toHaveBeenCalled()
  })

  it('stops ticking when isPlaying flips to false', () => {
    const onTick = vi.fn()
    const { rerender } = renderHook(
      ({ playing }) => useAutoPlay({ isPlaying: playing, intervalMs: 100, onTick }),
      { initialProps: { playing: true } }
    )
    vi.advanceTimersByTime(150)
    expect(onTick).toHaveBeenCalledTimes(1)
    rerender({ playing: false })
    vi.advanceTimersByTime(500)
    expect(onTick).toHaveBeenCalledTimes(1)
  })
})
