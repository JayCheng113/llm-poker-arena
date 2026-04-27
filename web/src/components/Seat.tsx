import { Card } from './Card'
import { Chip } from './Chip'
import type { CardStr, SeatStatus } from '../types'

interface Props {
  seatIdx: number
  positionLabel: string
  stack: number
  status: SeatStatus
  holeCards: 'face-down' | [CardStr, CardStr]
  lastAction?: string
  lastActionAmount?: number
  isActive?: boolean
}

export function Seat({
  seatIdx, positionLabel, stack, status, holeCards, lastAction, lastActionAmount, isActive,
}: Props) {
  const opacity = status === 'folded' ? 0.4 : 1
  const ring = isActive ? 'ring-4 ring-yellow-400 animate-pulse-ring' : ''
  return (
    <div
      className={`flex flex-col items-center gap-1 p-2 rounded bg-slate-800 text-white text-xs ${ring}`}
      style={{ opacity }}
      data-active={isActive ? '1' : undefined}
    >
      <div className="font-bold">seat {seatIdx} ({positionLabel})</div>
      <div className="text-slate-300">{stack}</div>
      {status === 'folded' && <div className="text-red-400 italic">folded</div>}
      {status === 'all_in' && <div className="text-orange-400 italic">all-in</div>}
      <div className="flex gap-1">
        {holeCards === 'face-down' ? (
          <>
            <Card card="face-down" width={36} />
            <Card card="face-down" width={36} />
          </>
        ) : (
          <>
            <Card card={holeCards[0]} width={36} />
            <Card card={holeCards[1]} width={36} />
          </>
        )}
      </div>
      {lastAction && (
        <div className="flex items-center gap-1">
          {lastActionAmount !== undefined && lastActionAmount > 0 && (
            <Chip denomination={lastActionAmount} size={20} />
          )}
          <div className="px-2 py-0.5 rounded bg-yellow-500 text-slate-900 font-semibold">
            {lastAction}
          </div>
        </div>
      )}
    </div>
  )
}
