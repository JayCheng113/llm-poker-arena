import { ProviderBadge } from './ProviderBadge'
import type { ActionType, Street } from '../types'

interface TurnInfo {
  actor: number
  actionLabel: string
  actionType?: ActionType
  street?: Street
  agentId?: string
}

interface Props {
  turns: TurnInfo[]
  currentTurnIdx: number
  onSeek: (turnIdx: number) => void
}

const STREET_ORDER: Street[] = ['preflop', 'flop', 'turn', 'river']

const ACTION_TONE: Record<string, string> = {
  fold:     'text-slate-400',
  check:    'text-slate-600',
  call:     'text-indigo-600',
  bet:      'text-emerald-700 font-semibold',
  raise_to: 'text-emerald-700 font-semibold',
  all_in:   'text-amber-700 font-semibold',
}

export function ActionTimeline({ turns, currentTurnIdx, onSeek }: Props) {
  // Group turns by street, preserving original index for click handler.
  const groups: { street: Street | 'unknown'; items: { t: TurnInfo; idx: number }[] }[] = []
  for (let i = 0; i < turns.length; i++) {
    const t = turns[i]
    const street = t.street ?? 'unknown'
    const last = groups[groups.length - 1]
    if (last && last.street === street) {
      last.items.push({ t, idx: i })
    } else {
      groups.push({ street, items: [{ t, idx: i }] })
    }
  }

  return (
    <div className="flex items-stretch gap-3 px-3 py-2 overflow-x-auto bg-slate-50 border-t border-slate-200">
      {groups.map((g, gi) => (
        <div key={gi} className="flex flex-col gap-1 flex-none">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold px-1">
            {g.street === 'unknown' ? '·' : streetLabel(g.street)}
          </div>
          <div className="flex gap-1.5">
            {g.items.map(({ t, idx }) => {
              const active = idx === currentTurnIdx
              const tone = ACTION_TONE[t.actionType ?? 'fold'] ?? 'text-slate-700'
              return (
                <button
                  key={idx}
                  data-turn-idx={idx}
                  onClick={() => onSeek(idx)}
                  title={`turn ${idx + 1}: seat ${t.actor} ${t.actionLabel}`}
                  className={[
                    'flex flex-col items-center gap-0.5 flex-none px-2.5 py-1.5 rounded-md',
                    'border bg-white text-xs',
                    active
                      ? 'border-indigo-500 ring-2 ring-indigo-200 shadow-sm'
                      : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50',
                  ].join(' ')}
                >
                  <div className="flex items-center gap-1">
                    {t.agentId && <ProviderBadge agentId={t.agentId} size={10} />}
                    <span className="text-[10px] font-mono tabular-nums text-slate-500">
                      s{t.actor}
                    </span>
                  </div>
                  <div className={`font-mono text-[11px] leading-tight ${tone}`}>
                    {t.actionLabel}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function streetLabel(s: Street): string {
  return s.toUpperCase()
}

// keep STREET_ORDER referenced so future sort usage finds it nearby
void STREET_ORDER
