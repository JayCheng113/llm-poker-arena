import type { ParsedSession, CardStr, PublicShowdown } from '../types'

export type RevealedCards = [CardStr, CardStr] | 'face-down'
export type RevelationMode = 'live' | 'god-view' | 'hero'

export function cardRevelation(
  session: ParsedSession,
  handId: number,
  mode: RevelationMode,
  ctx: { handEnded: boolean },
): { [seatStr: string]: RevealedCards } {
  const hand = session.hands[handId]
  if (!hand) return {}

  // god-view: always show all hole cards from canonical
  if (mode === 'god-view') {
    const out: { [k: string]: RevealedCards } = {}
    for (const [seatStr, cards] of Object.entries(hand.canonical.hole_cards)) {
      out[seatStr] = cards
    }
    return out
  }

  // live mode (Phase 1 default): face-down unless hand ended + showdown event present
  const out: { [k: string]: RevealedCards } = {}
  for (const seatStr of Object.keys(hand.canonical.hole_cards)) {
    out[seatStr] = 'face-down'
  }
  if (!ctx.handEnded) {
    return out
  }
  const showdown = hand.publicEvents.find(
    (e): e is PublicShowdown => e.type === 'showdown',
  )
  if (!showdown) {
    // Walk / uncalled — no revelation
    return out
  }
  for (const [seatStr, cards] of Object.entries(showdown.revealed)) {
    out[seatStr] = cards
  }
  return out
}
