import FreeCard from 'react-free-playing-cards'
import type { CardStr } from '../types'

type CardProp = CardStr | 'face-down'

interface Props {
  card: CardProp
  height?: string
  className?: string
}

/**
 * Wrapper around react-free-playing-cards. Accepts either a card code
 * (e.g. "As", "Kh") or 'face-down' for the back of the card.
 *
 * codex BLOCKER fix: react-free-playing-cards uses default export.
 * Pkg is on stale React ^16.13.1 peer; install via --legacy-peer-deps.
 */
export function Card({ card, height = '80px', className }: Props) {
  if (card === 'face-down') {
    return <FreeCard card="0" height={height} back className={className} />
  }
  return <FreeCard card={card} height={height} className={className} />
}
