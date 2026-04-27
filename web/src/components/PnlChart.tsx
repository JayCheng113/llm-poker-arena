import { LineChart } from '@tremor/react'

export interface SeatSeries {
  seat: number
  values: number[]
}

interface Props {
  series: SeatSeries[]
  currentHandIdx: number
}

// Indigo/Tailwind-canonical hues for the 6 seats. Tremor accepts color
// names, not hex; these match the safelist in tailwind.config.ts.
const SEAT_COLORS = ['indigo', 'emerald', 'amber', 'rose', 'violet', 'cyan'] as const

function fmt(v: number): string {
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

  return (
    <div
      data-pnl-chart
      className="bg-white border-y border-slate-200 px-4 py-2"
    >
      <div className="flex items-center justify-between gap-4 mb-1">
        <div className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
          cumulative PnL
          <span className="ml-2 font-normal text-slate-400 normal-case">
            · viewing hand {currentHandIdx} of {numHands}
          </span>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 justify-end">
          {series.map((s) => {
            const last = s.values[s.values.length - 1]
            const color = SEAT_COLORS[s.seat % SEAT_COLORS.length]
            return (
              <div key={s.seat} className="flex items-center gap-1.5 text-xs">
                <span
                  data-seat={s.seat}
                  className={`w-2 h-2 rounded-full bg-${color}-500`}
                />
                <span className="text-slate-500 font-medium">s{s.seat}</span>
                <span
                  className={`font-mono tabular-nums ${
                    last > 0 ? 'text-emerald-600'
                    : last < 0 ? 'text-rose-600'
                    : 'text-slate-400'
                  }`}
                >
                  {fmt(last)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
      <LineChart
        className="h-20"
        data={data}
        index="hand"
        categories={categories}
        colors={[...colors]}
        valueFormatter={fmt}
        showLegend={false}
        showAnimation={false}
        yAxisWidth={48}
        connectNulls
        showGridLines={false}
        startEndOnly={numHands > 12}
        autoMinValue
      />
    </div>
  )
}
