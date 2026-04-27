export interface SeatSeries {
  seat: number
  values: number[]
}

interface Props {
  series: SeatSeries[]
  currentHandIdx: number
  width?: number
  height?: number
}

const SEAT_COLORS = [
  '#ef4444', '#3b82f6', '#22c55e', '#eab308', '#a855f7', '#06b6d4',
]

const PADDING = 24
const LEGEND_GAP = 78

export function PnlChart({
  series, currentHandIdx, width = 700, height = 120,
}: Props) {
  if (series.length === 0 || series[0].values.length === 0) {
    return (
      <div className="text-xs text-slate-500 italic px-2 py-1">
        (no PnL data)
      </div>
    )
  }
  const numHands = series[0].values.length
  const allValues = series.flatMap((s) => s.values)
  const yMin = Math.min(...allValues, 0)
  const yMax = Math.max(...allValues, 0)
  const yRange = Math.max(yMax - yMin, 1)
  const chartW = width - PADDING * 2
  const chartH = height - PADDING * 2

  const xScale = (i: number) =>
    PADDING + (chartW * i) / Math.max(1, numHands - 1)
  const yScale = (v: number) =>
    PADDING + chartH - ((v - yMin) / yRange) * chartH
  const zeroY = yScale(0)

  return (
    <svg
      width={width}
      height={height}
      className="bg-slate-900 rounded"
      data-pnl-chart
    >
      {/* legend row */}
      {series.map((s, idx) => {
        const last = s.values[s.values.length - 1]
        const sign = last >= 0 ? '+' : ''
        return (
          <text
            key={`lg-${s.seat}`}
            x={PADDING + idx * LEGEND_GAP}
            y={14}
            fill={SEAT_COLORS[s.seat % SEAT_COLORS.length]}
            fontSize={11}
            fontFamily="monospace"
          >
            s{s.seat} {sign}{last}
          </text>
        )
      })}
      {/* zero baseline */}
      <line
        x1={PADDING} y1={zeroY}
        x2={width - PADDING} y2={zeroY}
        stroke="#475569" strokeDasharray="2 4"
      />
      {/* current hand marker */}
      <line
        x1={xScale(currentHandIdx)} y1={PADDING}
        x2={xScale(currentHandIdx)} y2={height - PADDING}
        stroke="#fbbf24" strokeWidth={2}
        data-current-marker
      />
      {/* seat polylines */}
      {series.map((s) => (
        <polyline
          key={s.seat}
          fill="none"
          stroke={SEAT_COLORS[s.seat % SEAT_COLORS.length]}
          strokeWidth={2}
          points={s.values.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ')}
          data-seat={s.seat}
        />
      ))}
    </svg>
  )
}
