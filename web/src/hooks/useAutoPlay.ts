import { useEffect } from 'react'

interface Opts {
  isPlaying: boolean
  intervalMs: number
  onTick: () => void
}

export function useAutoPlay({ isPlaying, intervalMs, onTick }: Opts) {
  useEffect(() => {
    if (!isPlaying) return
    const id = window.setInterval(onTick, intervalMs)
    return () => window.clearInterval(id)
  }, [isPlaying, intervalMs, onTick])
}
