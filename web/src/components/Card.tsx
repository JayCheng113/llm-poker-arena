import type { CardStr, Rank, Suit } from '../types'

type CardProp = CardStr | 'face-down'

interface Props {
  card: CardProp
  height?: string
  className?: string
}

// Unicode playing card code points (U+1F0A0 block).
// Suits: spades 1F0A0, hearts 1F0B0, diamonds 1F0C0, clubs 1F0D0.
// Ranks: A=1, 2-9=2-9, T=A, J=B, Q=D, K=E (0xC = knight, skipped).
const SUIT_BASE: Record<Suit, number> = {
  s: 0x1f0a0, h: 0x1f0b0, d: 0x1f0c0, c: 0x1f0d0,
}
const RANK_OFFSET: Record<Rank, number> = {
  A: 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
  '8': 8, '9': 9, T: 0xa, J: 0xb, Q: 0xd, K: 0xe,
}

function cardChar(card: CardStr): string {
  const rank = card[0] as Rank
  const suit = card[1] as Suit
  return String.fromCodePoint(SUIT_BASE[suit] + RANK_OFFSET[rank])
}

const SUIT_COLOR: Record<Suit, string> = {
  s: '#000', c: '#000', h: '#dc2626', d: '#dc2626',
}

/**
 * Single-character Unicode playing card (no external dep).
 *
 * Trade-off vs SVG: less polished, font-dependent rendering (can be small
 * on default fonts), but zero external dependency + CC0 + works in any
 * browser. Phase 2 polish may swap for a static SVG sprite.
 */
export function Card({ card, height = '80px', className }: Props) {
  const isBack = card === 'face-down'
  const ch = isBack ? '\u{1F0A0}' : cardChar(card)
  const color = isBack ? '#1e3a8a' : SUIT_COLOR[card[1] as Suit]
  return (
    <span
      data-card={card}
      className={className}
      style={{
        fontSize: height,
        lineHeight: '0.8',
        color,
        fontFamily:
          '"Apple Symbols", "DejaVu Sans", "Symbola", "Segoe UI Symbol", sans-serif',
        display: 'inline-block',
      }}
    >
      {ch}
    </span>
  )
}
