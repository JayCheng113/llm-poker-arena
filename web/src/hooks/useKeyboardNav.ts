import { useEffect } from 'react'

export interface NavTargets {
  onPrevTurn: () => void
  onNextTurn: () => void
  onPrevHand: () => void
  onNextHand: () => void
  onTogglePlay?: () => void
}

function isFormField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target.isContentEditable
  )
}

export function useKeyboardNav(targets: NavTargets, enabled: boolean = true) {
  useEffect(() => {
    if (!enabled) return
    const handler = (e: KeyboardEvent) => {
      if (isFormField(e.target)) return
      switch (e.key) {
        case 'ArrowLeft':
          targets.onPrevTurn(); e.preventDefault(); break
        case 'ArrowRight':
          targets.onNextTurn(); e.preventDefault(); break
        case 'ArrowUp':
          targets.onPrevHand(); e.preventDefault(); break
        case 'ArrowDown':
          targets.onNextHand(); e.preventDefault(); break
        case ' ':
          if (targets.onTogglePlay) { targets.onTogglePlay(); e.preventDefault() }
          break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [targets, enabled])
}
