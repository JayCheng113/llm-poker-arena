import { LineChart } from '@tremor/react'

export interface SeatSeries {
  seat: number
  values: number[]  // running stack per hand (starting + cumulative PnL)
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
  // Tremor expects rows: { hand: 0, "seat 0": v, "seat 1": v, ... }
  const data = Array.from({ length: numHands }, (_, i) => {
    const row: Record<string, number | string> = { hand: i }
    for (const s of series) row[`seat ${s.seat}`] = s.values[i]
    return row
  })

  const categories = series.map((s) => `seat ${s.seat}`)
  const colors = series.map((s) => SEAT_COLORS[s.seat % SEAT_COLORS.length])

  // For the legend value, show the *delta* from starting stack since that's
  // the interesting number ("how much did this player win/lose"). Derived
  // by subtracting the first value from the last.
  const startingStack = series[0].values[0]

  return (
    <div
      data-pnl-chart
      className="bg-white border-y border-slate-200 px-4 py-2"
    >
      <div className="flex items-center justify-between gap-4 mb-1">
        <div className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
          stack trajectory
          <span className="ml-2 font-normal text-slate-400 normal-case">
            · viewing hand {currentHandIdx} of {numHands}
            {' · '}
            starting {startingStack.toLocaleString()}
          </span>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 justify-end">
          {series.map((s) => {
            const last = s.values[s.values.length - 1]
            const delta = last - startingStack
            const color = SEAT_COLORS[s.seat % SEAT_COLORS.length]
            return (
              <div key={s.seat} className="flex items-center gap-1.5 text-xs">
                <span
                  data-pnl-seat={s.seat}
                  className={`w-2 h-2 rounded-full bg-${color}-500`}
                />
                <span className="text-slate-500 font-medium">s{s.seat}</span>
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
