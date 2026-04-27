#!/usr/bin/env node
// Auto-discover sessions in web/public/data/ and emit manifest.json.
// Each session dir must contain meta.json. Skips dirs without one.

import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DATA_ROOT = join(__dirname, '..', 'public', 'data')
const MANIFEST_PATH = join(DATA_ROOT, 'manifest.json')

function shortAgent(s) {
  if (s.startsWith('rule_based')) return 'RuleBased'
  // "anthropic:claude-haiku-4-5" → "claude-haiku-4-5"
  // "openai:gpt-4o" → "gpt-4o"
  return s.split(':').slice(1).join(':') || s
}

function lineupLabel(seatAssignment) {
  const counts = new Map()
  for (const v of Object.values(seatAssignment)) {
    const short = shortAgent(v)
    counts.set(short, (counts.get(short) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([name, n]) => (n > 1 ? `${n} ${name}` : name))
    .join(' + ')
}

function main() {
  const entries = readdirSync(DATA_ROOT)
    .filter((name) => {
      const full = join(DATA_ROOT, name)
      try { return statSync(full).isDirectory() } catch { return false }
    })
    .map((name) => {
      const metaPath = join(DATA_ROOT, name, 'meta.json')
      try {
        const meta = JSON.parse(readFileSync(metaPath, 'utf-8'))
        return {
          id: name,
          label: `${lineupLabel(meta.seat_assignment)} (${meta.total_hands_played} hands)`,
          hands: meta.total_hands_played,
        }
      } catch (e) {
        console.warn(`skip ${name}: ${e.message}`)
        return null
      }
    })
    .filter(Boolean)
    .sort((a, b) => a.id.localeCompare(b.id))

  const manifest = { sessions: entries }
  writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + '\n', 'utf-8')
  console.log(`wrote ${MANIFEST_PATH}:`)
  for (const s of entries) console.log(`  ${s.id}  →  ${s.label}`)
}

main()
