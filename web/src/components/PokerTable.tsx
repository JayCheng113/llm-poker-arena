import { Card } from './Card'
import { Seat } from './Seat'
import { seatPosition } from './polar'
import type { CardStr, HandResultPrivate, SeatStatus } from '../types'

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
  handResult?: HandResultPrivate
}

const TABLE_WIDTH = 800
const TABLE_HEIGHT = 400
const RX = 320
const RY = 180
const COMMUNITY_CARD_WIDTH = 48
const COMMUNITY_CARD_HEIGHT = Math.round(COMMUNITY_CARD_WIDTH * 1.4)

export function PokerTable({ seats, community, pot, activeSeatIdx, handResult }: Props) {
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
        <div className="flex gap-1" style={{ minHeight: COMMUNITY_CARD_HEIGHT }}>
          {[0, 1, 2, 3, 4].map((i) => {
            const card = community[i]
            if (card) return <Card key={i} card={card} width={COMMUNITY_CARD_WIDTH} />
            return (
              <div
                key={i}
                data-community-placeholder
                style={{
                  width: COMMUNITY_CARD_WIDTH,
                  height: COMMUNITY_CARD_HEIGHT,
                  border: '2px dashed rgba(255,255,255,0.18)',
                  borderRadius: Math.round(COMMUNITY_CARD_WIDTH * 0.1),
                }}
              />
            )
          })}
        </div>
        <div className="text-lg font-bold mt-1">pot {pot}</div>
        {handResult && handResult.winners.length > 0 && (
          <div className="flex flex-col items-center gap-0.5 mt-1">
            {handResult.winners.map((w) => (
              <div
                key={w.seat}
                className="px-2 py-0.5 rounded bg-yellow-500 text-slate-900 text-sm font-semibold"
              >
                seat {w.seat} wins +{w.winnings}
                {w.best_hand_desc ? ` (${w.best_hand_desc})` : ''}
              </div>
            ))}
          </div>
        )}
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
