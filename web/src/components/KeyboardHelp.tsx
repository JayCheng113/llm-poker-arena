import { useEffect } from 'react'

interface Props {
  onClose: () => void
}

interface Shortcut {
  keys: string[]
  description: string
}

const SHORTCUTS: Shortcut[] = [
  { keys: ['←'],         description: 'previous turn' },
  { keys: ['→'],         description: 'next turn' },
  { keys: ['↑'],         description: 'previous hand' },
  { keys: ['↓'],         description: 'next hand' },
  { keys: ['Space'],     description: 'play / pause auto-advance' },
]

export function KeyboardHelp({ onClose }: Props) {
  // Esc closes the modal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      data-keyboard-help
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-sm w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
          <h2 className="font-semibold text-slate-900 text-sm">keyboard shortcuts</h2>
          <button
            onClick={onClose}
            aria-label="close keyboard help"
            className="text-slate-500 hover:text-slate-800 text-xl leading-none px-2"
          >
            ×
          </button>
        </div>
        <ul className="px-4 py-3 space-y-2">
          {SHORTCUTS.map((sc) => (
            <li key={sc.description} className="flex items-center justify-between text-sm">
              <span className="text-slate-600">{sc.description}</span>
              <span className="flex gap-1">
                {sc.keys.map((k) => (
                  <kbd
                    key={k}
                    className="font-mono text-xs px-2 py-0.5 rounded border border-slate-300 bg-slate-50 text-slate-700 shadow-sm"
                  >
                    {k}
                  </kbd>
                ))}
              </span>
            </li>
          ))}
        </ul>
        <div className="px-4 py-2 border-t border-slate-200 text-[11px] text-slate-400">
          shortcuts ignored when typing in form fields
        </div>
      </div>
    </div>
  )
}
