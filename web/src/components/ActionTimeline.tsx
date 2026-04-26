interface TurnInfo {
  actor: number
  actionLabel: string
}

interface Props {
  turns: TurnInfo[]
  currentTurnIdx: number
  onSeek: (turnIdx: number) => void
}

export function ActionTimeline({ turns, currentTurnIdx, onSeek }: Props) {
  return (
    <div className="flex gap-2 p-3 overflow-x-auto bg-slate-200 border-t border-slate-300">
      {turns.map((t, i) => {
        const active = i === currentTurnIdx
        return (
          <button
            key={i}
            data-turn-idx={i}
            onClick={() => onSeek(i)}
            className={`flex-none px-3 py-2 rounded text-xs bg-white border border-slate-400 hover:bg-slate-100 ${
              active ? 'ring-2 ring-yellow-500 font-bold' : ''
            }`}
          >
            <div className="text-slate-500">{i + 1}</div>
            <div>seat {t.actor}</div>
            <div className="text-slate-700">{t.actionLabel}</div>
          </button>
        )
      })}
    </div>
  )
}
