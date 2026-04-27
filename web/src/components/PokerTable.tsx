import { Card } from './Card'
import { Seat } from './Seat'
import { seatPosition } from './polar'
import type { CardStr, SeatStatus } from '../types'

interface SeatProps {
  seatIdx: number
  positionLabel: string
  stack: number
  status: SeatStatus
  holeCards: 'face-down' | [CardStr, CardStr]
  lastAction?: string
}

interface Props {
  seats: SeatProps[]
  community: CardStr[]
  pot: number
  activeSeatIdx: number
}

const TABLE_WIDTH = 800
const TABLE_HEIGHT = 400
const RX = 320
const RY = 180

export function PokerTable({ seats, community, pot, activeSeatIdx }: Props) {
  return (
    <div
      className="relative mx-auto"
      style={{ width: TABLE_WIDTH, height: TABLE_HEIGHT }}
    >
      <div
        className="absolute inset-0 bg-gradient-radial from-emerald-700 to-emerald-900 border-8 border-emerald-950"
        style={{ borderRadius: '50%' }}
      />
      <div
        className="absolute flex flex-col items-center gap-2"
        style={{
          top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          color: 'white',
        }}
      >
        <div className="flex gap-1">
          {community.length === 0 ? (
            <div className="text-xs opacity-60">(no community cards yet)</div>
          ) : (
            community.map((c, i) => <Card key={i} card={c} width={48} />)
          )}
        </div>
        <div className="text-lg font-bold mt-1">pot {pot}</div>
      </div>
      {seats.map((s) => {
        const { x, y } = seatPosition(s.seatIdx, 6, RX, RY)
        return (
          <div
            key={s.seatIdx}
            className="absolute"
            style={{
              left: `${TABLE_WIDTH / 2 + x}px`,
              top: `${TABLE_HEIGHT / 2 + y}px`,
              transform: 'translate(-50%, -50%)',
            }}
          >
            <Seat {...s} isActive={s.seatIdx === activeSeatIdx} />
          </div>
        )
      })}
    </div>
  )
}
