import type {
  CanonicalPrivateHand,
  PublicHandRecord,
  AgentViewSnapshot,
  SessionMeta,
} from '../types'

function parseLines<T>(text: string): T[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line) as T)
}

export function parseCanonicalPrivate(text: string): CanonicalPrivateHand[] {
  return parseLines<CanonicalPrivateHand>(text)
}

export function parsePublicReplay(text: string): PublicHandRecord[] {
  return parseLines<PublicHandRecord>(text)
}

export function parseAgentSnapshots(text: string): AgentViewSnapshot[] {
  return parseLines<AgentViewSnapshot>(text)
}

export function parseMeta(text: string): SessionMeta {
  return JSON.parse(text) as SessionMeta
}
