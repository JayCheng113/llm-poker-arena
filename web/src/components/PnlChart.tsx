import { LineChart } from '@tremor/react'
import { ProviderBadge } from './ProviderBadge'

export interface SeatSeries {
  seat: number
  values: number[]  // running stack per hand (starting + cumulative PnL)
  label: string    // human-readable agent name (e.g. "Haiku 4.5", "DeepSeek")
  agentId?: string // for ProviderBadge icon
}

interface Props {
  series: SeatSeries[]
  currentHandIdx: number
}

// Indigo/Tailwind-canonical hues for the 6 seats. Tremor accepts color
// names, not hex; these match the safelist in tailwind.config.ts.
const SEAT_COLORS = ['indigo', 'emerald', 'amber', 'rose', 'violet', 'cyan'] as const

function fmtStack(v: number): string {
  return v.toLocaleString()
}

function fmtDelta(v: number): string {
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  const abs = Math.abs(v)
  return `${sign}${abs.toLocaleString()}`
}

export function PnlChart({ series, currentHandIdx }: Props) {
  if (series.length === 0 || series[0].values.length === 0) {
    return (
      <div
        data-pnl-chart
        className="text-sm text-slate-400 italic px-3 py-2"
      >
        (no PnL data)
      </div>
    )
  }

  const numHands = series[0].values.length

  // Make a unique key per series: prefer the LLM name; if two seats share
  // the same label (e.g. two RuleBased agents) disambiguate by appending
  // the seat number. Tremor's tooltip + our legend both show this string.
  const labelCounts = new Map<string, number>()
  for (const s of series) {
    labelCounts.set(s.label, (labelCounts.get(s.label) ?? 0) + 1)
  }
  const seriesKey = (s: SeatSeries) =>
    (labelCounts.get(s.label) ?? 0) > 1 ? `${s.label} · s${s.seat}` : s.label

  // Tremor expects rows: { hand: 0, "Haiku 4.5": v, "DeepSeek": v, ... }
  const data = Array.from({ length: numHands }, (_, i) => {
    const row: Record<string, number | string> = { hand: i }
    for (const s of series) row[seriesKey(s)] = s.values[i]
    return row
  })

  const categories = series.map(seriesKey)
  const colors = series.map((s) => SEAT_COLORS[s.seat % SEAT_COLORS.length])

  // For the legend value, show the *delta* from starting stack at the
  // CURRENTLY VIEWED hand (codex NIT-3 — was end-of-session, which made
  // the legend lie about live state when scrubbing back through hands).
  const startingStack = series[0].values[0]
  const cursor = Math.max(0, Math.min(currentHandIdx, numHands - 1))

  return (
    <div
      data-pnl-chart
      className="bg-white border-y border-slate-200 px-4 py-2"
    >
      <div className="flex items-center justify-between gap-4 mb-1.5">
        <div className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
          standings
          <span className="ml-2 font-normal text-slate-400 normal-case">
            · @ hand {currentHandIdx} of {numHands}
            {' · '}
            starting {startingStack.toLocaleString()}
          </span>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 mb-2">
        {[...series]
          .map((s) => ({
            s,
            cursorValue: s.values[cursor],
            delta: s.values[cursor] - startingStack,
          }))
          .sort((a, b) => b.cursorValue - a.cursorValue)
          .map((row, idx) => {
            const { s, delta } = row
            const color = SEAT_COLORS[s.seat % SEAT_COLORS.length]
            const rank = idx + 1
            const rankBadge =
              rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `${rank}.`
            return (
              <div
                key={s.seat}
                data-pnl-seat={s.seat}
                className="flex items-center gap-1 text-xs"
              >
                <span className="w-4 text-center text-[11px] font-mono tabular-nums text-slate-500">
                  {rankBadge}
                </span>
                <span className={`w-1.5 h-1.5 rounded-full bg-${color}-500`} />
                {s.agentId && <ProviderBadge agentId={s.agentId} size={12} />}
                <span className="text-slate-700 font-medium">{s.label}</span>
                <span
                  className={`font-mono tabular-nums ${
                    delta > 0 ? 'text-emerald-600'
                    : delta < 0 ? 'text-rose-600'
                    : 'text-slate-400'
                  }`}
                >
                  {fmtDelta(delta)}
                </span>
              </div>
            )
          })}
      </div>
      <LineChart
        className="h-24"
        data={data}
        index="hand"
        categories={categories}
        colors={[...colors]}
        valueFormatter={fmtStack}
        showLegend={false}
        showAnimation={false}
        yAxisWidth={56}
        connectNulls
        showGridLines={false}
        startEndOnly={numHands > 12}
        curveType="monotone"
        autoMinValue
      />
    </div>
  )
}
