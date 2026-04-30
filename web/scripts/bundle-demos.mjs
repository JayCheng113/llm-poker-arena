#!/usr/bin/env node
// Auto-discover sessions in web/public/data/ and emit manifest.json.
// Each session dir must contain meta.json. Skips dirs without one.

import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DATA_ROOT = join(__dirname, '..', 'public', 'data')
const MANIFEST_PATH = join(DATA_ROOT, 'manifest.json')

// OpenRouter agent ids are vendor-prefixed
// (e.g. "openrouter:google/gemini-3.1-pro-preview"). For the manifest
// label we want the human-friendly model name without the gateway —
// so "openrouter:google/gemini-3.1-pro-preview" reads as
// "gemini-3.1-pro-preview", same as if it had hit Gemini directly.
const OPENROUTER_VENDORS = new Set([
  'google',
  'anthropic',
  'openai',
  'deepseek',
  'qwen',
  'moonshotai',
  'x-ai',
])

function shortAgent(s) {
  if (s.startsWith('rule_based')) return 'RuleBased'
  // "anthropic:claude-haiku-4-5" → "claude-haiku-4-5"
  // "openai:gpt-4o" → "gpt-4o"
  // "openrouter:google/gemini-3.1-pro-preview" → "gemini-3.1-pro-preview"
  const tail = s.split(':').slice(1).join(':')
  if (s.startsWith('openrouter:')) {
    const slash = tail.indexOf('/')
    if (slash > 0 && OPENROUTER_VENDORS.has(tail.slice(0, slash))) {
      return tail.slice(slash + 1)
    }
  }
  return tail || s
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

// Marquee order — ids in this list float to the top in this exact order.
// Anything else falls back to alphabetical at the bottom. The picker
// shows whatever is first (App.tsx's `manifest.sessions[0]?.id`), so
// putting the headline 6-LLM tournament first makes it the default
// landing demo without forcing the user to re-pick on every page load.
//
// As of 2026-04-27 the GitHub Pages deploy ships only `demo-6llm`
// (30-hand official tournament with one LLM per seat). Other ids stay
// in the list so a contributor regenerating an older demo locally still
// gets it placed sensibly without an extra picker hunt — but those
// directories are not bundled into the pages deploy.
const MARQUEE_ORDER = [
  'demo-6llm',           // 30-hand baseline (mini-tier across all 6) — landing demo
  'demo-6llm-flagship',  // 102-hand controlled experiment (Anthropic→Sonnet)
  'pilot-flagship-30h',  // 30-hand all-flagship lineup pilot — Opus 4.7 / GPT-5.5 / Gemini-3.1-pro-preview / etc.
  'demo-tournament',     // 4-LLM mixed lineup (local-only)
  'demo-6llm-smoke',     // smoke variant (local-only)
  'demo-1',              // single-LLM walk-through (local-only)
  'demo-bots',           // all-bot baseline (local-only)
]

function priority(id) {
  const i = MARQUEE_ORDER.indexOf(id)
  // unknown ids sort after the marquee block (Number.MAX_SAFE_INTEGER
  // keeps the comparator stable even if the list grows large).
  return i === -1 ? Number.MAX_SAFE_INTEGER : i
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
    .sort((a, b) => {
      const pa = priority(a.id)
      const pb = priority(b.id)
      if (pa !== pb) return pa - pb
      return a.id.localeCompare(b.id)
    })

  const manifest = { sessions: entries }
  writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + '\n', 'utf-8')
  console.log(`wrote ${MANIFEST_PATH}:`)
  for (const s of entries) console.log(`  ${s.id}  →  ${s.label}`)
}

main()
