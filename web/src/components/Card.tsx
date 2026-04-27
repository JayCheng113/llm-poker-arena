import type { CardStr, Rank, Suit } from '../types'

type CardProp = CardStr | 'face-down'

interface Props {
  card: CardProp
  /** width in px (height auto-derived ~1.4:1) */
  width?: number
  className?: string
}

const SUIT_CHAR: Record<Suit, string> = {
  s: '♠', h: '♥', d: '♦', c: '♣',
}
const SUIT_COLOR: Record<Suit, string> = {
  s: '#000', c: '#000', h: '#dc2626', d: '#dc2626',
}

function rankDisplay(r: Rank): string {
  return r === 'T' ? '10' : r
}

/**
 * CSS-rendered playing card. Looks like a real card (white face, rounded
 * corners, rank+suit corners + large center suit). Zero external dep.
 *
 * width prop controls overall size; height = 1.4 × width (poker standard).
 */
export function Card({ card, width = 50, className }: Props) {
  const height = Math.round(width * 1.4)
  const cornerFontSize = Math.max(10, Math.round(width * 0.28))
  const centerFontSize = Math.max(20, Math.round(width * 0.55))

  if (card === 'face-down') {
    return (
      <div
        data-card="face-down"
        className={className}
        style={{
          width, height,
          background: 'repeating-linear-gradient(45deg, #1e3a8a, #1e3a8a 4px, #1e40af 4px, #1e40af 8px)',
          border: '2px solid #1e40af',
          borderRadius: Math.round(width * 0.1),
          boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
          display: 'inline-block',
          verticalAlign: 'middle',
        }}
      />
    )
  }

  const rank = card[0] as Rank
  const suit = card[1] as Suit
  const color = SUIT_COLOR[suit]
  const rankStr = rankDisplay(rank)
  const suitStr = SUIT_CHAR[suit]

  return (
    <div
      data-card={card}
      className={className}
      style={{
        width, height,
        background: 'white',
        border: '1px solid #444',
        borderRadius: Math.round(width * 0.1),
        position: 'relative',
        display: 'inline-block',
        verticalAlign: 'middle',
        boxShadow: '0 1px 2px rgba(0,0,0,0.15)',
        fontFamily: 'Helvetica, Arial, sans-serif',
        color,
        userSelect: 'none',
        overflow: 'hidden',
      }}
    >
      {/* top-left corner */}
      <div style={{
        position: 'absolute',
        top: Math.round(width * 0.06),
        left: Math.round(width * 0.08),
        fontSize: cornerFontSize,
        fontWeight: 700,
        lineHeight: 1,
        textAlign: 'center',
      }}>
        <div>{rankStr}</div>
        <div style={{ fontSize: cornerFontSize * 0.85 }}>{suitStr}</div>
      </div>
      {/* center suit */}
      <div style={{
        position: 'absolute',
        top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        fontSize: centerFontSize,
        lineHeight: 1,
      }}>{suitStr}</div>
    </div>
  )
}
