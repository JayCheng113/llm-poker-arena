import type { SessionManifest } from '../types'

interface Props {
  handIds: number[]
  currentHandId: number
  onSelect: (handId: number) => void
  isPlaying?: boolean
  onTogglePlay?: () => void
  playbackSpeed?: number
  onChangeSpeed?: (s: number) => void
  devMode?: boolean
  onToggleDev?: () => void
  onOpenSummary?: () => void
  manifest?: SessionManifest | null
  currentSessionId?: string
  onSelectSession?: (id: string) => void
}

export function HandSelector({
  handIds, currentHandId, onSelect, isPlaying, onTogglePlay,
  playbackSpeed, onChangeSpeed,
  devMode, onToggleDev, onOpenSummary,
  manifest, currentSessionId, onSelectSession,
}: Props) {
  const idx = handIds.indexOf(currentHandId)
  const canPrev = idx > 0
  const canNext = idx >= 0 && idx < handIds.length - 1
  return (
    <div className="flex items-center gap-3 p-3 bg-slate-700 text-white">
      <button
        onClick={() => canPrev && onSelect(handIds[idx - 1])}
        disabled={!canPrev}
        className="px-3 py-1 rounded bg-slate-500 hover:bg-slate-400 disabled:opacity-40"
      >
        ← prev
      </button>
      <div className="font-bold">hand {currentHandId}</div>
      <span className="text-slate-300 text-sm">
        ({idx + 1} / {handIds.length})
      </span>
      <button
        onClick={() => canNext && onSelect(handIds[idx + 1])}
        disabled={!canNext}
        className="px-3 py-1 rounded bg-slate-500 hover:bg-slate-400 disabled:opacity-40"
      >
        next →
      </button>
      {onTogglePlay && (
        <button
          onClick={onTogglePlay}
          aria-label={isPlaying ? 'pause' : 'play'}
          className={`px-3 py-1 rounded font-semibold ${
            isPlaying
              ? 'bg-amber-500 hover:bg-amber-400 text-slate-900'
              : 'bg-emerald-600 hover:bg-emerald-500 text-white'
          }`}
        >
          {isPlaying ? '⏸ pause' : '▶ play'}
        </button>
      )}
      {onChangeSpeed && (
        <select
          value={String(playbackSpeed ?? 1)}
          onChange={(e) => onChangeSpeed(Number(e.target.value))}
          aria-label="playback speed"
          className="bg-slate-600 border border-slate-500 rounded px-2 py-1 text-xs"
        >
          <option value="0.5">0.5×</option>
          <option value="1">1×</option>
          <option value="2">2×</option>
          <option value="4">4×</option>
        </select>
      )}
      <span className="text-slate-400 text-xs hidden md:inline">
        ←/→ turn · ↑/↓ hand · space play
      </span>
      {onOpenSummary && (
        <button
          onClick={onOpenSummary}
          aria-label="open session summary"
          className="px-2 py-1 rounded text-xs bg-slate-600 text-slate-200 hover:bg-slate-500"
        >
          📊 summary
        </button>
      )}
      {onToggleDev && (
        <button
          onClick={onToggleDev}
          aria-label="toggle dev mode"
          title="dev mode: god-view + raw JSON viewer"
          className={`px-2 py-1 rounded text-xs font-mono ${
            devMode
              ? 'bg-fuchsia-600 text-white'
              : 'bg-slate-600 text-slate-300 hover:bg-slate-500'
          }`}
        >
          dev {devMode ? 'ON' : 'OFF'}
        </button>
      )}
      {manifest && manifest.sessions.length > 1 && onSelectSession && (
        <select
          value={currentSessionId ?? manifest.sessions[0].id}
          onChange={(e) => onSelectSession(e.target.value)}
          aria-label="select session"
          className="ml-auto bg-slate-800 border border-slate-500 rounded px-2 py-1 text-xs"
        >
          {manifest.sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      )}
      <select
        value={currentHandId}
        onChange={(e) => onSelect(Number(e.target.value))}
        aria-label="select hand"
        className={`${manifest && manifest.sessions.length > 1 ? '' : 'ml-auto'} bg-slate-600 border border-slate-500 rounded px-2 py-1 text-sm`}
      >
        {handIds.map((h) => (
          <option key={h} value={h}>
            hand {h}
          </option>
        ))}
      </select>
    </div>
  )
}
