# Changelog

All notable user-facing changes are listed here. Dates are in YYYY-MM-DD.

## [Unreleased]

### 6-LLM showdown shipped (April 27, 2026)

Official 30-hand 6-LLM tournament now lives at
`web/public/data/demo-6llm/` and is the GitHub Pages landing demo.
Took three runs to drive censor count to zero (4 → 4 → 0):

- **Run 1** (commit `13b88bb` baseline): 4/30 censored. Investigation
  revealed two real protocol bugs (Kimi K2.5 reasoning_content stripping,
  GPT-5 invalid_prompt) plus one Gemini 503 capacity spike.
- **Run 2** (commits `ced6534` + `d4dac42`): the Kimi reasoning fix
  worked; GPT-5 still censored hand 2 because the user.j2 template had
  a hard-coded "explain your reasoning" instruction independent of the
  `rationale_required` flag.
- **Run 3** (commit `2cae85c`): user.j2 also respects `rationale_required`.
  30/30 clean, 51.6 min wall time, $0.71 total cost (cap was $2).

P&L (final stacks − 10,000 starting):

  🥇 kimi-k2.5         +20,150
  🥈 qwen3.6-plus       +6,300
  🥉 gemini-2.5-flash   +2,200
     deepseek-chat      +1,250
     gpt-5.4-mini      −12,800
  ❌ claude-haiku-4-5  −17,100

Pre-flight infrastructure that made this practical:

- `meta.censored_hand_ids`, `meta.estimated_cost_breakdown`,
  `meta.latency_per_seat_ms`, `meta.agent_config_per_seat`,
  `meta.session_config` for full reproducibility (commits `13b88bb`,
  `cca5457`)
- Per-hand progress line on stderr so a 50-min run isn't a black box
  (commit `2bf937f`)
- Provider registry centralization with per-model temperature locks
  (commit `13b88bb`)
- USD pricing table corrected to match April 2026 official rates
  (commit `cca5457`)
- Generator `--force` guards to prevent silent overwrites of finished
  tournaments (commit `13b88bb`)
- `bundle-demos.mjs` MARQUEE_ORDER puts the headline demo first
  automatically (commit `13b88bb`)
- Frontend action labels switched from raw enum (`raise_to 250`) to
  human-readable (`Raise to 250`) (commit `13b88bb`)

The Pages deploy now ships only `demo-6llm/`. Other generator scripts
(`generate-demo-tournament.py`, `generate-demo-bots.py`,
`generate-demo.py`) remain in the repo for local experimentation.

### Polish round 3 — 6-LLM compatibility (April 27, 2026)

Drove a 6-LLM tournament smoke (one provider per seat: Anthropic +
DeepSeek + OpenAI + Qwen + Kimi + Gemini) and fixed every protocol
incompatibility encountered along the way.

- **Kimi region routing**: the user's key is China-region. The default
  `api.moonshot.ai` (international) endpoint 401s on it; routing to
  `api.moonshot.cn/v1` works. Documented in USAGE.
- **Kimi forced temperature=1.0**: `kimi-k2.5` rejects any other
  temperature with 400 "invalid temperature: only 1 is allowed for
  this model". Tournament script now hardcodes 1.0 for the Kimi seat.
- **Kimi total_turn_timeout 60→120s**: Kimi is observably slower than
  the other providers (China-region latency + verbose internal
  reasoning); 60s default censored 2/6 hands in early smoke runs.
- **Kimi empty-content rejection on replay**: Kimi rejects any
  assistant message whose content is null or `""` (even when
  `tool_calls` is present, and even when Kimi itself produced the
  empty turn). The provider's `_normalize_assistant_content` now
  replaces empty content with a single space.
- **Gemini "Value is not a struct: null" rejection on replay**:
  Gemini's OpenAI-compat shim rejects assistant message dicts that
  include legacy OpenAI null fields (`function_call: null`,
  `audio: null`, `refusal: null`, `annotations: null`,
  `tool_calls: null`). The normalizer now strips these whenever the
  value is null.
- **Gemini `Unknown name "seed"` not detected as seed-unsupported**:
  The seed detector heuristic now matches Gemini's error format too
  (in addition to OpenAI / DeepSeek phrasings).
- **Demo session**: `web/public/data/demo-6llm-smoke/` ships a 6-hand
  smoke (one hand per button rotation) so visitors can see all six
  providers reasoning side-by-side. Full 30-hand `demo-6llm` will
  follow once approved.

### Polish round 2 (April 27, 2026)

- **More providers**: Kimi (Moonshot), Grok (xAI), Gemini (Google AI Studio
  via OpenAI-compatible shim) added to CLI + agent label/icon mappings.
  Total provider count: 7 (Anthropic, OpenAI, DeepSeek, Qwen, Kimi, Grok,
  Gemini).
- **DeepSeek thinking-mode roundtrip**: provider now preserves
  `reasoning_content` on multi-turn replays for the `deepseek` provider —
  unblocks `deepseek-v4-flash` direct usage before the legacy
  `deepseek-chat` alias deprecation 2026-07-24.
- **PnL chart switched to running-stack view**: Y axis now shows each
  player's bankroll over time (starting + cumulative PnL) instead of a
  centered-at-zero PnL delta. Smooth monotone curves replace linear lines.
  More intuitive for "who's winning" at a glance; small swings stay
  legible next to big spikes.
- **RuleBased agent records the rule that fired**: reasoning panel now
  shows e.g. "PREMIUM hand AA (UTG) → open-raise 300 (3× BB)" instead of
  an opaque "(no LLM reasoning)" placeholder. Backend's
  RuleBasedAgent.decide() emits a synthetic IterationRecord so the
  existing rendering path picks it up unchanged.
- **HUD persisted to meta.json + displayed**: per-seat VPIP / PFR / 3-bet /
  AF / WTSD aggregates now serialize into `meta.hud_per_seat`. Session
  Summary modal grows a per-seat HUD table and a per-hand outcomes
  table (winner + pot + community).
- **Bundle code-splitting**: React.lazy + Suspense around PnlChart,
  SessionSummary, DevPanel. Initial JS payload dropped 296 KB → 79 KB
  gzip (3× reduction in first-paint download).
- **Keyboard shortcuts modal**: clicking the toolbar's keyboard icon now
  opens a small popover listing all shortcuts (←/→ / ↑/↓ / Space). Esc
  + backdrop click + × close.
- **Updated provider docs**: USAGE.md per-provider notes refreshed for
  April 2026 model lineups (Grok 4.x, Gemini 3.x, Kimi K2.6, DeepSeek V4).

### Web UI Polish (April 27, 2026)

- Inter + JetBrains Mono fonts loaded from Google Fonts
- Tremor + Recharts as the chart engine; PnL chart redesigned with axes,
  gridlines, gradient fill, and hover tooltips
- @lobehub/icons brand SVGs added; each seat shows the actual provider logo
  (Anthropic, OpenAI, DeepSeek, Qwen) instead of a grey box
- god-view (all hole cards visible) is now the default replay mode; live
  spectator mode is opt-in via `?live=1`
- HandSelector toolbar redesigned with lucide-react icons and grouped
  controls; brand title "♠ LLM Poker Arena" in the header
- ReasoningPanel: provider header, structured iteration cards with code-block
  styling for tool calls, color-coded decision row (lucide icon + tone)
- ActionTimeline: turns grouped by street (PREFLOP / FLOP / TURN / RIVER),
  per-action color coding, provider color dots

### Multi-LLM Tournament Demo

- New `web/scripts/generate-demo-tournament.py` runs a 4-LLM × 30-hand
  tournament: Claude Haiku 4.5 + DeepSeek + GPT-5.4-mini + Qwen 3.6-plus
  + 2 RuleBased agents
- 30-hand bundled session at `web/public/data/demo-tournament/`
- Provider compatibility fix: `_max_tokens_kwarg` routes gpt-5.x and
  o-series to `max_completion_tokens`; older OpenAI / DeepSeek / Qwen
  keep `max_tokens`

### Web UI Phase 2 (April 26, 2026)

- Per-session chip-stack PnL chart (`PnlChart`)
- Auto-play mode + playback speed selector (0.5× / 1× / 2× / 4×)
- Keyboard navigation (←/→ turn, ↑/↓ hand, space play/pause)
- Multi-session selector + `bundle-demos.mjs` auto-discovery
- Custom-session file picker in dev mode (load any local `runs/<id>/`)
- Dev mode toggle (`?dev=1`): raw JSON viewer + retry / api_error /
  reasoning_artifact.kind badges
- Session summary modal (per-seat PnL / tokens / utility calls / retry)
- Mobile-responsive layout (best-effort)
- GitHub Actions deploy workflow → GitHub Pages
- CSS-rendered playing cards (no external card-image dep)
- Winner banner + community-card placeholders
- Active-seat ring with subtle pulse animation

### Web UI Phase 1 (April 26, 2026)

- React 19 + Vite 8 + TypeScript 6 + Tailwind v3 stack
- Replay viewer: oval poker table with polar-arranged seats, community
  cards, pot display, action highlighting
- Reasoning panel showing every LLM iteration verbatim (text + tool
  calls + tool results)
- Action timeline (one card per turn, click to seek)
- Hand selector (prev / next / dropdown)
- URL state: `?session=&hand=&turn=&dev=&live=`
- 4 JSONL parsers + canonical-private / public-replay / agent-snapshot
  data flow
- Hardcoded `demo-1` session bundled (1 Claude Haiku + 5 RuleBased,
  6 hands, $0.05)

### Backend Phase 4 (April 26, 2026)

- Session-level `max_total_tokens` cost cap with clean abort at hand
  boundary
- USAGE.md initial publication
- CLI: `--llm-seat / --llm-provider / --llm-model` flags

### Backend Phase 3 (April 24-26, 2026)

- LLMAgent with bounded ReAct loop (K+1 utility calls + 1 commit)
- 4 retry budgets per spec §4.1 BR2-05: api_retry,
  illegal_action_retry, no_tool_retry, tool_usage_error
- Three providers: Anthropic (`AnthropicProvider`), OpenAI / DeepSeek /
  Qwen (`OpenAICompatibleProvider`)
- Math tools: `pot_odds`, `spr`, `hand_equity_vs_ranges`
- HUD tool: `get_opponent_stats` with VPIP / PFR / 3-bet / AF / WTSD
  counters (single-session in-memory)
- Prompt-retry-censor-redact pipeline: secrets redacted, hands censored
  on permanent provider error
- Reasoning artifacts captured per provider (raw / summary /
  thinking_block / encrypted / redacted)

### Backend Phase 2 (April 24, 2026)

- `cli/play.py` entry point + HumanCLIAgent
- Multi-hand session loop with button rotation
- 3-layer JSONL artifacts: canonical_private, public_replay,
  agent_view_snapshots, plus meta.json

### Backend Phase 1 (April 23, 2026)

- 6-max No-Limit Texas Hold'em engine wrapping PokerKit 0.7.3
- Frozen Pydantic DTOs for engine ↔ agent boundary
- RandomAgent + RuleBasedAgent baselines
- Test suite scaffolding
