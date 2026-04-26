import { useEffect, useState } from 'react'
import {
  parseCanonicalPrivate,
  parsePublicReplay,
  parseAgentSnapshots,
  parseMeta,
} from './parsers/parseJsonl'
import { getCurrentTurn } from './selectors/getCurrentTurn'
import { cardRevelation } from './selectors/cardRevelation'
import { HandSelector } from './components/HandSelector'
import { PokerTable } from './components/PokerTable'
import { ReasoningPanel } from './components/ReasoningPanel'
import { ActionTimeline } from './components/ActionTimeline'
import type {
  ParsedSession, SeatStatus, CardStr, ActionType,
} from './types'

const DATA_BASE = '/data/demo-1'
const POSITION_LABELS = ['BTN', 'SB', 'BB', 'UTG', 'HJ', 'CO']

function _positionLabelForSeat(seat: number, buttonSeat: number, n: number): string {
  const offset = ((seat - buttonSeat) + n) % n
  return POSITION_LABELS[offset]
}

function useUrlPointer(): {
  handId: number
  turnIdx: number
  setHandId: (h: number) => void
  setTurnIdx: (t: number) => void
} {
  const [pointer, setPointer] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    return {
      handId: Number(params.get('hand') ?? '0'),
      turnIdx: Number(params.get('turn') ?? '0'),
    }
  })

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    params.set('hand', String(pointer.handId))
    params.set('turn', String(pointer.turnIdx))
    const newUrl = `${window.location.pathname}?${params.toString()}`
    window.history.replaceState(null, '', newUrl)
  }, [pointer])

  return {
    handId: pointer.handId,
    turnIdx: pointer.turnIdx,
    setHandId: (h: number) => setPointer({ handId: h, turnIdx: 0 }),
    setTurnIdx: (t: number) => setPointer((p) => ({ ...p, turnIdx: t })),
  }
}

function _formatAction(action: { type: ActionType; amount?: number }): string {
  if (action.amount !== undefined) return `${action.type} ${action.amount}`
  return action.type
}

function App() {
  const [session, setSession] = useState<ParsedSession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ptr = useUrlPointer()

  useEffect(() => {
    Promise.all([
      fetch(`${DATA_BASE}/canonical_private.jsonl`).then((r) => r.text()),
      fetch(`${DATA_BASE}/public_replay.jsonl`).then((r) => r.text()),
      fetch(`${DATA_BASE}/agent_view_snapshots.jsonl`).then((r) => r.text()),
      fetch(`${DATA_BASE}/meta.json`).then((r) => r.text()),
    ])
      .then(([canonText, publicText, snapText, metaText]) => {
        const meta = parseMeta(metaText)
        const canonical = parseCanonicalPrivate(canonText)
        const publicRecords = parsePublicReplay(publicText)
        const snaps = parseAgentSnapshots(snapText)
        const hands: ParsedSession['hands'] = {}
        for (const hand of canonical) {
          const pubRec = publicRecords.find((p) => p.hand_id === hand.hand_id)
          hands[hand.hand_id] = {
            canonical: hand,
            publicEvents: pubRec ? pubRec.street_events : [],
            agentSnapshots: snaps.filter((s) => s.hand_id === hand.hand_id),
          }
        }
        setSession({ meta, hands })
      })
      .catch((e: Error) => setError(`Failed to load session: ${e.message}`))
  }, [])

  if (error) {
    return <div className="p-8 text-red-700">{error}</div>
  }
  if (!session) {
    return <div className="p-8">Loading session...</div>
  }

  const handIds = Object.keys(session.hands).map(Number).sort((a, b) => a - b)
  const hand = session.hands[ptr.handId]
  if (!hand) {
    return <div className="p-8">Hand {ptr.handId} not in session</div>
  }
  const turnCount = hand.agentSnapshots.length
  const safeTurnIdx = Math.min(ptr.turnIdx, turnCount - 1)
  const turn = getCurrentTurn(session, ptr.handId, safeTurnIdx)
  const handEnded = safeTurnIdx >= turnCount - 1
  const revealed = cardRevelation(session, ptr.handId, 'live', { handEnded })

  const cfg = hand.canonical
  const buttonSeat = cfg.button_seat
  const folded = new Set<number>()
  const actionsByTurn = hand.agentSnapshots.slice(0, safeTurnIdx + 1)
  for (const snap of actionsByTurn) {
    if (snap.final_action.type === 'fold') {
      folded.add(snap.seat)
    }
  }

  // Stacks come from current snapshot's view_at_turn_start.seats_public
  // (codex IMPORTANT-7 fix; see types.ts SeatPublicInfo)
  const currentSnap = hand.agentSnapshots[safeTurnIdx]
  const seatsPublic = currentSnap?.view_at_turn_start.seats_public ?? []
  const seatsPublicByIdx: { [k: number]: typeof seatsPublic[0] } = {}
  for (const sp of seatsPublic) {
    seatsPublicByIdx[sp.seat] = sp
  }
  const seats = [0, 1, 2, 3, 4, 5].map((seatIdx) => {
    const positionLabel = _positionLabelForSeat(seatIdx, buttonSeat, 6)
    const sp = seatsPublicByIdx[seatIdx]
    const status: SeatStatus = sp?.status ?? (folded.has(seatIdx) ? 'folded' : 'in_hand')
    const holeFromRevealed = revealed[String(seatIdx)]
    const holeCards: 'face-down' | [CardStr, CardStr] =
      holeFromRevealed && holeFromRevealed !== 'face-down' ? holeFromRevealed : 'face-down'
    const myActions = actionsByTurn.filter((s) => s.seat === seatIdx)
    const lastAction = myActions.length > 0
      ? _formatAction(myActions[myActions.length - 1].final_action)
      : undefined
    return {
      seatIdx,
      positionLabel,
      stack: sp?.stack ?? cfg.starting_stacks[String(seatIdx)] ?? 0,
      status,
      holeCards,
      lastAction,
    }
  })

  const community: CardStr[] =
    turn.street === 'preflop'
      ? []
      : turn.street === 'flop'
      ? cfg.community.slice(0, 3)
      : turn.street === 'turn'
      ? cfg.community.slice(0, 4)
      : cfg.community.slice(0, 5)

  const timelineTurns = hand.agentSnapshots.map((s) => ({
    actor: s.seat,
    actionLabel: _formatAction(s.final_action),
  }))

  const actorPosition = _positionLabelForSeat(turn.actor, buttonSeat, 6)

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      <HandSelector
        handIds={handIds}
        currentHandId={ptr.handId}
        onSelect={ptr.setHandId}
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 flex items-center justify-center p-4">
          <PokerTable
            seats={seats}
            community={community}
            pot={turn.pot}
            activeSeatIdx={turn.actor}
          />
        </div>
        <div className="w-96">
          <ReasoningPanel
            actor={turn.actor}
            positionLabel={actorPosition}
            iterations={turn.reasoning}
            commitAction={turn.commitAction}
          />
        </div>
      </div>
      <ActionTimeline
        turns={timelineTurns}
        currentTurnIdx={safeTurnIdx}
        onSeek={ptr.setTurnIdx}
      />
    </div>
  )
}

export default App
