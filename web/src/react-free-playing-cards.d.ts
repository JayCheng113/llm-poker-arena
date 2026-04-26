declare module 'react-free-playing-cards' {
  import type { CSSProperties } from 'react'
  interface CardProps {
    card: string
    height?: string
    back?: boolean
    className?: string
    style?: CSSProperties
  }
  export default function Card(props: CardProps): JSX.Element
}
