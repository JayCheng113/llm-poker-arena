import { Card } from './Card'
import { ProviderBadge } from './ProviderBadge'
import { shortAgentLabel } from './agentLabel'
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
  agentId?: string  // meta.seat_assignment[seatIdx], e.g. "anthropic:claude-haiku-4-5"
}

export function Seat({
  seatIdx, positionLabel, stack, status, holeCards,
  lastAction, lastActionAmount, isActive, agentId,
}: Props) {
  const folded = status === 'folded'
  const allIn = status === 'all_in'
  const label = agentId ? shortAgentLabel(agentId) : 'unknown'

  return (
    <div
      data-seat={seatIdx}
      data-active={isActive ? '1' : undefined}
      className={[
        'flex flex-col gap-1 px-2 pt-1.5 pb-2 rounded-lg w-28',
        'bg-white border shadow-sm',
        isActive
          ? 'border-indigo-500 ring-2 ring-indigo-200 animate-pulse-ring'
          : 'border-slate-200',
        folded ? 'opacity-50' : '',
      ].join(' ')}
    >
      {/* Provider header */}
      <div className="flex items-center gap-1 min-w-0">
        {agentId && <ProviderBadge agentId={agentId} size={14} />}
        <span className="text-[11px] font-medium text-slate-700 truncate">
          {label}
        </span>
      </div>

      {/* Position + stack */}
      <div className="flex items-baseline justify-between text-[11px]">
        <span className="text-slate-500 font-medium">
          {positionLabel} <span className="text-slate-300">·</span> s{seatIdx}
        </span>
        <span
          className={`font-mono tabular-nums font-semibold ${
            folded ? 'text-slate-400' : 'text-slate-900'
          }`}
        >
          {stack.toLocaleString()}
        </span>
      </div>

      {/* Hole cards */}
      <div className="flex justify-center gap-1 mt-0.5">
        {holeCards === 'face-down' ? (
          <>
            <Card card="face-down" width={28} />
            <Card card="face-down" width={28} />
          </>
        ) : (
          <>
            <Card card={holeCards[0]} width={28} />
            <Card card={holeCards[1]} width={28} />
          </>
        )}
      </div>

      {/* Status / last action */}
      {(folded || allIn || lastAction) && (
        <div className="flex justify-center mt-0.5 min-h-[18px]">
          {folded ? (
            <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
              folded
            </span>
          ) : allIn ? (
            <span className="text-[10px] uppercase tracking-wider text-amber-600 font-semibold">
              all-in
            </span>
          ) : lastAction ? (
            <span
              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 truncate max-w-full"
              title={lastAction}
            >
              {lastAction}
              {lastActionAmount !== undefined && lastActionAmount > 0
                ? ''
                : ''}
            </span>
          ) : null}
        </div>
      )}
    </div>
  )
}
