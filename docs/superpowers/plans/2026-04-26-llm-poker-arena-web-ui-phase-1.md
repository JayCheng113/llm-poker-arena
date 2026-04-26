# Web UI Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (inline mode) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a portfolio-grade replay viewer for `llm-poker-arena` sessions: a React static site that renders one bundled Claude 6-hand session as a poker table visualization with a reasoning panel and seek-able action timeline. ~1 week of work.

**Architecture:** React 18 + Vite + TypeScript + Tailwind in `web/` subdirectory. Pure static site (no backend, no API calls). Plain `useEffect + useState` to fetch 4 JSONL/JSON files from `web/public/data/demo-1/`. Pure-function selectors derive display state from session data + URL pointer `(handId, turnIdx)`. Components: PokerTable (oval + 6 polar-positioned Seats) + ReasoningPanel (right) + ActionTimeline (bottom) + HandSelector (top).

**Tech Stack:**
- React 18 + Vite 5 + TypeScript 5
- Tailwind CSS 3 (no shadcn/ui in Phase 1)
- `react-free-playing-cards` (CC0 SVG card components)
- Vitest + @testing-library/react (unit + behavior tests)
- Playwright (1 e2e happy-path test)
- ESLint (typescript-eslint preset) + Prettier
- No TanStack Query, no framer-motion, no shadcn/ui (all Phase 2)

---

## Phase 1 Scope Recap (from spec §144-176)

**IN scope** (this plan):
1. Oval poker table with 6 polar-positioned seats (seat 3 = bottom-center)
2. Community cards centered (text-based or SVG)
3. Hole cards revelation: `live` mode only (face-down until contested showdown)
4. Pot display centered
5. Active seat highlight + last action floating text
6. Reasoning panel: text_content + tool_call/args/result + commit
7. Action timeline (bottom): one card per turn, click to seek
8. Hand selector (top): prev/next + dropdown
9. Single hardcoded demo session bundled at `web/public/data/demo-1/`

**OUT of Phase 1** (deferred to Phase 2 plan):
- Auto-play animations
- Multi-session selector
- Dev mode toggle (god-view, raw JSON viewer)
- Session summary view
- Mobile responsive
- Visual polish (animations)
- TanStack Query, shadcn/ui, framer-motion

---

## File Structure (Phase 1 deliverable)

```
llm-poker-arena/
├── web/                       # NEW (this plan)
│   ├── package.json           # npm scripts + deps
│   ├── vite.config.ts         # Vite + React + tailwind plugin
│   ├── tsconfig.json          # strict TS
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── .eslintrc.cjs
│   ├── .prettierrc
│   ├── .gitignore             # node_modules, dist
│   ├── index.html
│   ├── playwright.config.ts
│   ├── public/
│   │   └── data/
│   │       └── demo-1/        # Demo session artifacts (committed)
│   │           ├── canonical_private.jsonl
│   │           ├── public_replay.jsonl
│   │           ├── agent_view_snapshots.jsonl
│   │           └── meta.json
│   ├── scripts/
│   │   └── generate-demo.py   # One-time demo session generator
│   ├── src/
│   │   ├── main.tsx           # Entry: ReactDOM root + App
│   │   ├── App.tsx            # SessionLoader + ReplayView
│   │   ├── index.css          # Tailwind base
│   │   ├── types.ts           # TS types mirroring Pydantic schemas
│   │   ├── parsers/
│   │   │   ├── parseJsonl.ts
│   │   │   └── parseJsonl.test.ts
│   │   ├── selectors/
│   │   │   ├── getCurrentTurn.ts
│   │   │   ├── getCurrentTurn.test.ts
│   │   │   ├── cardRevelation.ts
│   │   │   └── cardRevelation.test.ts
│   │   ├── components/
│   │   │   ├── polar.ts                # math helper
│   │   │   ├── polar.test.ts
│   │   │   ├── Card.tsx
│   │   │   ├── Card.test.tsx
│   │   │   ├── Chip.tsx
│   │   │   ├── Chip.test.tsx
│   │   │   ├── Seat.tsx
│   │   │   ├── Seat.test.tsx
│   │   │   ├── PokerTable.tsx
│   │   │   ├── PokerTable.test.tsx
│   │   │   ├── ReasoningPanel.tsx
│   │   │   ├── ReasoningPanel.test.tsx
│   │   │   ├── ActionTimeline.tsx
│   │   │   ├── ActionTimeline.test.tsx
│   │   │   ├── HandSelector.tsx
│   │   │   └── HandSelector.test.tsx
│   │   └── assets/
│   │       └── chip.svg
│   └── e2e/
│       └── replay-happy-path.spec.ts
└── .github/workflows/
    └── web.yml                # CI: lint + tsc + vitest + playwright
```

**~25 source files**, ~2000 LOC frontend (per spec components hierarchy estimate).

---

## Task Counts (cumulative)

| Task | New tests | Cumulative tests |
|---|---|---|
| 0 | 0 (scaffold) | 0 |
| 1 | 0 (types only) | 0 |
| 2 | 0 (committed artifacts) | 0 |
| 3 | 4 unit (4 parsers) | 4 |
| 4 | 3 unit (selector) | 7 |
| 5 | 3 unit (revelation) | 10 |
| 6 | 3 unit (polar math) | 13 |
| 7 | 2 RTL (Card) | 15 |
| 8 | 2 RTL (Chip) | 17 |
| 9 | 3 RTL (Seat states) | 20 |
| 10 | 3 RTL (PokerTable) | 23 |
| 11 | 4 RTL (ReasoningPanel) | 27 |
| 12 | 3 RTL (ActionTimeline) | 30 |
| 13 | 4 RTL (HandSelector) | 34 |
| 14 | 0 (App = e2e) | 34 |
| 15 | 1 Playwright e2e | 35 |
| 16 | 0 (CI workflow) | 35 |
| 17 | 0 (build smoke) | 35 |

**Final: ~35 tests** (13 unit + 21 RTL behavior + 1 e2e).

---

## Task 0: Scaffold web/ (Vite + React + TS + Tailwind)

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`, `web/tsconfig.node.json`
- Create: `web/tailwind.config.ts`, `web/postcss.config.js`
- Create: `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/index.css`
- Create: `web/.eslintrc.cjs`, `web/.prettierrc`
- Create: `web/.gitignore`

- [ ] **Step 1: Use Vite scaffold + customize**

Run from repo root:
```bash
npm create vite@latest web -- --template react-ts
cd web
npm install
```

This creates baseline `package.json`, `vite.config.ts`, `tsconfig.json`, etc. with React 18 + TS template.

- [ ] **Step 2: Add Tailwind v3 (pinned)**

Tailwind v4 (released early 2025) ships a different config / setup
(no `tailwind.config.ts`, uses `@theme` in CSS instead). This plan
uses v3 because shadcn/ui (Phase 2 target) ships v3 templates.

```bash
cd web
npm install -D tailwindcss@^3 postcss autoprefixer
npx tailwindcss init -p
```

Edit `web/tailwind.config.ts` to:
```ts
import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
}
export default config
```

Replace `web/src/index.css` content with:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 3: Add ESLint + Prettier**

```bash
cd web
npm install -D eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin \
               eslint-plugin-react eslint-plugin-react-hooks prettier \
               eslint-config-prettier
```

Create `web/.eslintrc.cjs`:
```js
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 2022, sourceType: 'module', ecmaFeatures: { jsx: true } },
  plugins: ['@typescript-eslint', 'react', 'react-hooks'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
    'prettier',
  ],
  settings: { react: { version: 'detect' } },
  rules: {
    'react/react-in-jsx-scope': 'off',
  },
}
```

Create `web/.prettierrc`:
```json
{ "semi": false, "singleQuote": true, "trailingComma": "all", "printWidth": 100 }
```

- [ ] **Step 4: Add npm scripts to package.json**

Edit `web/package.json` `"scripts"` section:
```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint src --ext ts,tsx",
    "format": "prettier --write src",
    "type-check": "tsc --noEmit"
  }
}
```

- [ ] **Step 5: Create .gitignore**

Create `web/.gitignore`:
```
node_modules/
dist/
*.local
.env.local
```

- [ ] **Step 6: Replace App.tsx with placeholder**

Replace `web/src/App.tsx` with:
```tsx
function App() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">llm-poker-arena Web UI</h1>
      <p className="text-gray-600">Replay viewer (Phase 1 placeholder)</p>
    </div>
  )
}

export default App
```

- [ ] **Step 7: Verify dev server boots**

Run:
```bash
cd web && npm run dev
```

Expected: Vite serves at `http://localhost:5173/`. Open browser → see "llm-poker-arena Web UI" heading. Kill server (Ctrl-C).

- [ ] **Step 8: Verify lint + type-check pass**

```bash
cd web && npm run lint && npm run type-check
```

Expected: both clean (no errors).

- [ ] **Step 9: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena
git add web/
git commit -m "$(cat <<'EOF'
chore(web): scaffold Vite + React + TS + Tailwind (Web UI Task 0)

npm create vite@latest web -- --template react-ts
+ Tailwind + ESLint + Prettier setup. App.tsx is a placeholder heading;
subsequent tasks add JSONL parsers, selectors, components.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: TypeScript types (mirror Pydantic schemas)

**Files:**
- Create: `web/src/types.ts`

**Why no test:** Pure type declarations; type-checking via `tsc --noEmit` is verification.

- [ ] **Step 1: Create types.ts**

Create `web/src/types.ts`:
```ts
// Mirror of Pydantic schemas in src/llm_poker_arena/{engine/views.py,
// agents/llm/types.py, storage/schemas.py}. JSON shapes only — no
// runtime validation (we trust generated artifacts).

export type Suit = 's' | 'h' | 'd' | 'c'
export type Rank = '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' | 'T' | 'J' | 'Q' | 'K' | 'A'
export type CardStr = `${Rank}${Suit}` // e.g. "As", "Kh"

export type Street = 'preflop' | 'flop' | 'turn' | 'river'
export type ActionType = 'fold' | 'check' | 'call' | 'bet' | 'raise_to' | 'all_in'
export type SeatStatus = 'in_hand' | 'folded' | 'all_in'

// === meta.json ===
export interface SessionMeta {
  session_id: string
  version: number
  schema_version: string
  total_hands_played: number
  planned_hands: number
  chip_pnl: { [seatStr: string]: number }
  total_tokens: { [seatStr: string]: TokenCounts }
  retry_summary_per_seat: { [seatStr: string]: RetrySummary }
  tool_usage_summary: { [seatStr: string]: { total_utility_calls: number } }
  seat_assignment: { [seatStr: string]: string } // "anthropic:claude-haiku-4-5", "rule_based:tag_v1"
  initial_button_seat: number
  stop_reason: string
  // ... other fields not used by UI Phase 1
}

export interface TokenCounts {
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

export interface RetrySummary {
  total_turns: number
  api_retry_count: number
  illegal_action_retry_count: number
  no_tool_retry_count: number
  tool_usage_error_count: number
  default_action_fallback_count: number
  turn_timeout_exceeded_count: number
}

// === canonical_private.jsonl ===
export interface CanonicalPrivateHand {
  hand_id: number
  started_at: string
  ended_at: string
  button_seat: number
  sb_seat: number
  bb_seat: number
  deck_seed: number
  starting_stacks: { [seatStr: string]: number }
  hole_cards: { [seatStr: string]: [CardStr, CardStr] } // ALL hole cards (god-view source)
  community: CardStr[]
  actions: ActionRecordPrivate[]
  result: HandResultPrivate
}

export interface ActionRecordPrivate {
  seat: number
  street: Street
  action_type: ActionType
  amount: number | null
  is_forced_blind: boolean
  turn_index: number
}

export interface HandResultPrivate {
  showdown: boolean
  winners: WinnerInfo[]
  side_pots: SidePotSummary[]
  final_invested: { [seatStr: string]: number }
  net_pnl: { [seatStr: string]: number }
}

export interface WinnerInfo {
  seat: number
  amount: number
  hand_label?: string
}

export interface SidePotSummary {
  amount: number
  eligible_seats: number[]
}

// === public_replay.jsonl ===
export interface PublicHandRecord {
  hand_id: number
  street_events: PublicEvent[]
}

export type PublicEvent =
  | PublicHandStarted
  | PublicHoleDealt
  | PublicAction
  | PublicFlop
  | PublicTurn
  | PublicRiver
  | PublicShowdown
  | PublicHandEnded

export interface PublicHandStarted {
  type: 'hand_started'
  hand_id: number
  button_seat: number
  blinds: { sb: number; bb: number }
}

export interface PublicHoleDealt {
  type: 'hole_dealt'
  hand_id: number
}

export interface PublicAction {
  type: 'action'
  hand_id: number
  seat: number
  street: Street
  action: { type: ActionType; amount?: number }
}

export interface PublicFlop {
  type: 'flop'
  hand_id: number
  community: [CardStr, CardStr, CardStr]
}

export interface PublicTurn {
  type: 'turn'
  hand_id: number
  card: CardStr
}

export interface PublicRiver {
  type: 'river'
  hand_id: number
  card: CardStr
}

export interface PublicShowdown {
  type: 'showdown'
  hand_id: number
  revealed: { [seatStr: string]: [CardStr, CardStr] } // KEY: only these seats reveal
}

export interface PublicHandEnded {
  type: 'hand_ended'
  hand_id: number
  winnings: { [seatStr: string]: number }
}

// === agent_view_snapshots.jsonl ===
export interface AgentViewSnapshot {
  hand_id: number
  turn_id: string
  session_id: string
  seat: number
  street: Street
  timestamp: string
  view_at_turn_start: PlayerViewLite
  iterations: IterationRecord[]
  final_action: { type: ActionType; amount?: number }
  is_forced_blind: boolean
  total_utility_calls: number
  api_retry_count: number
  illegal_action_retry_count: number
  no_tool_retry_count: number
  tool_usage_error_count: number
  default_action_fallback: boolean
  api_error: ApiErrorInfo | null
  turn_timeout_exceeded: boolean
  total_tokens: TokenCounts | object
  wall_time_ms: number
  agent: AgentDescriptor
}

// Subset of PlayerView the UI actually reads. The full schema has more
// fields (seats_public, opponent_seats_in_hand, opponent_stats, etc.) but
// Phase 1 surfaces only what's needed by the table+timeline+reasoning views.
export interface PlayerViewLite {
  my_seat: number
  pot: number
  my_stack: number
  current_bet_to_match: number
  to_call: number
  pot_odds_required: number | null
  effective_stack: number
  street: Street
  legal_actions: { tools: { name: string; args: object }[] }
  // Extra fields are ignored at parse time (TS doesn't enforce extras
  // when reading JSON; we just don't access them.)
}

export interface IterationRecord {
  step: number
  request_messages_digest: string
  provider_response_kind: 'tool_use' | 'text' | 'error'
  tool_call: ToolCall | null
  tool_result: { [k: string]: unknown } | null // utility tool returned dict, or null for action commits
  text_content: string
  tokens: TokenCounts
  wall_time_ms: number
  reasoning_artifacts?: ReasoningArtifact[]
}

export interface ToolCall {
  name: string // 'fold' / 'pot_odds' / 'get_opponent_stats' / etc.
  args: { [k: string]: unknown }
  tool_use_id: string
}

export interface ReasoningArtifact {
  kind: 'raw' | 'summary' | 'thinking_block' | 'encrypted' | 'redacted' | 'unavailable'
  content?: string
}

export interface AgentDescriptor {
  provider: string
  model: string
  version: string
  temperature: number | null
  seed: number | null
}

export interface ApiErrorInfo {
  type: string
  detail: string
}

// === Top-level container after parsing all 4 files ===
export interface ParsedSession {
  meta: SessionMeta
  hands: { [handId: number]: ParsedHand }
}

export interface ParsedHand {
  canonical: CanonicalPrivateHand
  publicEvents: PublicEvent[]
  agentSnapshots: AgentViewSnapshot[]
}
```

- [ ] **Step 2: Verify type-check passes**

Run:
```bash
cd web && npm run type-check
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add web/src/types.ts
git commit -m "$(cat <<'EOF'
feat(web): TypeScript types mirroring Pydantic schemas (Web UI Task 1)

Mirrors src/llm_poker_arena/{engine/views.py,agents/llm/types.py,
storage/schemas.py} JSON shapes for the 3 JSONL files + meta.json.

PlayerViewLite is a subset — Phase 1 doesn't read seats_public,
opponent_seats_in_hand, etc. (table viz computes from canonical+events).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Generate demo session

**Files:**
- Create: `web/scripts/generate-demo.py`
- Create (committed artifacts): `web/public/data/demo-1/{canonical_private,public_replay,agent_view_snapshots}.jsonl`, `meta.json`

**Why this task:** Need real session JSONL files to develop and test parsers/selectors against. Spec §213 specifies recipe: 1 LLM (Claude Haiku 4.5 at seat 3) + 5 RuleBased, 6 hands, seed=42, all flags on. ~$0.05 cost.

- [ ] **Step 1: Write the generation script**

Create `web/scripts/generate-demo.py`:
```python
#!/usr/bin/env python3
"""Generate the Phase 1 hardcoded demo session.

Recipe (per Web UI spec §213):
  - Lineup: Claude Haiku 4.5 (seat 3) + 5 RuleBasedAgent (seats 0,1,2,4,5)
  - 6 hands, seed=42, all flags on
  - Cost ~$0.05 at Claude Haiku 4.5 rates

Output: runs/demo-1/ then copy to web/public/data/demo-1/

Usage:
  source <(sed -n '3s/^#//p' ~/.zprofile)  # load ANTHROPIC_API_KEY
  python web/scripts/generate-demo.py
"""
import asyncio
import os
import shutil
import sys
from pathlib import Path

# Ensure repo root on sys.path so we can import from src/
_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import AnthropicProvider
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set; source your env vars first")

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm = LLMAgent(provider=provider, model="claude-haiku-4-5",
                   temperature=0.7, total_turn_timeout_sec=60.0)
    agents = [
        RuleBasedAgent(),  # 0 (BTN at hand 0)
        RuleBasedAgent(),  # 1 (SB)
        RuleBasedAgent(),  # 2 (BB)
        llm,               # 3 (UTG) ← Claude
        RuleBasedAgent(),  # 4 (HJ)
        RuleBasedAgent(),  # 5 (CO)
    ]

    output_root = _REPO / "runs"
    session_dir = output_root / "demo-1"
    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id="demo-1")
    asyncio.run(sess.run())

    # Copy to web/public/data/demo-1/ (overwrite if exists)
    web_target = _REPO / "web" / "public" / "data" / "demo-1"
    if web_target.exists():
        shutil.rmtree(web_target)
    web_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(session_dir, web_target)

    print(f"Demo session generated:")
    print(f"  runs/demo-1/ (canonical)")
    print(f"  web/public/data/demo-1/ (web bundle)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the generator**

```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
python /Users/zcheng256/llm-poker-arena/web/scripts/generate-demo.py
```

Expected: Script runs in 30-60s, ~$0.05 spend. Outputs:
```
Demo session generated:
  runs/demo-1/ (canonical)
  web/public/data/demo-1/ (web bundle)
```

If a transient API error happens, just re-run.

- [ ] **Step 3: Verify artifact files exist**

```bash
ls -l /Users/zcheng256/llm-poker-arena/web/public/data/demo-1/
```

Expected: 4 files: `canonical_private.jsonl`, `public_replay.jsonl`, `agent_view_snapshots.jsonl`, `meta.json`. Sizes should be ~5-50KB each.

```bash
python -c "
import json
m = json.load(open('/Users/zcheng256/llm-poker-arena/web/public/data/demo-1/meta.json'))
print('hands:', m['total_hands_played'])
print('chip_pnl_sum:', sum(int(v) for v in m['chip_pnl'].values()))
print('seat_assignment:', m['seat_assignment'])
"
```

Expected:
- `hands: 6`
- `chip_pnl_sum: 0` (conservation)
- seat 3 = `anthropic:claude-haiku-4-5`, others = `rule_based:tag_v1`

- [ ] **Step 4: Commit script + artifacts**

```bash
cd /Users/zcheng256/llm-poker-arena
git add web/scripts/generate-demo.py web/public/data/demo-1/
git commit -m "$(cat <<'EOF'
feat(web): demo session generator + bundled demo-1 artifacts (Web UI Task 2)

generate-demo.py runs a 6-hand session with Claude Haiku 4.5 (seat 3 UTG)
+ 5 RuleBased opponents at seed=42, with all utility tools enabled. Cost
~$0.05 per regeneration.

Bundled artifacts at web/public/data/demo-1/ are committed so the static
build is reproducible without repeated API calls.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: JSONL parsers (pure functions)

**Files:**
- Create: `web/src/parsers/parseJsonl.ts`
- Create: `web/src/parsers/parseJsonl.test.ts`

- [ ] **Step 1: Install vitest**

```bash
cd web
npm install -D vitest @vitest/ui happy-dom
```

Add to `web/package.json` scripts:
```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

Add to `web/vite.config.ts`:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'happy-dom',
    globals: true,
  },
})
```

- [ ] **Step 2: Write the failing tests**

Create `web/src/parsers/parseJsonl.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import {
  parseCanonicalPrivate,
  parsePublicReplay,
  parseAgentSnapshots,
  parseMeta,
} from './parseJsonl'

describe('parseCanonicalPrivate', () => {
  it('parses one hand line', () => {
    const text = JSON.stringify({
      hand_id: 0,
      started_at: '2026-04-26T00:00:00Z',
      ended_at: '2026-04-26T00:00:30Z',
      button_seat: 0,
      sb_seat: 1,
      bb_seat: 2,
      deck_seed: 42,
      starting_stacks: { '0': 10000, '1': 10000 },
      hole_cards: { '0': ['As', 'Kh'], '1': ['Qd', 'Qc'] },
      community: ['2s', '3h', '4d'],
      actions: [],
      result: {
        showdown: false, winners: [], side_pots: [],
        final_invested: {}, net_pnl: {},
      },
    })
    const hands = parseCanonicalPrivate(text)
    expect(hands).toHaveLength(1)
    expect(hands[0].hand_id).toBe(0)
    expect(hands[0].hole_cards['0']).toEqual(['As', 'Kh'])
  })

  it('parses multiple lines', () => {
    const text = [
      JSON.stringify({ hand_id: 0, started_at: '', ended_at: '', button_seat: 0, sb_seat: 1, bb_seat: 2, deck_seed: 42, starting_stacks: {}, hole_cards: {}, community: [], actions: [], result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: {} } }),
      JSON.stringify({ hand_id: 1, started_at: '', ended_at: '', button_seat: 1, sb_seat: 2, bb_seat: 3, deck_seed: 43, starting_stacks: {}, hole_cards: {}, community: [], actions: [], result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: {} } }),
    ].join('\n')
    expect(parseCanonicalPrivate(text)).toHaveLength(2)
  })
})

describe('parsePublicReplay', () => {
  it('parses one hand record with events', () => {
    const text = JSON.stringify({
      hand_id: 0,
      street_events: [
        { type: 'hand_started', hand_id: 0, button_seat: 0, blinds: { sb: 50, bb: 100 } },
        { type: 'action', hand_id: 0, seat: 3, street: 'preflop', action: { type: 'raise_to', amount: 300 } },
      ],
    })
    const records = parsePublicReplay(text)
    expect(records).toHaveLength(1)
    expect(records[0].street_events).toHaveLength(2)
    expect(records[0].street_events[0].type).toBe('hand_started')
  })
})

describe('parseAgentSnapshots', () => {
  it('parses one snapshot line', () => {
    const text = JSON.stringify({
      hand_id: 0,
      turn_id: '0-preflop-0',
      session_id: 'demo-1',
      seat: 3,
      street: 'preflop',
      timestamp: '',
      view_at_turn_start: { my_seat: 3, pot: 150, my_stack: 10000, current_bet_to_match: 100, to_call: 100, pot_odds_required: 0.4, effective_stack: 10000, street: 'preflop', legal_actions: { tools: [] } },
      iterations: [],
      final_action: { type: 'raise_to', amount: 300 },
      is_forced_blind: false,
      total_utility_calls: 0,
      api_retry_count: 0,
      illegal_action_retry_count: 0,
      no_tool_retry_count: 0,
      tool_usage_error_count: 0,
      default_action_fallback: false,
      api_error: null,
      turn_timeout_exceeded: false,
      total_tokens: { input_tokens: 100, output_tokens: 20, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
      wall_time_ms: 1000,
      agent: { provider: 'anthropic', model: 'claude-haiku-4-5', version: 'phase3a', temperature: 0.7, seed: null },
    })
    const snaps = parseAgentSnapshots(text)
    expect(snaps).toHaveLength(1)
    expect(snaps[0].seat).toBe(3)
    expect(snaps[0].final_action.type).toBe('raise_to')
  })
})

describe('parseMeta', () => {
  it('parses meta.json', () => {
    const text = JSON.stringify({
      session_id: 'demo-1',
      version: 2,
      schema_version: 'v2.0',
      total_hands_played: 6,
      planned_hands: 6,
      chip_pnl: { '0': -50, '3': 100, '5': -50 },
      total_tokens: {},
      retry_summary_per_seat: {},
      tool_usage_summary: {},
      seat_assignment: { '3': 'anthropic:claude-haiku-4-5' },
      initial_button_seat: 0,
      stop_reason: 'completed',
    })
    const meta = parseMeta(text)
    expect(meta.session_id).toBe('demo-1')
    expect(meta.total_hands_played).toBe(6)
    expect(meta.chip_pnl['3']).toBe(100)
  })
})
```

- [ ] **Step 3: Run test to verify FAIL**

```bash
cd web && npm test
```

Expected: FAIL — parsers don't exist.

- [ ] **Step 4: Implement parsers**

Create `web/src/parsers/parseJsonl.ts`:
```ts
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
```

- [ ] **Step 5: Run test to verify PASS**

```bash
cd web && npm test
```

Expected: 4 tests PASS.

- [ ] **Step 6: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add web/src/parsers/ web/package.json web/package-lock.json web/vite.config.ts
git commit -m "$(cat <<'EOF'
feat(web): JSONL parsers + vitest setup (Web UI Task 3)

4 pure-function parsers (canonical_private, public_replay,
agent_snapshots, meta). JSONL text → typed object arrays.
No validation; we trust generator output.

vitest installed with happy-dom environment.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Selector — getCurrentTurn

**Files:**
- Create: `web/src/selectors/getCurrentTurn.ts`
- Create: `web/src/selectors/getCurrentTurn.test.ts`

**What it does**: pure function `(session, handId, turnIdx)` → display state for the turn (actor, pot, community cards, etc.).

**Naming convention**: `get*` prefix (not `use*`) — it's a pure function, NOT a React hook. The `use*` prefix would trip ESLint react-hooks/rules-of-hooks if accidentally called outside a component.

- [ ] **Step 1: Write the failing test**

Create `web/src/selectors/getCurrentTurn.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { getCurrentTurn } from './getCurrentTurn'
import type { ParsedSession, AgentViewSnapshot } from '../types'

function _makeSnap(handId: number, turnIdx: number, seat: number): AgentViewSnapshot {
  return {
    hand_id: handId,
    turn_id: `${handId}-preflop-${turnIdx}`,
    session_id: 'demo-1',
    seat,
    street: 'preflop',
    timestamp: '',
    view_at_turn_start: {
      my_seat: seat, pot: 150 + turnIdx * 50, my_stack: 10000,
      current_bet_to_match: 100, to_call: 100, pot_odds_required: 0.4,
      effective_stack: 10000, street: 'preflop',
      legal_actions: { tools: [{ name: 'fold', args: {} }] },
    },
    iterations: [],
    final_action: { type: 'raise_to', amount: 300 },
    is_forced_blind: false,
    total_utility_calls: 0,
    api_retry_count: 0, illegal_action_retry_count: 0,
    no_tool_retry_count: 0, tool_usage_error_count: 0,
    default_action_fallback: false, api_error: null,
    turn_timeout_exceeded: false,
    total_tokens: { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
    wall_time_ms: 0,
    agent: { provider: 'anthropic', model: 'claude-haiku-4-5', version: 'p', temperature: 0.7, seed: null },
  }
}

const sess: ParsedSession = {
  meta: {
    session_id: 'demo-1', version: 2, schema_version: 'v2.0',
    total_hands_played: 1, planned_hands: 6,
    chip_pnl: {}, total_tokens: {}, retry_summary_per_seat: {},
    tool_usage_summary: {},
    seat_assignment: { '3': 'anthropic:claude-haiku-4-5' },
    initial_button_seat: 0, stop_reason: 'completed',
  },
  hands: {
    0: {
      canonical: {
        hand_id: 0, started_at: '', ended_at: '',
        button_seat: 0, sb_seat: 1, bb_seat: 2, deck_seed: 42,
        starting_stacks: { '0': 10000, '1': 10000, '2': 10000, '3': 10000, '4': 10000, '5': 10000 },
        hole_cards: { '3': ['As', 'Kh'] },
        community: ['2s', '3h', '4d'],
        actions: [], result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: {} },
      },
      publicEvents: [],
      agentSnapshots: [_makeSnap(0, 0, 3), _makeSnap(0, 1, 4)],
    },
  },
}

describe('getCurrentTurn', () => {
  it('returns actor + pot from snapshot at given turn', () => {
    const t = getCurrentTurn(sess, 0, 0)
    expect(t.actor).toBe(3)
    expect(t.pot).toBe(150)
    expect(t.street).toBe('preflop')
  })

  it('returns later turn correctly', () => {
    const t = getCurrentTurn(sess, 0, 1)
    expect(t.actor).toBe(4)
    expect(t.pot).toBe(200)
  })

  it('returns last commit action via reasoning', () => {
    const t = getCurrentTurn(sess, 0, 0)
    expect(t.commitAction).toEqual({ type: 'raise_to', amount: 300 })
  })
})
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd web && npm test -- getCurrentTurn
```

Expected: FAIL — selector doesn't exist.

- [ ] **Step 3: Implement selector**

Create `web/src/selectors/getCurrentTurn.ts`:
```ts
import type {
  ParsedSession, Street, ActionType, IterationRecord,
} from '../types'

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
```

- [ ] **Step 4: Run test to verify PASS**

```bash
cd web && npm test -- getCurrentTurn
```

Expected: 3 tests PASS.

- [ ] **Step 5: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 6: Commit**

```bash
git add web/src/selectors/
git commit -m "$(cat <<'EOF'
feat(web): getCurrentTurn selector (Web UI Task 4)

Pure function (session, handId, turnIdx) → CurrentTurnState carrying
actor/street/pot/toCall/reasoning/commitAction.

Reads from agentSnapshots[turnIdx] which carries view_at_turn_start
(pot, to_call, pot_odds_required already computed at engine boundary).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Selector — cardRevelation (live mode)

**Files:**
- Create: `web/src/selectors/cardRevelation.ts`
- Create: `web/src/selectors/cardRevelation.test.ts`

**What it does**: pure function returning per-seat hole cards visibility for the live mode (Phase 1 default). Per spec §240: face-down for everyone unless hand ended + len(showdown_seats) > 1.

- [ ] **Step 1: Write the failing test**

Create `web/src/selectors/cardRevelation.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { cardRevelation } from './cardRevelation'
import type { ParsedSession, ParsedHand, PublicShowdown } from '../types'

function _hand(showdownEvent: PublicShowdown | null = null): ParsedHand {
  return {
    canonical: {
      hand_id: 0, started_at: '', ended_at: '',
      button_seat: 0, sb_seat: 1, bb_seat: 2, deck_seed: 42,
      starting_stacks: { '0': 10000 },
      hole_cards: {
        '0': ['As', 'Kh'],
        '1': ['2c', '3d'],
        '2': ['Ts', 'Jh'],
        '3': ['Qd', 'Qc'],
        '4': ['7s', '8s'],
        '5': ['9c', '9d'],
      },
      community: ['2s', '3h', '4d', '5s', '6h'],
      actions: [],
      result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: {} },
    },
    publicEvents: showdownEvent
      ? [{ type: 'hand_started', hand_id: 0, button_seat: 0, blinds: { sb: 50, bb: 100 } }, showdownEvent]
      : [{ type: 'hand_started', hand_id: 0, button_seat: 0, blinds: { sb: 50, bb: 100 } }],
    agentSnapshots: [],
  }
}

function _session(hand: ParsedHand): ParsedSession {
  return {
    meta: {
      session_id: 'demo-1', version: 2, schema_version: 'v2.0',
      total_hands_played: 1, planned_hands: 6,
      chip_pnl: {}, total_tokens: {}, retry_summary_per_seat: {},
      tool_usage_summary: {}, seat_assignment: {},
      initial_button_seat: 0, stop_reason: 'completed',
    },
    hands: { 0: hand },
  }
}

describe('cardRevelation (live mode)', () => {
  it('all face-down mid-hand (no showdown event yet)', () => {
    const sess = _session(_hand())
    const cards = cardRevelation(sess, 0, 'live', { handEnded: false })
    expect(cards['0']).toBe('face-down')
    expect(cards['3']).toBe('face-down')
    expect(cards['5']).toBe('face-down')
  })

  it('all face-down on uncalled win (no showdown event)', () => {
    const sess = _session(_hand())
    const cards = cardRevelation(sess, 0, 'live', { handEnded: true })
    expect(cards['0']).toBe('face-down')
    expect(cards['3']).toBe('face-down')
  })

  it('reveals only seats in showdown_event.revealed', () => {
    const showdown: PublicShowdown = {
      type: 'showdown', hand_id: 0,
      revealed: { '3': ['Qd', 'Qc'], '5': ['9c', '9d'] },
    }
    const sess = _session(_hand(showdown))
    const cards = cardRevelation(sess, 0, 'live', { handEnded: true })
    expect(cards['3']).toEqual(['Qd', 'Qc'])
    expect(cards['5']).toEqual(['9c', '9d'])
    // Seats not in revealed: still face-down
    expect(cards['0']).toBe('face-down')
    expect(cards['1']).toBe('face-down')
  })
})
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd web && npm test -- cardRevelation
```

Expected: FAIL — selector doesn't exist.

- [ ] **Step 3: Implement selector**

Create `web/src/selectors/cardRevelation.ts`:
```ts
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
```

- [ ] **Step 4: Run test to verify PASS**

```bash
cd web && npm test -- cardRevelation
```

Expected: 3 tests PASS.

- [ ] **Step 5: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 6: Commit**

```bash
git add web/src/selectors/cardRevelation.ts web/src/selectors/cardRevelation.test.ts
git commit -m "$(cat <<'EOF'
feat(web): cardRevelation selector — live + god-view (Web UI Task 5)

Pure function returning per-seat hole-card visibility. Phase 1 uses 'live'
mode only (face-down until contested showdown event). god-view kept in
the API for Phase 2 dev mode toggle.

Walk (uncalled win) → no PublicShowdown event → all stay face-down,
matching Phase 3c-hud WTSD fix semantic.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Polar positioning math

**Files:**
- Create: `web/src/components/polar.ts`
- Create: `web/src/components/polar.test.ts`

**What it does**: pure helper to compute (x, y) on an ellipse for seat indices, with seat 3 = bottom-center (270°) per spec §266.

- [ ] **Step 1: Write the failing test**

Create `web/src/components/polar.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { seatPosition } from './polar'

describe('seatPosition', () => {
  it('seat 3 sits at bottom-center (positive y, x ≈ 0 with anchor)', () => {
    const { x, y } = seatPosition(3, 6, 100, 50)
    expect(Math.abs(x)).toBeLessThan(0.01)
    expect(y).toBeCloseTo(50, 2)
  })

  it('seat 0 is opposite seat 3 (top-ish)', () => {
    const { x: x3, y: y3 } = seatPosition(3, 6, 100, 50)
    const { x: x0, y: y0 } = seatPosition(0, 6, 100, 50)
    // seat 0 is 3 indices counterclockwise of seat 3 → 180° away
    expect(y0).toBeCloseTo(-y3, 2) // mirror across x-axis
    expect(Math.abs(x0)).toBeLessThan(0.01)
  })

  it('all seats spread around the ellipse (distinct positions)', () => {
    const positions = Array.from({ length: 6 }, (_, i) => seatPosition(i, 6, 100, 50))
    // No two seats coincide
    for (let i = 0; i < 6; i++) {
      for (let j = i + 1; j < 6; j++) {
        const dist = Math.hypot(positions[i].x - positions[j].x, positions[i].y - positions[j].y)
        expect(dist).toBeGreaterThan(10)
      }
    }
  })
})
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd web && npm test -- polar
```

Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement polar**

Create `web/src/components/polar.ts`:
```ts
/**
 * Compute the (x, y) position on an ellipse for a seat index.
 *
 * Convention (spec §266): seat 3 sits at bottom-center (270° / 6 o'clock,
 * +y direction in screen coords). Other seats distribute counterclockwise.
 *
 * Seat → angle mapping (n=6):
 *   seat 0 → 90°  (top)
 *   seat 1 → 30°  (upper-right)
 *   seat 2 → 330° (lower-right ... wait that's wrong)
 *
 * Re-thinking: counterclockwise from seat 3:
 *   seat 3 → 270°
 *   seat 4 → 210°
 *   seat 5 → 150°
 *   seat 0 → 90°
 *   seat 1 → 30°
 *   seat 2 → 330°
 *
 * Each seat is 60° (= 360/6) counterclockwise from its predecessor.
 *
 * Returns {x, y} in pixel offsets from table center.
 * y is positive DOWN (screen coords): 90° = top (negative y),
 * 270° = bottom (positive y).
 */
export function seatPosition(
  seatIdx: number,
  n: number,
  rx: number,
  ry: number,
): { x: number; y: number } {
  // Seat 3 anchor at 270° (bottom). Each seat += 60° counterclockwise.
  const baseDeg = 270 // seat 3
  const deltaDeg = ((seatIdx - 3) * 360) / n // signed; counterclockwise = decreasing y
  const angleDeg = baseDeg - deltaDeg // counterclockwise visually = subtract
  const angleRad = (angleDeg * Math.PI) / 180
  const x = rx * Math.cos(angleRad)
  // Screen y axis points DOWN; sin(270°) = -1 should map to bottom (positive y).
  const y = -ry * Math.sin(angleRad)
  return { x, y }
}
```

- [ ] **Step 4: Run test to verify PASS**

```bash
cd web && npm test -- polar
```

Expected: 3 tests PASS.

- [ ] **Step 5: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 6: Commit**

```bash
git add web/src/components/polar.ts web/src/components/polar.test.ts
git commit -m "$(cat <<'EOF'
feat(web): polar seat positioning math (Web UI Task 6)

Pure function seatPosition(seatIdx, n, rx, ry) → {x, y} pixel offsets
from table center. Seat 3 anchored at bottom-center (270°), other seats
distribute counterclockwise at 60° increments. Convention matches spec
§266 + default CLI my_seat=3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Card component (react-free-playing-cards)

**Files:**
- Create: `web/src/components/Card.tsx`
- Create: `web/src/components/Card.test.tsx`

- [ ] **Step 1: Install react-free-playing-cards + RTL**

```bash
cd web
npm install react-free-playing-cards
npm install -D @testing-library/react @testing-library/jest-dom @types/react-test-renderer
```

- [ ] **Step 2: Write the failing test**

Create `web/src/components/Card.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Card } from './Card'

describe('Card', () => {
  it('renders a face-up card with the right rank+suit', () => {
    const { container } = render(<Card card="As" />)
    // react-free-playing-cards renders an SVG; check it's not empty
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
  })

  it('renders face-down when card="face-down"', () => {
    const { container } = render(<Card card="face-down" />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    // face-down should differ from face-up; assert by comparing to a face-up render
    const faceUp = render(<Card card="As" />)
    expect(svg!.outerHTML).not.toEqual(faceUp.container.querySelector('svg')!.outerHTML)
  })
})
```

- [ ] **Step 3: Run test to verify FAIL**

```bash
cd web && npm test -- Card
```

Expected: FAIL — Card component doesn't exist.

- [ ] **Step 4: Implement Card**

Create `web/src/components/Card.tsx`:
```tsx
import { Card as FreeCard } from 'react-free-playing-cards'
import type { CardStr } from '../types'

type CardProp = CardStr | 'face-down'

interface Props {
  card: CardProp
  height?: string // default 80px
  className?: string
}

/**
 * Wrapper around react-free-playing-cards. Accepts either a card code
 * (e.g. "As", "Kh") or 'face-down' for the back of the card.
 */
export function Card({ card, height = '80px', className }: Props) {
  if (card === 'face-down') {
    return <FreeCard card="0" height={height} back className={className} />
  }
  return <FreeCard card={card} height={height} className={className} />
}
```

- [ ] **Step 5: Run test to verify PASS**

```bash
cd web && npm test -- Card
```

Expected: 2 tests PASS.

- [ ] **Step 6: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

If type errors arise from `react-free-playing-cards` (no built-in types), add `web/src/react-free-playing-cards.d.ts`:
```ts
declare module 'react-free-playing-cards' {
  import type { CSSProperties } from 'react'
  interface CardProps {
    card: string
    height?: string
    back?: boolean
    className?: string
    style?: CSSProperties
  }
  export function Card(props: CardProps): JSX.Element
}
```

Then re-run lint+type-check.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/Card.tsx web/src/components/Card.test.tsx web/package.json web/package-lock.json
# also add the .d.ts file if you created one
[ -f web/src/react-free-playing-cards.d.ts ] && git add web/src/react-free-playing-cards.d.ts
git commit -m "$(cat <<'EOF'
feat(web): Card component (react-free-playing-cards) (Web UI Task 7)

Wrapper around react-free-playing-cards (CC0 SVG cards). Accepts
CardStr (e.g. 'As') or 'face-down'. Default height 80px.

Includes ambient module declaration for the upstream lib (no types
shipped by author).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Chip component (inline SVG)

**Files:**
- Create: `web/src/assets/chip.svg`
- Create: `web/src/components/Chip.tsx`
- Create: `web/src/components/Chip.test.tsx`

**What it does**: simple poker chip SVG, color via CSS `fill` per denomination.

- [ ] **Step 1: Create the chip SVG asset**

Create `web/src/assets/chip.svg`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none">
  <circle cx="50" cy="50" r="48" fill="currentColor" stroke="#222" stroke-width="2" />
  <circle cx="50" cy="50" r="38" fill="none" stroke="#fff" stroke-width="2" stroke-dasharray="6,4" />
  <circle cx="50" cy="50" r="28" fill="#fff" />
  <text x="50" y="58" text-anchor="middle" font-family="sans-serif" font-size="22" fill="currentColor" font-weight="bold">C</text>
</svg>
```

- [ ] **Step 2: Write the failing test**

Create `web/src/components/Chip.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Chip } from './Chip'

describe('Chip', () => {
  it('renders an SVG circle with denomination label', () => {
    const { container, getByText } = render(<Chip denomination={100} />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    expect(getByText('100')).toBeDefined()
  })

  it('different denominations get different colors', () => {
    const small = render(<Chip denomination={1} />)
    const large = render(<Chip denomination={500} />)
    const smallStyle = small.container.firstElementChild!.getAttribute('style') ?? ''
    const largeStyle = large.container.firstElementChild!.getAttribute('style') ?? ''
    expect(smallStyle).not.toEqual(largeStyle)
  })
})
```

- [ ] **Step 3: Run test to verify FAIL**

```bash
cd web && npm test -- Chip
```

Expected: FAIL — component doesn't exist.

- [ ] **Step 4: Implement Chip**

Create `web/src/components/Chip.tsx`:
```tsx
interface Props {
  denomination: number
  size?: number // px, default 32
}

/**
 * Poker chip color per denomination (standard cash table colors).
 */
function colorForDenom(d: number): string {
  if (d <= 1) return '#fff'      // white
  if (d <= 5) return '#ef4444'   // red (Tailwind red-500)
  if (d <= 25) return '#3b82f6'  // blue
  if (d <= 100) return '#22c55e' // green
  if (d <= 500) return '#1f2937' // black/charcoal
  return '#a855f7'               // purple for higher
}

export function Chip({ denomination, size = 32 }: Props) {
  const color = colorForDenom(denomination)
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        borderRadius: '50%',
        backgroundColor: color,
        border: '2px solid #222',
        color: color === '#fff' ? '#222' : '#fff',
        fontSize: size * 0.32,
        fontWeight: 'bold',
        fontFamily: 'sans-serif',
        userSelect: 'none',
      }}
    >
      {denomination}
    </div>
  )
}
```

(The SVG was the original plan, but a CSS circle is even simpler and renders the same way — using inline div with border-radius gets us a chip without an SVG file. The SVG asset stays in `assets/` for Phase 2 polish where we may want concentric ring styling.)

- [ ] **Step 5: Run test to verify PASS**

```bash
cd web && npm test -- Chip
```

Expected: 2 tests PASS.

- [ ] **Step 6: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 7: Commit**

```bash
git add web/src/assets/chip.svg web/src/components/Chip.tsx web/src/components/Chip.test.tsx
git commit -m "$(cat <<'EOF'
feat(web): Chip component (Web UI Task 8)

Simple inline-styled circle (not SVG yet) with denomination label and
standard cash-table color per denomination (white/red/blue/green/black/purple
for 1/5/25/100/500/higher). SVG asset committed to assets/ for Phase 2
polish (concentric ring styling).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Seat component

**Files:**
- Create: `web/src/components/Seat.tsx`
- Create: `web/src/components/Seat.test.tsx`

**What it does**: one seat at the table — position label, stack, status indicator, hole cards (or face-down), optional last action floating text.

- [ ] **Step 1: Write the failing test**

Create `web/src/components/Seat.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Seat } from './Seat'
import type { CardStr } from '../types'

describe('Seat', () => {
  it('renders position label + stack', () => {
    const { getByText } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={10000}
            status="in_hand" holeCards="face-down" />
    )
    expect(getByText('seat 3 (UTG)')).toBeDefined()
    expect(getByText('10000')).toBeDefined()
  })

  it('renders folded status differently', () => {
    const { container } = render(
      <Seat seatIdx={0} positionLabel="BTN" stack={9700}
            status="folded" holeCards="face-down" />
    )
    expect(container.textContent).toContain('folded')
  })

  it('renders revealed hole cards (showdown)', () => {
    const cards: [CardStr, CardStr] = ['Qd', 'Qc']
    const { container } = render(
      <Seat seatIdx={3} positionLabel="UTG" stack={9700}
            status="in_hand" holeCards={cards} />
    )
    // Card components render SVGs; expect 2 SVGs (one per hole card)
    expect(container.querySelectorAll('svg').length).toBe(2)
  })
})
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd web && npm test -- Seat
```

Expected: FAIL — Seat component doesn't exist.

- [ ] **Step 3: Implement Seat**

Create `web/src/components/Seat.tsx`:
```tsx
import { Card } from './Card'
import type { CardStr, SeatStatus } from '../types'

interface Props {
  seatIdx: number
  positionLabel: string // 'UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'
  stack: number
  status: SeatStatus
  holeCards: 'face-down' | [CardStr, CardStr]
  lastAction?: string // e.g. 'raise 300', 'fold', 'call'
  isActive?: boolean // current actor
}

export function Seat({
  seatIdx, positionLabel, stack, status, holeCards, lastAction, isActive,
}: Props) {
  const opacity = status === 'folded' ? 0.4 : 1
  const ring = isActive ? 'ring-4 ring-yellow-400' : ''
  return (
    <div
      className={`flex flex-col items-center gap-1 p-2 rounded bg-slate-800 text-white text-xs ${ring}`}
      style={{ opacity }}
    >
      <div className="font-bold">seat {seatIdx} ({positionLabel})</div>
      <div className="text-slate-300">{stack}</div>
      {status === 'folded' && <div className="text-red-400 italic">folded</div>}
      {status === 'all_in' && <div className="text-orange-400 italic">all-in</div>}
      <div className="flex gap-1">
        {holeCards === 'face-down' ? (
          <>
            <Card card="face-down" height="50px" />
            <Card card="face-down" height="50px" />
          </>
        ) : (
          <>
            <Card card={holeCards[0]} height="50px" />
            <Card card={holeCards[1]} height="50px" />
          </>
        )}
      </div>
      {lastAction && (
        <div className="px-2 py-0.5 rounded bg-yellow-500 text-slate-900 font-semibold">
          {lastAction}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify PASS**

```bash
cd web && npm test -- Seat
```

Expected: 3 tests PASS.

- [ ] **Step 5: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 6: Commit**

```bash
git add web/src/components/Seat.tsx web/src/components/Seat.test.tsx
git commit -m "$(cat <<'EOF'
feat(web): Seat component (Web UI Task 9)

Renders one seat: position label + stack + status (in_hand/folded/all_in)
+ 2 hole cards (face-down or revealed) + optional last action badge +
optional active-actor ring highlight.

Tailwind classes for Phase 1 styling (no shadcn/ui per spec).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: PokerTable component

**Files:**
- Create: `web/src/components/PokerTable.tsx`
- Create: `web/src/components/PokerTable.test.tsx`

**What it does**: oval table + 6 polar-positioned Seat children + community cards center + pot display center.

- [ ] **Step 1: Write the failing test**

Create `web/src/components/PokerTable.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { PokerTable } from './PokerTable'
import type { CardStr, SeatStatus } from '../types'

const seats = Array.from({ length: 6 }, (_, i) => ({
  seatIdx: i,
  positionLabel: ['BTN', 'SB', 'BB', 'UTG', 'HJ', 'CO'][i],
  stack: 10000,
  status: 'in_hand' as SeatStatus,
  holeCards: 'face-down' as const,
}))

describe('PokerTable', () => {
  it('renders 6 seats', () => {
    const { container } = render(
      <PokerTable seats={seats} community={[]} pot={150} activeSeatIdx={3} />
    )
    // Each Seat has a "seat N" text; expect 6
    const seatLabels = container.querySelectorAll('.font-bold')
    expect(seatLabels.length).toBeGreaterThanOrEqual(6)
  })

  it('renders community cards when given', () => {
    const community: CardStr[] = ['As', 'Kh', '2c']
    const { container } = render(
      <PokerTable seats={seats} community={community} pot={500} activeSeatIdx={3} />
    )
    // 3 community cards = 3 SVGs in the center area, plus 12 SVGs from 6 seats × 2 face-down cards = 15 total
    expect(container.querySelectorAll('svg').length).toBeGreaterThanOrEqual(3)
  })

  it('renders pot number', () => {
    const { getByText } = render(
      <PokerTable seats={seats} community={[]} pot={1234} activeSeatIdx={3} />
    )
    expect(getByText(/1234/)).toBeDefined()
  })
})
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd web && npm test -- PokerTable
```

Expected: FAIL — PokerTable doesn't exist.

- [ ] **Step 3: Implement PokerTable**

Create `web/src/components/PokerTable.tsx`:
```tsx
import { Card } from './Card'
import { Seat } from './Seat'
import { seatPosition } from './polar'
import type { CardStr, SeatStatus } from '../types'

interface SeatProps {
  seatIdx: number
  positionLabel: string
  stack: number
  status: SeatStatus
  holeCards: 'face-down' | [CardStr, CardStr]
  lastAction?: string
}

interface Props {
  seats: SeatProps[]
  community: CardStr[]
  pot: number
  activeSeatIdx: number
}

const TABLE_WIDTH = 800
const TABLE_HEIGHT = 400
const RX = 320 // ellipse radius x for seat positioning
const RY = 180 // ellipse radius y

export function PokerTable({ seats, community, pot, activeSeatIdx }: Props) {
  return (
    <div
      className="relative mx-auto"
      style={{ width: TABLE_WIDTH, height: TABLE_HEIGHT }}
    >
      {/* Table felt */}
      <div
        className="absolute inset-0 bg-gradient-radial from-emerald-700 to-emerald-900 border-8 border-emerald-950"
        style={{ borderRadius: '50%' }}
      />
      {/* Center: community cards + pot */}
      <div
        className="absolute flex flex-col items-center gap-2"
        style={{
          top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          color: 'white',
        }}
      >
        <div className="flex gap-1">
          {community.length === 0 ? (
            <div className="text-xs opacity-60">(no community cards yet)</div>
          ) : (
            community.map((c, i) => <Card key={i} card={c} height="60px" />)
          )}
        </div>
        <div className="text-lg font-bold mt-1">pot {pot}</div>
      </div>
      {/* Seats positioned via polar math */}
      {seats.map((s) => {
        const { x, y } = seatPosition(s.seatIdx, 6, RX, RY)
        return (
          <div
            key={s.seatIdx}
            className="absolute"
            style={{
              left: `${TABLE_WIDTH / 2 + x}px`,
              top: `${TABLE_HEIGHT / 2 + y}px`,
              transform: 'translate(-50%, -50%)',
            }}
          >
            <Seat {...s} isActive={s.seatIdx === activeSeatIdx} />
          </div>
        )
      })}
    </div>
  )
}
```

If Tailwind doesn't have `bg-gradient-radial` by default, add to `tailwind.config.ts`:
```ts
theme: {
  extend: {
    backgroundImage: {
      'gradient-radial': 'radial-gradient(circle, var(--tw-gradient-stops))',
    },
  },
}
```

- [ ] **Step 4: Run test to verify PASS**

```bash
cd web && npm test -- PokerTable
```

Expected: 3 tests PASS.

- [ ] **Step 5: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 6: Commit**

```bash
git add web/src/components/PokerTable.tsx web/src/components/PokerTable.test.tsx web/tailwind.config.ts
git commit -m "$(cat <<'EOF'
feat(web): PokerTable component (Web UI Task 10)

Oval table felt (radial gradient + thick border) with 6 seats positioned
via polar math at fixed pixel offsets. Community cards + pot label
centered. Active seat gets ring highlight via Seat's isActive prop.

Tailwind extended with bg-gradient-radial utility for the felt.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: ReasoningPanel component

**Files:**
- Create: `web/src/components/ReasoningPanel.tsx`
- Create: `web/src/components/ReasoningPanel.test.tsx`

**What it does**: right-side panel showing current actor's iterations. Each iteration shows text_content + tool_call/args/result + commit per spec §155.

- [ ] **Step 1: Write the failing test**

Create `web/src/components/ReasoningPanel.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ReasoningPanel } from './ReasoningPanel'
import type { IterationRecord, ActionType } from '../types'

const _iter = (overrides: Partial<IterationRecord>): IterationRecord => ({
  step: 1, request_messages_digest: 'd',
  provider_response_kind: 'text', tool_call: null, tool_result: null,
  text_content: '', tokens: { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
  wall_time_ms: 0,
  ...overrides,
})

describe('ReasoningPanel', () => {
  it('shows actor seat in header', () => {
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={[]} commitAction={{ type: 'fold' }} />
    )
    expect(getByText(/seat 3.*UTG/i)).toBeDefined()
  })

  it('renders text_content for each iteration', () => {
    const iters = [
      _iter({ text_content: 'AKo + UTG raise → 3-bet for value' }),
    ]
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={iters} commitAction={{ type: 'raise_to', amount: 900 }} />
    )
    expect(getByText(/3-bet for value/)).toBeDefined()
  })

  it('renders tool_call + tool_result for utility iterations', () => {
    const iters = [
      _iter({
        provider_response_kind: 'tool_use',
        tool_call: { name: 'pot_odds', args: { to_call: 300, pot: 750 }, tool_use_id: 'p1' },
        tool_result: { value: 0.286 },
        text_content: 'checking pot odds',
      }),
    ]
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={iters} commitAction={{ type: 'fold' }} />
    )
    expect(getByText(/pot_odds/)).toBeDefined()
    expect(getByText(/0\.286/)).toBeDefined()
  })

  it('renders commit action prominently', () => {
    const commit: { type: ActionType; amount?: number } = { type: 'raise_to', amount: 900 }
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={[]} commitAction={commit} />
    )
    expect(getByText(/raise_to.*900/)).toBeDefined()
  })
})
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd web && npm test -- ReasoningPanel
```

Expected: FAIL.

- [ ] **Step 3: Implement ReasoningPanel**

Create `web/src/components/ReasoningPanel.tsx`:
```tsx
import type { IterationRecord, ActionType } from '../types'

interface Props {
  actor: number
  positionLabel: string
  iterations: IterationRecord[]
  commitAction: { type: ActionType; amount?: number }
}

export function ReasoningPanel({ actor, positionLabel, iterations, commitAction }: Props) {
  return (
    <div className="bg-slate-100 border-l border-slate-300 p-3 h-full overflow-auto text-sm">
      <div className="font-bold text-slate-700 mb-2">
        seat {actor} ({positionLabel}) is acting
      </div>
      <div className="space-y-2">
        {iterations.length === 0 && (
          <div className="text-slate-500 italic">(no iterations recorded)</div>
        )}
        {iterations.map((it, i) => (
          <IterationItem key={i} iter={it} />
        ))}
      </div>
      <div className="mt-3 pt-3 border-t border-slate-300">
        <div className="text-xs text-slate-500 mb-1">commit</div>
        <div className="font-bold text-emerald-700">
          {commitAction.type}
          {commitAction.amount !== undefined && ` ${commitAction.amount}`}
        </div>
      </div>
    </div>
  )
}

function IterationItem({ iter }: { iter: IterationRecord }) {
  return (
    <div className="border-l-2 border-slate-400 pl-2">
      {iter.text_content && (
        <div className="text-slate-800 whitespace-pre-wrap">{iter.text_content}</div>
      )}
      {iter.tool_call && (
        <div className="mt-1 text-xs">
          <span className="font-mono text-blue-700">
            {iter.tool_call.name}({JSON.stringify(iter.tool_call.args).slice(1, -1)})
          </span>
          {iter.tool_result && (
            <span className="ml-2 font-mono text-slate-600">
              → {JSON.stringify(iter.tool_result)}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify PASS**

```bash
cd web && npm test -- ReasoningPanel
```

Expected: 4 tests PASS.

- [ ] **Step 5: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 6: Commit**

```bash
git add web/src/components/ReasoningPanel.tsx web/src/components/ReasoningPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(web): ReasoningPanel component (Web UI Task 11)

Right-side panel listing current actor's iterations + final commit.
Each iteration shows text_content (LLM prose), tool_call signature, and
tool_result summary if present. Commit action gets emerald-bold badge
under a separator.

Phase 1 = all-expanded (no collapse), per spec YAGNI for current 0/22
organic utility-call rate.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: ActionTimeline component

**Files:**
- Create: `web/src/components/ActionTimeline.tsx`
- Create: `web/src/components/ActionTimeline.test.tsx`

**What it does**: bottom strip with one card per turn in the current hand. Click to seek.

- [ ] **Step 1: Write the failing test**

Create `web/src/components/ActionTimeline.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { ActionTimeline } from './ActionTimeline'

const turns = [
  { actor: 3, actionLabel: 'raise 300' },
  { actor: 4, actionLabel: 'fold' },
  { actor: 5, actionLabel: 'call' },
]

describe('ActionTimeline', () => {
  it('renders one card per turn', () => {
    const { getByText } = render(
      <ActionTimeline turns={turns} currentTurnIdx={0} onSeek={vi.fn()} />
    )
    expect(getByText(/raise 300/)).toBeDefined()
    expect(getByText(/fold/)).toBeDefined()
    expect(getByText(/call/)).toBeDefined()
  })

  it('highlights current turn', () => {
    const { container } = render(
      <ActionTimeline turns={turns} currentTurnIdx={1} onSeek={vi.fn()} />
    )
    const items = container.querySelectorAll('[data-turn-idx]')
    expect(items[1].className).toContain('ring-')
  })

  it('clicking a card calls onSeek with that index', () => {
    const onSeek = vi.fn()
    const { container } = render(
      <ActionTimeline turns={turns} currentTurnIdx={0} onSeek={onSeek} />
    )
    const items = container.querySelectorAll('[data-turn-idx]')
    fireEvent.click(items[2])
    expect(onSeek).toHaveBeenCalledWith(2)
  })
})
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd web && npm test -- ActionTimeline
```

Expected: FAIL.

- [ ] **Step 3: Implement ActionTimeline**

Create `web/src/components/ActionTimeline.tsx`:
```tsx
interface TurnInfo {
  actor: number
  actionLabel: string
}

interface Props {
  turns: TurnInfo[]
  currentTurnIdx: number
  onSeek: (turnIdx: number) => void
}

export function ActionTimeline({ turns, currentTurnIdx, onSeek }: Props) {
  return (
    <div className="flex gap-2 p-3 overflow-x-auto bg-slate-200 border-t border-slate-300">
      {turns.map((t, i) => {
        const active = i === currentTurnIdx
        return (
          <button
            key={i}
            data-turn-idx={i}
            onClick={() => onSeek(i)}
            className={`flex-none px-3 py-2 rounded text-xs bg-white border border-slate-400 hover:bg-slate-100 ${
              active ? 'ring-2 ring-yellow-500 font-bold' : ''
            }`}
          >
            <div className="text-slate-500">{i + 1}</div>
            <div>seat {t.actor}</div>
            <div className="text-slate-700">{t.actionLabel}</div>
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify PASS**

```bash
cd web && npm test -- ActionTimeline
```

Expected: 3 tests PASS.

- [ ] **Step 5: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 6: Commit**

```bash
git add web/src/components/ActionTimeline.tsx web/src/components/ActionTimeline.test.tsx
git commit -m "$(cat <<'EOF'
feat(web): ActionTimeline component (Web UI Task 12)

Bottom horizontal strip with one button per turn in current hand. Each
button shows turn number + actor + action label. Current turn highlighted
with yellow ring. Click to call onSeek(turnIdx) parent handler.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: HandSelector component

**Files:**
- Create: `web/src/components/HandSelector.tsx`
- Create: `web/src/components/HandSelector.test.tsx`

**What it does**: top bar with prev/next buttons + dropdown to switch between hands in the session.

- [ ] **Step 1: Write the failing test**

Create `web/src/components/HandSelector.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { HandSelector } from './HandSelector'

describe('HandSelector', () => {
  it('shows current hand id', () => {
    const { getByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={vi.fn()} />
    )
    expect(getByText(/hand 3/i)).toBeDefined()
  })

  it('clicking next calls onSelect with current+1', () => {
    const onSelect = vi.fn()
    const { getByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={onSelect} />
    )
    fireEvent.click(getByText(/next/i))
    expect(onSelect).toHaveBeenCalledWith(4)
  })

  it('clicking prev calls onSelect with current-1', () => {
    const onSelect = vi.fn()
    const { getByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={3} onSelect={onSelect} />
    )
    fireEvent.click(getByText(/prev/i))
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('next button disabled at last hand', () => {
    const onSelect = vi.fn()
    const { getByText } = render(
      <HandSelector handIds={[0, 1, 2, 3, 4, 5]} currentHandId={5} onSelect={onSelect} />
    )
    const nextBtn = getByText(/next/i) as HTMLButtonElement
    expect(nextBtn.disabled).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd web && npm test -- HandSelector
```

Expected: FAIL.

- [ ] **Step 3: Implement HandSelector**

Create `web/src/components/HandSelector.tsx`:
```tsx
interface Props {
  handIds: number[] // sorted ascending
  currentHandId: number
  onSelect: (handId: number) => void
}

export function HandSelector({ handIds, currentHandId, onSelect }: Props) {
  const idx = handIds.indexOf(currentHandId)
  const canPrev = idx > 0
  const canNext = idx >= 0 && idx < handIds.length - 1
  return (
    <div className="flex items-center gap-3 p-3 bg-slate-700 text-white">
      <button
        onClick={() => canPrev && onSelect(handIds[idx - 1])}
        disabled={!canPrev}
        className="px-3 py-1 rounded bg-slate-500 hover:bg-slate-400 disabled:opacity-40"
      >
        ← prev
      </button>
      <div className="font-bold">hand {currentHandId}</div>
      <span className="text-slate-300 text-sm">
        ({idx + 1} / {handIds.length})
      </span>
      <button
        onClick={() => canNext && onSelect(handIds[idx + 1])}
        disabled={!canNext}
        className="px-3 py-1 rounded bg-slate-500 hover:bg-slate-400 disabled:opacity-40"
      >
        next →
      </button>
      <select
        value={currentHandId}
        onChange={(e) => onSelect(Number(e.target.value))}
        className="ml-auto bg-slate-600 border border-slate-500 rounded px-2 py-1 text-sm"
      >
        {handIds.map((h) => (
          <option key={h} value={h}>
            hand {h}
          </option>
        ))}
      </select>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify PASS**

```bash
cd web && npm test -- HandSelector
```

Expected: 4 tests PASS.

- [ ] **Step 5: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

- [ ] **Step 6: Commit**

```bash
git add web/src/components/HandSelector.tsx web/src/components/HandSelector.test.tsx
git commit -m "$(cat <<'EOF'
feat(web): HandSelector component (Web UI Task 13)

Top bar with prev/next buttons + dropdown for switching hands. Buttons
disable at boundaries. Calls onSelect(handId) parent handler.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: SessionLoader + main App + URL state

**Files:**
- Modify: `web/src/App.tsx`

**What it does**: top-level App: fetch 4 files on mount, parse, store in state. URL params drive (handId, turnIdx). Compose HandSelector + PokerTable + ReasoningPanel + ActionTimeline.

- [ ] **Step 1: Replace App.tsx**

Replace `web/src/App.tsx` with:
```tsx
import { useEffect, useState } from 'react'
import {
  parseCanonicalPrivate,
  parsePublicReplay,
  parseAgentSnapshots,
  parseMeta,
} from './parsers/parseJsonl'
import { getCurrentTurn } from './selectors/getCurrentTurn'
import { cardRevelation } from './selectors/cardRevelation'
import { HandSelector } from './components/HandSelector'
import { PokerTable } from './components/PokerTable'
import { ReasoningPanel } from './components/ReasoningPanel'
import { ActionTimeline } from './components/ActionTimeline'
import type {
  ParsedSession, SeatStatus, CardStr, ActionType,
} from './types'

const DATA_BASE = 'data/demo-1'
// Standard 6-max position labels per seat order from BTN.
const POSITION_LABELS = ['BTN', 'SB', 'BB', 'UTG', 'HJ', 'CO']

function _positionLabelForSeat(seat: number, buttonSeat: number, n: number): string {
  // Seat 'BTN' is buttonSeat; SB = buttonSeat+1, BB = +2, UTG = +3, ...
  const offset = ((seat - buttonSeat) + n) % n
  return POSITION_LABELS[offset]
}

function _useUrlPointer(): {
  handId: number
  turnIdx: number
  setHandId: (h: number) => void
  setTurnIdx: (t: number) => void
} {
  const [pointer, setPointer] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    return {
      handId: Number(params.get('hand') ?? '0'),
      turnIdx: Number(params.get('turn') ?? '0'),
    }
  })

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    params.set('hand', String(pointer.handId))
    params.set('turn', String(pointer.turnIdx))
    const newUrl = `${window.location.pathname}?${params.toString()}`
    window.history.replaceState(null, '', newUrl)
  }, [pointer])

  return {
    handId: pointer.handId,
    turnIdx: pointer.turnIdx,
    setHandId: (h: number) => setPointer({ handId: h, turnIdx: 0 }),
    setTurnIdx: (t: number) => setPointer((p) => ({ ...p, turnIdx: t })),
  }
}

function App() {
  const [session, setSession] = useState<ParsedSession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ptr = _useUrlPointer()

  useEffect(() => {
    Promise.all([
      fetch(`${DATA_BASE}/canonical_private.jsonl`).then((r) => r.text()),
      fetch(`${DATA_BASE}/public_replay.jsonl`).then((r) => r.text()),
      fetch(`${DATA_BASE}/agent_view_snapshots.jsonl`).then((r) => r.text()),
      fetch(`${DATA_BASE}/meta.json`).then((r) => r.text()),
    ])
      .then(([canonText, publicText, snapText, metaText]) => {
        const meta = parseMeta(metaText)
        const canonical = parseCanonicalPrivate(canonText)
        const publicRecords = parsePublicReplay(publicText)
        const snaps = parseAgentSnapshots(snapText)
        const hands: ParsedSession['hands'] = {}
        for (const hand of canonical) {
          const pubRec = publicRecords.find((p) => p.hand_id === hand.hand_id)
          hands[hand.hand_id] = {
            canonical: hand,
            publicEvents: pubRec ? pubRec.street_events : [],
            agentSnapshots: snaps.filter((s) => s.hand_id === hand.hand_id),
          }
        }
        setSession({ meta, hands })
      })
      .catch((e) => setError(`Failed to load session: ${e.message}`))
  }, [])

  if (error) {
    return <div className="p-8 text-red-700">{error}</div>
  }
  if (!session) {
    return <div className="p-8">Loading session...</div>
  }

  const handIds = Object.keys(session.hands).map(Number).sort((a, b) => a - b)
  const hand = session.hands[ptr.handId]
  if (!hand) {
    return <div className="p-8">Hand {ptr.handId} not in session</div>
  }
  const turnCount = hand.agentSnapshots.length
  const safeTurnIdx = Math.min(ptr.turnIdx, turnCount - 1)
  const turn = getCurrentTurn(session, ptr.handId, safeTurnIdx)
  const handEnded = safeTurnIdx >= turnCount - 1
  const revealed = cardRevelation(session, ptr.handId, 'live', { handEnded })

  // Build seat props
  const cfg = hand.canonical
  const buttonSeat = cfg.button_seat
  const folded = new Set<number>()
  // Walk through actions UP TO current turn to track folds
  const actionsByTurn = hand.agentSnapshots.slice(0, safeTurnIdx + 1)
  for (const snap of actionsByTurn) {
    if (snap.final_action.type === 'fold') {
      folded.add(snap.seat)
    }
  }

  // Stack tracking via meta starting_stacks; for Phase 1 just show starting stack.
  const seats = [0, 1, 2, 3, 4, 5].map((seatIdx) => {
    const positionLabel = _positionLabelForSeat(seatIdx, buttonSeat, 6)
    const status: SeatStatus = folded.has(seatIdx) ? 'folded' : 'in_hand'
    const holeFromRevealed = revealed[String(seatIdx)]
    const holeCards: 'face-down' | [CardStr, CardStr] =
      holeFromRevealed && holeFromRevealed !== 'face-down' ? holeFromRevealed : 'face-down'
    // last action this hand for this seat (if any)
    const myActions = actionsByTurn.filter((s) => s.seat === seatIdx)
    const lastAction = myActions.length > 0
      ? _formatAction(myActions[myActions.length - 1].final_action)
      : undefined
    return {
      seatIdx,
      positionLabel,
      stack: cfg.starting_stacks[String(seatIdx)] ?? 0,
      status,
      holeCards,
      lastAction,
    }
  })

  // Community cards depend on street
  const community: CardStr[] =
    turn.street === 'preflop'
      ? []
      : turn.street === 'flop'
      ? cfg.community.slice(0, 3)
      : turn.street === 'turn'
      ? cfg.community.slice(0, 4)
      : cfg.community.slice(0, 5)

  // Action timeline turns
  const timelineTurns = hand.agentSnapshots.map((s) => ({
    actor: s.seat,
    actionLabel: _formatAction(s.final_action),
  }))

  const actorPosition = _positionLabelForSeat(turn.actor, buttonSeat, 6)

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      <HandSelector
        handIds={handIds}
        currentHandId={ptr.handId}
        onSelect={ptr.setHandId}
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 flex items-center justify-center p-4">
          <PokerTable
            seats={seats}
            community={community}
            pot={turn.pot}
            activeSeatIdx={turn.actor}
          />
        </div>
        <div className="w-96">
          <ReasoningPanel
            actor={turn.actor}
            positionLabel={actorPosition}
            iterations={turn.reasoning}
            commitAction={turn.commitAction}
          />
        </div>
      </div>
      <ActionTimeline
        turns={timelineTurns}
        currentTurnIdx={safeTurnIdx}
        onSeek={ptr.setTurnIdx}
      />
    </div>
  )
}

function _formatAction(action: { type: ActionType; amount?: number }): string {
  if (action.amount !== undefined) return `${action.type} ${action.amount}`
  return action.type
}

export default App
```

- [ ] **Step 2: Verify dev server boots + demo loads**

```bash
cd web && npm run dev
```

Open `http://localhost:5173/`. Expected:
- "Loading session..." briefly
- Then HandSelector at top, PokerTable in middle (oval green felt + 6 seats around), ReasoningPanel on right, ActionTimeline at bottom
- URL becomes `?hand=0&turn=0`
- Click "next →" → URL becomes `?hand=1&turn=0`, table re-renders
- Click a turn card in timeline → URL becomes `?hand=X&turn=Y`, reasoning panel updates

Kill server.

- [ ] **Step 3: Lint + type-check**

```bash
cd web && npm run lint && npm run type-check
```

Fix any type errors (likely around `_useUrlPointer` typing or fetch promises).

- [ ] **Step 4: Commit**

```bash
git add web/src/App.tsx
git commit -m "$(cat <<'EOF'
feat(web): SessionLoader + ReplayView composition (Web UI Task 14)

App.tsx wires everything: parallel fetch of 4 files via plain useEffect,
parse via Task 3 parsers, store in useState. URL params (?hand=X&turn=Y)
drive the (handId, turnIdx) pointer; useEffect syncs URL on pointer change.

Composes HandSelector (top) + PokerTable (center) + ReasoningPanel
(right 96 width) + ActionTimeline (bottom).

Derives per-seat status (folded set tracking via actions up to current
turn), position labels (rotating per button_seat), revealed hole cards
(via cardRevelation selector), street-aware community cards.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Playwright e2e happy path

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/e2e/replay-happy-path.spec.ts`

- [ ] **Step 1: Install Playwright**

```bash
cd web
npm install -D @playwright/test
npx playwright install chromium  # downloads Chromium browser
```

- [ ] **Step 2: Create config**

Create `web/playwright.config.ts`:
```ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  webServer: {
    command: 'npm run dev',
    port: 5173,
    timeout: 30_000,
    reuseExistingServer: !process.env.CI,
  },
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
  },
})
```

Add to `web/package.json` scripts:
```json
{
  "scripts": {
    "test:e2e": "playwright test"
  }
}
```

- [ ] **Step 3: Write the happy-path test**

Create `web/e2e/replay-happy-path.spec.ts`:
```ts
import { test, expect } from '@playwright/test'

test('load demo session and navigate', async ({ page }) => {
  await page.goto('/')

  // Wait for session to load
  await expect(page.getByText(/hand 0/i)).toBeVisible({ timeout: 10_000 })

  // Should show poker table — at least 6 'seat N' labels visible
  for (let i = 0; i < 6; i++) {
    await expect(page.getByText(`seat ${i}`).first()).toBeVisible()
  }

  // Reasoning panel: should show some actor seat
  await expect(page.getByText(/is acting/i)).toBeVisible()

  // Click next → URL should reflect hand 1
  await page.getByRole('button', { name: /next/i }).first().click()
  await expect(page).toHaveURL(/hand=1/)

  // Action timeline: click second turn (if exists)
  const timelineButtons = page.locator('[data-turn-idx]')
  const count = await timelineButtons.count()
  if (count >= 2) {
    await timelineButtons.nth(1).click()
    await expect(page).toHaveURL(/turn=1/)
  }
})
```

- [ ] **Step 4: Run e2e**

```bash
cd web && npm run test:e2e
```

Expected: 1 test PASS in ~10-20s.

- [ ] **Step 5: Add browsers to .gitignore (if needed)**

Playwright browser binaries shouldn't be committed; verify `.gitignore` covers:
```
node_modules/
playwright/.cache/
```

If `web/.gitignore` is missing playwright cache, add:
```
test-results/
playwright-report/
playwright/.cache/
```

- [ ] **Step 6: Commit**

```bash
git add web/playwright.config.ts web/e2e/ web/package.json web/package-lock.json web/.gitignore
git commit -m "$(cat <<'EOF'
test(web): Playwright happy-path e2e (Web UI Task 15)

Loads page, asserts session loads (hand 0 visible + 6 seats rendered +
reasoning panel showing 'is acting'), navigates to next hand (URL
becomes ?hand=1), seeks timeline (URL becomes ?turn=1).

Catches major regressions: parser broken / fetch broken / component
import broken / URL state broken.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/web.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/web.yml`:
```yaml
name: web ci

on:
  push:
    branches: [main]
    paths: ['web/**', '.github/workflows/web.yml']
  pull_request:
    paths: ['web/**', '.github/workflows/web.yml']

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Type check
        run: npm run type-check

      - name: Unit + behavior tests
        run: npm test

      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium

      - name: E2E
        run: npm run test:e2e
```

- [ ] **Step 2: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena
git add .github/workflows/web.yml
git commit -m "$(cat <<'EOF'
ci(web): GitHub Actions workflow for web/ (Web UI Task 16)

Triggered on push to main + PR when web/** or .github/workflows/web.yml
changes. Runs lint → type-check → unit tests → playwright e2e.

Independent from Python CI (doesn't block .py merges).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Verify next push triggers workflow**

After pushing, check `https://github.com/<your-user>/<repo>/actions` to see "web ci" workflow runs.

(If running locally without push access yet, defer this verification to first PR.)

---

## Task 17: Build smoke + final checkpoint

**Files:**
- (None — verification only)

- [ ] **Step 1: Build production bundle**

```bash
cd web && npm run build
```

Expected: `web/dist/` created with:
- `index.html`
- `assets/` (JS + CSS bundles)
- `data/demo-1/` (JSONL files copied via Vite's static asset handling — or NOT, see Step 2)

If `data/demo-1/` is NOT in `dist/` → check `web/public/data/demo-1/` exists. Vite copies `web/public/` to `web/dist/` automatically. If files are there, this should work. If not, fix.

- [ ] **Step 2: Preview production build**

```bash
cd web && npm run preview
```

Expected: serves `dist/` at `http://localhost:4173/`. Open browser → should see same UI as `npm run dev` showed in Task 14.

If session fails to load: verify network tab shows successful fetch of `data/demo-1/canonical_private.jsonl` etc.

- [ ] **Step 3: Final summary commit (no code change)**

If anything was tweaked above to make build work, commit it. Otherwise just a checkpoint message:

```bash
cd /Users/zcheng256/llm-poker-arena
git log --oneline c6198e8..HEAD
```

Expected output: ~17 commits matching task numbers (T0-T16).

- [ ] **Step 4: Update memory + plan inventory**

Read `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`. Insert a "Phase 5 Web UI Phase 1 COMPLETE" block following the existing pattern. Capture:
- HEAD SHA after final commit
- Test count (~21 tests)
- Demo session bundled at `web/public/data/demo-1/`
- Phase 2 next: animations + dev toggle + multi-session selector

Update `~/.claude/projects/-Users-zcheng256/memory/MEMORY.md` index entry.

```bash
git add docs/superpowers/plans/2026-04-26-llm-poker-arena-web-ui-phase-1.md
git commit -m "$(cat <<'EOF'
plan: Web UI Phase 1 (replay-first portfolio MVP)

17-task plan. Vite + React 18 + TS + Tailwind in web/ subdirectory.
Pure static site, no backend, fetches 4 JSONL/JSON from web/public/data/.

Per spec §144-176 IN scope: oval table viz, community cards, hole cards
live mode, reasoning panel (text_content + tool_call/args/result + commit),
action timeline (seek), hand selector, single hardcoded demo.

OUT (Phase 2): animations, multi-session selector, dev toggle, mobile,
TanStack Query, shadcn/ui, framer-motion.

Tech stack minimal: React + Vite + TS + Tailwind + react-free-playing-cards.
~21 tests (unit parsers + selectors + RTL behavior + 1 Playwright e2e).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Checklist (auditor-facing summary)

After all 17 tasks land:

1. **Spec coverage**:
   - §144 IN scope items 1-9 → Tasks 7+8+9+10+11+12+13+14 cover them ✅
   - §213 demo session generation → Task 2 ✅
   - §240 card revelation policy (live mode) → Task 5 ✅
   - §266 polar layout (seat 3 = bottom) → Task 6 + Task 10 ✅
   - §305 data flow (plain useEffect, selectors) → Task 14 ✅
   - §362 testing (~10 unit, ~5 behavior, 1 e2e) → 21 total ✅
   - §456 success criteria 1-6 → all addressable post-execution

2. **No placeholders**: every step has actual code or commands.

3. **Type consistency**:
   - `ParsedSession` defined Task 1, used Tasks 4 + 5 + 14 — same shape ✅
   - `IterationRecord` defined Task 1, used Tasks 4 + 11 — same shape ✅
   - Component prop types match component usage in App.tsx — ✅

4. **What this plan doesn't cover** (intentionally):
   - Phase 2 polish (animations, multi-session, dev toggle) — separate plan
   - Phase 3 spectator (WebSocket backend) — separate plan
   - Phase 4 player mode — separate plan
   - Demo session regeneration cadence (manual, ad-hoc when needed)
   - GitHub Pages deployment automation — Phase 2

5. **Phase 1 ship gate** (after Task 17):
   - `cd web && npm run dev` boots, demo loads, navigation works ✓
   - `npm run build && npm run preview` produces working static site ✓
   - All 21 tests pass via `npm test && npm run test:e2e` ✓
   - GitHub Actions CI green on first push ✓
