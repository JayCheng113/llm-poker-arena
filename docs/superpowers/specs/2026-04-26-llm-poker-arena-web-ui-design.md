# llm-poker-arena Web UI Design Spec

**Date**: 2026-04-26
**Status**: Brainstorm complete; ready for plan
**Phase**: Phase 5 / Web UI

## Goal

Ship a browser-based replay viewer for `llm-poker-arena` sessions. Phase 1
delivers a working portfolio-grade demo (1 week); Phase 2 adds polish.
Phase 3+ adds live spectator and player modes (deferred).

The Web UI is the project's portfolio-facing surface — it's how recruiters,
collaborators, and the user themselves see "what does an LLM think about
when playing poker". Reasoning panel + poker table visualization are the
core differentiators.

## Motivation & Context

The CLI-only platform (Phases 1-4) shipped 468 tests + 4 LLM provider
integrations + HUD stats + cost cap. JSONL artifacts capture full hand
history, every LLM iteration's reasoning, and per-seat HUD stats. **The
data is rich; what's missing is a way to share it.**

Two audiences drive this design:
1. **External viewers** (recruiters, prospective collaborators): want a
   polished, immediate-load demo. No installation, no command line.
2. **The user themselves** (debug + demo): wants drill-down into LLM
   reasoning, raw JSON view, dev mode toggle.

Hence "portfolio + dev toggle" (D from Q2): default UX is portfolio-grade,
toggle exposes raw data.

## Decisions Summary

Brainstormed 7 questions:

| # | Decision | Rationale |
|---|---|---|
| 1 | **MVP scope = Replay-first (A)** | No backend needed, fastest to portfolio-demo |
| 2 | **Audience = portfolio + dev toggle (D)** | Dual use; ~30% extra effort vs portfolio-only |
| 3 | **Deployment = both static + dev server (C)** | Static for portfolio link, dev for local debug |
| 4 | **Layout = full poker table viz (A)** | Visual differentiation for portfolio |
| 5 | **Hand navigation = auto-play + seek bar (D)** | Video-player UX for spectators, seek for drill-down |
| 6 | **Card revelation = toggle (D)** | Spec §10 default: live experience; dev override god-view |
| 7 | **Reasoning panel = right + bottom timeline (D)** | Reasoning is the differentiator; timeline enables drill-down |

Plus testing simplifications:
- Drop snapshot tests (noise > value); replace with React Testing Library
  behavior tests
- Keep Playwright (1 happy-path)
- Drop husky pre-commit; CI lints

Execution path: **Layered MVP (B)** — Phase 1 ship-able in ~1 week, Phase 2
polish ~1 week, Phase 3+ deferred.

## Tech Stack & Assets

**Stack** (per spec §10):
- React 18 + Vite + TypeScript
- Tailwind CSS + shadcn/ui (component primitives)
- TanStack Query (fetch caching)
- framer-motion (animations, Phase 2 only)

**Card asset**:
- `react-free-playing-cards` (npm) — CC0 license, SVG cards via simple
  `<Card card="As" />` API. Adrian Kennard design.
- Backup: `htdebeer/SVG-cards` (LGPL-2.1, comprehensive sprite via
  `<use>`)

**Chip asset**:
- 1-2 SVG files inline in `web/src/assets/chip.svg`, recolored via CSS
  `fill` per denomination (white/red/blue/green/black for 1/5/25/100/500).
- Source: SVG Repo `/svg/4886/poker-chip` or FreeSVG.org (both CC0/free
  commercial)

**Table background**:
- Pure Tailwind: `bg-gradient-radial from-emerald-700 to-emerald-900` +
  `rounded-[120px/50%]`. No image asset.

**Layout reference (read-only, do NOT vendor)**:
- `Mikhail-MM/React-Poker` and `sergij14/poker-table` for polar seat
  positioning math (`cos(θ)/sin(θ)` for ellipse arrangement). Self-implement
  ~10 lines based on their pattern.

## Architecture

**Repo structure**:
```
llm-poker-arena/
├── src/                       # Python (existing, unchanged)
├── tests/                     # Python (existing, unchanged)
├── runs/                      # Session artifacts (already gitignored)
├── web/                       # NEW
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── public/
│   │   └── data/              # Bundled demo sessions for static build
│   │       └── demo-1/
│   │           ├── canonical_private.jsonl
│   │           ├── public_replay.jsonl
│   │           ├── agent_view_snapshots.jsonl
│   │           └── meta.json
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/        # React components (~10 files)
│   │   ├── parsers/           # JSONL → typed objects
│   │   ├── selectors/         # Pure functions deriving display state
│   │   ├── types.ts           # TS types mirroring Pydantic schemas
│   │   └── assets/            # Inline SVGs (chips, etc.)
│   ├── e2e/                   # Playwright tests
│   └── scripts/
│       └── bundle-demos.mjs   # Phase 2: copy selected sessions to public/data/
└── docs/superpowers/specs/2026-04-26-llm-poker-arena-web-ui-design.md
```

**Backend**: NONE for Phase 1+2. React fetches static JSONL files via
plain `fetch`. Two data source modes (single Vite flag):
- `VITE_MODE=dev`: `fetch('/runs/<session_id>/...')` — Vite serves
  `../runs/` via custom middleware
- `VITE_MODE=static`: `fetch('/data/<session_id>/...')` — sessions
  bundled in `dist/data/` at build time

**State**: React `useState` + TanStack Query for fetch caching. URL params
(`?session=X&hand=Y&turn=Z&mode=live`) drive deep linking; URL is
single source of truth, useState mirrors it.

**No global state library** (Redux/Zustand) — selectors compute derived
state from session data + URL pointer; React's tree handles propagation.

## Phase 1 MVP Scope (~1 week)

**IN scope**:
1. Poker table visualization: oval table + 6 seats arranged via polar
   coordinates; seat labels (position + stack + status indicator)
2. Community cards display (centered, text-based suit chars or SVG cards)
3. Hole cards: per-seat, visibility per spec §10 default (live experience —
   only revealed at showdown)
4. Pot display (centered number)
5. Action indicator: highlight active seat; show last action text floating
   near the seat
6. **Reasoning panel** (right side, ~25-30% width): all iterations of
   current actor (utility tool calls + final commit), each iteration shows
   tool_call name + args + tool_result. Final commit text bold.
7. **Action timeline** (bottom): one card per turn in current hand,
   click to seek
8. Hand selector (top): dropdown or prev/next buttons
9. **Single hardcoded demo session**: bundle one real Claude 6-hand
   session (run from CLI, copy artifacts to `web/public/data/demo-1/`)

**OUT of Phase 1** (deferred to Phase 2):
- Auto-play animations (chip slide, card flip)
- Multi-session selector
- Dev mode toggle (god-view, raw JSON viewer)
- Session summary view
- Mobile responsive
- i18n

## Phase 2 Polish Scope (~1 week)

1. **Auto-play animations**:
   - 1s/action default, speed slider (0.5x/1x/2x/4x), pause button
   - Chip slide animation (framer-motion: actor → pot)
   - Active seat highlight (pulsating border)
   - Card flip on hole-card reveal

2. **Dev mode toggle** (`?dev=1` URL or settings panel):
   - God-view (always show all hole cards from `canonical_private.jsonl`)
   - Raw JSON viewer per turn (debug LLM decisions)
   - Retry counts / api_error / default_action_fallback red badges
   - reasoning_artifact.kind labels
     (raw / summary / thinking_block / encrypted / redacted)

3. **Session selector**:
   - Top dropdown listing bundled demo sessions
   - Dev mode: "load custom" button → file picker for local `runs/`

4. **Build pipeline**:
   - `web/scripts/bundle-demos.mjs` — copy selected session ids to
     `web/public/data/<id>/` before vite build
   - GitHub Actions workflow: build + deploy to gh-pages

5. **Session summary view**:
   - Toggle to "summary": chip P&L table + total tokens + retry summary +
     tool usage (all from `meta.json`)
   - Cross-hand stats table

6. **Mobile responsive (best-effort)**:
   - <768px: reasoning panel → bottom drawer (B layout fallback)
   - Timeline hides prev/next buttons
   - No promise of polished mobile UX

## Components Hierarchy

```
App
├── SessionLoader (TanStack Query: fetch + parse JSONL → cached)
└── ReplayView (main page)
    ├── HandHeader
    │   ├── HandSelector (1-of-N hand dropdown / prev-next)
    │   └── HandMeta (hand_id, button_seat, blinds)
    ├── PokerTable
    │   ├── Seat × 6 (positioned via polar math: cos(θ)/sin(θ))
    │   │   ├── SeatLabel (position + stack + status)
    │   │   ├── HoleCards (face-down or revealed per visibility policy)
    │   │   └── LastAction (floating text "raise 300")
    │   ├── CommunityCards (centered)
    │   └── PotDisplay (centered number)
    ├── ReasoningPanel (right side, fixed)
    │   ├── ActorHeader (current actor seat + position)
    │   └── IterationStream
    │       └── IterationItem × N (tool_call / tool_result / commit)
    └── ActionTimeline (bottom)
        └── TurnCard × N (highlight current + click to seek)
```

**~10 core components**. Each ~50-150 lines TSX. Total Phase 1
frontend: ~1500-2000 lines.

**Implementation choices**:
- Seat × 6 = independent `<Seat />` div components, parent `<PokerTable />`
  uses `position: absolute` with polar-computed `top`/`left`. Allows
  framer-motion to animate individual seats in Phase 2.
- ReasoningPanel iterations: all-expanded in Phase 1 (no collapse). 99% of
  turns have 1 iteration (commit-only) per current Claude organic
  utility-call rate (0/22 baseline). Add collapse only if real overflow
  becomes a problem (YAGNI).

## Data Flow

**Data sources** (per session):
```
runs/session_xxx/  (or  web/public/data/<id>/  for static build)
├── canonical_private.jsonl   ← 1 line/hand, complete hole cards (god-view)
├── public_replay.jsonl       ← 1 line/hand, public events (live experience)
├── agent_view_snapshots.jsonl ← N lines/turn, LLM iterations + reasoning
└── meta.json                  ← session-level (chip_pnl, retry_summary, etc.)
```

**Fetch strategy**:
- TanStack Query `useQuery(['session', id])` fetches all 4 files in
  parallel on session change
- A 6-hand session is ~50KB JSONL — full upload to in-memory typed object
- Cache key = session_id; switching hands/turns within a session does NOT
  re-fetch

**Derived state via selector pure functions**:
```ts
useCurrentTurn(session, handId, turnIdx) → {
  actor, street, pot, communityCards,
  holeCardsBySeat,  // visibility-filtered per mode
  lastAction, currentSeatStacks,
  reasoning,  // iterations[]
}
```

Selectors centralize:
- Visibility filtering (god-view / live / hero-only)
- Card revelation timing (preflop empty / flop 3 / turn 4 / river 5)
- Stack snapshots at given turn (pre-action vs post-action)

Components consume selector output as props; they don't decide what to show.

**URL state**:
- `?session=demo-1&hand=3&turn=5&mode=live`
- All controllable: refresh restores exact pointer; URL is shareable
- Phase 1 default `mode=live`; Phase 2 adds `mode=dev` toggle

**State machine**:
- Single useState pointer `(handId, turnIdx)`
- Operations: `next()` / `prev()` / `seek(turnIdx)` / `selectHand(handId)`
  pure functions returning new pointer
- React useState + useEffect syncs URL params

**Error handling (Phase 1)**:
- Fetch fail → "Session not found, check URL"
- JSONL parse fail → "Line N invalid: <raw text>"
- No retries, no fallbacks, no error toasts

## Testing

**Strategy**:

| Layer | Tool | Scope | Phase 1 count |
|---|---|---|---|
| Unit | Vitest | parsers + selectors (pure functions) | ~10-15 tests |
| Behavior | RTL + Vitest | 3-5 key components (Seat fold state, ReasoningPanel iterations, etc.) | ~5 tests |
| E2E | Playwright | 1 happy-path: load demo → see hand 3 → seek timeline → reasoning updates | 1 test |

**Coverage target**: parsers/selectors **>90%** (easy on pure functions);
components no enforced coverage.

**Snapshot tests intentionally omitted**: layout changes cascade snapshot
breaks → dev habit of `--update-snapshots` → snapshot loses defensive
value. RTL behavior tests target observable contracts (DOM text, aria
attributes), not full DOM tree.

**Tooling**:
- ESLint (typescript-eslint preset) + Prettier
- `tsc --noEmit` in CI
- `vite build` + `vite preview` + Playwright headless
- **No husky pre-commit** — single-developer project, CI catches lints
  before merge to main

**CI integration**:
- New `.github/workflows/web.yml`: lint → tsc → vitest → playwright
- Independent from Python CI (doesn't block Python merges)
- Phase 2 adds: build → push to gh-pages

**Test file organization**:
```
web/src/
├── parsers/parseJsonl.ts
├── parsers/parseJsonl.test.ts        ← unit
├── selectors/useCurrentTurn.ts
├── selectors/useCurrentTurn.test.ts  ← unit
├── components/Seat.tsx
├── components/Seat.test.tsx          ← behavior
└── ...
web/e2e/
└── replay-happy-path.spec.ts          ← Playwright
```

## Future Scope & Security Constraints

### Phase 3 (Spectator live mode) — DEFERRED

Spec §9 + §10 design: WebSocket-based live event stream. Backend Python
service runs Session, publishes public events to WebSocket subscribers.

**API key constraint**: Backend MUST hold the LLM API key — client never
sees it. Spectator mode itself doesn't expose API to clients (read-only),
but enables live sessions which DO consume API quota.

**Rate limit / cost cap requirements**:
1. Per-IP / per-session rate limit (e.g. 1 active spectated session per IP,
   max 1 hand/min)
2. Daily cost cap (`SessionConfig.max_total_tokens` from Phase 4) per
   active session
3. Auth gate: even simple invite-only token; portfolio link does NOT
   permit anonymous live sessions

### Phase 4 (Player mode — human plays vs LLM) — DEFERRED

Per spec §9.2: WebSocket `mode=player&seat=N` with auth token.
Same backend constraints as Phase 3 (server holds API key, rate limits,
cost caps), plus seat-N private channel for player's own hole cards.

**Demo strategy** (so portfolio still works without exposing live):
- Public portfolio link → static replay only (Phase 1+2 deliverable)
- "Live" / "Play vs LLM" buttons hidden behind invite token
- The user (project owner) can demo live during interviews via personal
  invite token

### Spec items intentionally NOT in any Web UI phase

- Multi-language i18n (defer indefinitely; English-first)
- A11y polish (best-effort aria labels, no formal WCAG audit)
- Cross-browser testing (Chrome + Safari validated; Firefox/Edge best-effort)
- Visual regression testing (Percy / Chromatic) — defer
- Production-grade observability (Sentry / etc.) — defer

## Out of Scope (Explicit)

This spec is **Web UI Phase 1 + 2** (replay-only static site). Out:
- Live spectator (Phase 3, separate spec required)
- Player mode (Phase 4, separate spec required)
- Backend service (no Python service runs for Phase 1+2)
- API key handling (no API calls from client)
- Authentication / authorization (Phase 3+ concern)
- Multi-tenant session storage (Phase 3+ concern)
- Mobile app (web-only)

## Success Criteria

Phase 1 MVP ship gate:
1. `cd web && npm install && npm run dev` opens browser with demo session
   loaded; can navigate hand 1-6, seek timeline, see reasoning panel
   update per turn
2. `npm run build` produces `dist/` deployable to GitHub Pages; visiting
   the deployed URL shows the same demo session
3. All Phase 1 tests pass: ~10 unit (parsers + selectors), ~5 behavior (key components), 1 Playwright e2e (~16 total)
4. Lighthouse score >85 on desktop (no a11y enforcement)

Phase 2 polish ship gate:
1. Auto-play animation works smoothly at 1x speed; chip slide animation
   doesn't drop frames
2. Dev mode toggle in URL flips god-view; raw JSON viewer renders for
   each turn
3. 3+ bundled demo sessions selectable from dropdown
4. GitHub Actions deploy workflow live; merging to main triggers
   gh-pages publish
