interface Props {
  handIds: number[]
  currentHandId: number
  onSelect: (handId: number) => void
}

export function HandSelector({ handIds, currentHandId, onSelect }: Props) {
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
      <select
        value={currentHandId}
        onChange={(e) => onSelect(Number(e.target.value))}
        className="ml-auto bg-slate-600 border border-slate-500 rounded px-2 py-1 text-sm"
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
