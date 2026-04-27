interface Props {
  denomination: number
  size?: number // px, default 32
}

function colorForDenom(d: number): string {
  if (d <= 1) return '#fff'
  if (d <= 5) return '#ef4444'
  if (d <= 25) return '#3b82f6'
  if (d <= 100) return '#22c55e'
  if (d <= 500) return '#1f2937'
  return '#a855f7'
}

export function Chip({ denomination, size = 32 }: Props) {
  const color = colorForDenom(denomination)
  return (
    <div
      data-chip={denomination}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        borderRadius: '50%',
        backgroundColor: color,
        border: '2px solid #222',
        color: color === '#fff' ? '#222' : '#fff',
        fontSize: size * 0.32,
        fontWeight: 'bold',
        fontFamily: 'sans-serif',
        userSelect: 'none',
      }}
    >
      {denomination}
    </div>
  )
}
