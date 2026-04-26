import type { ParsedSession, Street, ActionType, IterationRecord } from '../types'

export interface CurrentTurnState {
  actor: number
  street: Street
  pot: number
  toCall: number
  potOddsRequired: number | null
  reasoning: IterationRecord[]
  commitAction: { type: ActionType; amount?: number }
}

export function getCurrentTurn(
  session: ParsedSession,
  handId: number,
  turnIdx: number,
): CurrentTurnState {
  const hand = session.hands[handId]
  if (!hand) {
    throw new Error(`hand ${handId} not in session`)
  }
  const snap = hand.agentSnapshots[turnIdx]
  if (!snap) {
    throw new Error(`turn ${turnIdx} not in hand ${handId}`)
  }
  return {
    actor: snap.seat,
    street: snap.street,
    pot: snap.view_at_turn_start.pot,
    toCall: snap.view_at_turn_start.to_call,
    potOddsRequired: snap.view_at_turn_start.pot_odds_required,
    reasoning: snap.iterations,
    commitAction: snap.final_action,
  }
}
