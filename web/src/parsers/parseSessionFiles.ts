import {
  parseCanonicalPrivate,
  parsePublicReplay,
  parseAgentSnapshots,
  parseMeta,
} from './parseJsonl'
import type { ParsedSession } from '../types'

/**
 * Build a ParsedSession from the four raw file contents.
 * Used by both fetch-based session loading and the dev-mode file picker.
 */
export function parseSessionFiles(texts: {
  canonical: string
  public: string
  snapshots: string
  meta: string
}): ParsedSession {
  const meta = parseMeta(texts.meta)
  const canonical = parseCanonicalPrivate(texts.canonical)
  const publicRecords = parsePublicReplay(texts.public)
  const snaps = parseAgentSnapshots(texts.snapshots)
  const hands: ParsedSession['hands'] = {}
  for (const hand of canonical) {
    const pubRec = publicRecords.find((p) => p.hand_id === hand.hand_id)
    hands[hand.hand_id] = {
      canonical: hand,
      publicEvents: pubRec ? pubRec.street_events : [],
      agentSnapshots: snaps.filter((s) => s.hand_id === hand.hand_id),
    }
  }
  return { meta, hands }
}

/**
 * From a FileList (typically from `<input type="file" multiple>` or
 * webkitdirectory), find the four required session files by name and parse.
 * Throws if any required file is missing.
 */
export async function parseSessionFromFiles(files: FileList): Promise<ParsedSession> {
  const byName: { [name: string]: File } = {}
  for (const f of Array.from(files)) {
    byName[f.name] = f
  }
  const required = [
    'canonical_private.jsonl',
    'public_replay.jsonl',
    'agent_view_snapshots.jsonl',
    'meta.json',
  ] as const
  const missing = required.filter((n) => !byName[n])
  if (missing.length > 0) {
    throw new Error(`missing required files: ${missing.join(', ')}`)
  }
  const [canonical, publicText, snapshots, meta] = await Promise.all([
    byName['canonical_private.jsonl'].text(),
    byName['public_replay.jsonl'].text(),
    byName['agent_view_snapshots.jsonl'].text(),
    byName['meta.json'].text(),
  ])
  return parseSessionFiles({ canonical, public: publicText, snapshots, meta })
}
