# Usage Guide

A multi-agent platform for No-Limit Texas Hold'em 6-max. Mix human players,
rule-based bots, and LLM agents (Anthropic / OpenAI / DeepSeek / Qwen / any
OpenAI-compatible endpoint) in the same session; replay any hand from the
3-layer JSONL artifacts in your browser.

For the project pitch, screenshots, and live demos, see [README.md](README.md).
This file is the operational reference.

---

## Quick start (CLI)

```bash
pip install -e '.[dev]'
poker-play
```

Plays 6 hands with `HumanCLIAgent` at seat 3 and `RuleBasedAgent` bots
elsewhere. Logs land in `runs/session_<timestamp>_seed42/`.

### Add an LLM opponent

```bash
export ANTHROPIC_API_KEY=sk-ant-...
poker-play \
  --llm-seat 0 --llm-provider anthropic --llm-model claude-haiku-4-5
```

You're at seat 3, Claude Haiku 4.5 plays seat 0, bots fill 1/2/4/5.

### Two LLMs (you spectate)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export DEEPSEEK_API_KEY=sk-...
poker-play \
  --llm-seat 0 --llm-provider anthropic           --llm-model claude-haiku-4-5 \
  --llm-seat 4 --llm-provider openai-compatible   --llm-model deepseek-chat \
                                                 --llm-base-url https://api.deepseek.com/v1
```

### 4-LLM tournament demo

The script bundled with the web UI runs the full lineup that powers the
[live demo](https://jaycheng113.github.io/llm-poker-arena/?session=demo-tournament):

```bash
# all four keys required
export ANTHROPIC_API_KEY=sk-ant-...
export DEEPSEEK_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
export QWEN_API_KEY=sk-...

.venv/bin/python web/scripts/generate-demo-tournament.py --hands 30
# → runs/demo-tournament/ + web/public/data/demo-tournament/
```

Cost: ~$0.55 for 30 hands at the prices in effect April 2026 (Haiku $0.24 +
DeepSeek $0.06 + GPT-5.4-mini $0.13 + Qwen 3.6-plus $0.12).

## Agent types

| Type | Status | Tools | Notes |
|------|--------|-------|-------|
| `RandomAgent` | shipped | none | Uniform over legal actions |
| `RuleBasedAgent` | shipped | none | TAG baseline (preflop pair-strength + position) |
| `HumanCLIAgent` | shipped | none | Reads stdin (one human per session) |
| `LLMAgent` + Anthropic | shipped | math + equity + HUD | Claude Haiku 4.5 / Opus 4.7 / Sonnet 4.6 |
| `LLMAgent` + OpenAI | shipped | math + equity + HUD | GPT-4o, gpt-5.4-mini (auto-routes `max_completion_tokens` for gpt-5.x / o-series) |
| `LLMAgent` + DeepSeek | shipped | math + equity + HUD | deepseek-chat / deepseek-reasoner (legacy) — see DeepSeek notes |
| `LLMAgent` + Qwen | shipped | math + equity + HUD | qwen3.6-plus / qwen3.5-flash via DashScope OpenAI-compatible endpoint |

## Cost guard

Set `SessionConfig.max_total_tokens` to abort cleanly when cumulative
tokens (input+output across all seats) exceed the cap:

```python
cfg = SessionConfig(..., max_total_tokens=500_000)
```

500K tokens ≈ $3 at Claude Haiku 4.5 rates. Abort happens at the next hand
boundary so all artifacts stay consistent. `meta.json.stop_reason` records
`"max_total_tokens_exceeded"`.

CLI flag for this is not yet exposed — set programmatically via
`SessionConfig` in a Python script (see `web/scripts/generate-demo-tournament.py`
for an end-to-end example).

## Log file structure

Each session writes to `runs/<session_id>/`:

| File | Contents |
|---|---|
| `config.json` | Frozen `SessionConfig` snapshot (reproducibility) |
| `canonical_private.jsonl` | Engine truth, one line per hand (all hole cards) |
| `public_replay.jsonl` | UI-safe events, one line per hand |
| `agent_view_snapshots.jsonl` | Per-turn per-seat views + LLM iterations |
| `censored_hands.jsonl` | Hands aborted by permanent provider error (BR2-01) |
| `meta.json` | Session-level summary (chip P&L, retry / token aggregates, provider capabilities, stop reason) |

For analysis with DuckDB:

```python
from llm_poker_arena.storage.duckdb_query import open_session
con = open_session("runs/demo-tournament", access_token=...)
con.execute("SELECT seat, COUNT(*) FROM actions GROUP BY seat").fetchall()
```

## Web UI

The replay viewer in `web/` is a React + Vite static site. It fetches the
JSONL artifacts from `web/public/data/<session_id>/` and renders the table,
reasoning panel, PnL chart, and timeline.

```bash
cd web
npm install --legacy-peer-deps
npm run dev          # local dev → http://localhost:5173
npm test             # vitest unit/component tests
npm run test:e2e     # playwright (chromium)
npm run build        # static build → dist/
```

### URL parameters

| Param | Values | Default | Effect |
|---|---|---|---|
| `session` | session id (must exist in `manifest.json`) | first manifest entry | Which session to display |
| `hand` | integer | 0 | Which hand to view |
| `turn` | integer | 0 | Which turn within the hand (clamped to last available) |
| `live` | `1` | absent | Live spectator mode: cards face-down until showdown. Default behavior is god-view (all cards visible). |
| `dev` | `1` | absent | Dev mode: raw JSON viewer + retry/error/artifact badges in the reasoning panel |

### Adding a new session to the bundled site

```bash
# 1. produce the session (any way you like — CLI, script, etc.)
.venv/bin/python web/scripts/generate-demo-bots.py     # 60-hand all-bot baseline

# 2. copy the runs/<id>/ directory into web/public/data/
cp -r runs/demo-bots web/public/data/

# 3. regenerate the manifest
node web/scripts/bundle-demos.mjs                      # writes web/public/data/manifest.json

# 4. dev / build
cd web && npm run dev
```

### GitHub Pages deploy

`.github/workflows/deploy-web.yml` builds `web/` with
`VITE_BASE=/llm-poker-arena/` and pushes `dist/` to GitHub Pages on every
push to `main`. Repo owner must enable Pages once: Settings → Pages →
Source = "GitHub Actions".

## Configuration knobs (SessionConfig)

| Field | Notes |
|---|---|
| `num_players` | Currently fixed at 6 (engine assumption) |
| `num_hands` | Must be a multiple of `num_players` (balanced button rotation) |
| `enable_math_tools` | Exposes `pot_odds` + `spr` + `hand_equity_vs_ranges` to LLMs |
| `enable_hud_tool` | Exposes `get_opponent_stats` (in-memory VPIP/PFR/3-bet/AF/WTSD) |
| `rationale_required` | Strict mode: empty text + tool call triggers retry |
| `opponent_stats_min_samples` | Minimum samples before HUD numbers are returned |
| `max_utility_calls` | Per-turn LLM tool-call budget (default 5) |
| `max_total_tokens` | Session-level cost cap (None = no cap) |
| `rng_seed` | Deterministic shuffles for reproducible sessions |

## Provider notes

### Anthropic
Standard `claude-*` model IDs. No special handling needed.

### OpenAI
`gpt-5.x` and `o1`/`o3` families require `max_completion_tokens` instead of
`max_tokens`. The provider auto-routes by model-name prefix; older `gpt-4*`
keep `max_tokens`. Reasoning models (o-series) emit `reasoning_content`
which is captured into `reasoning_artifacts`.

### DeepSeek
Use base_url `https://api.deepseek.com/v1`. The legacy aliases `deepseek-chat`
(non-thinking-mode) and `deepseek-reasoner` (thinking-mode) work today but
**will be deprecated 2026-07-24** in favor of `deepseek-v4-flash` /
`deepseek-v4-pro`. The current provider implementation does not yet round-trip
`reasoning_content` between turns, so calling `deepseek-v4-flash` directly
can intermittently 400 with "the `reasoning_content` in the thinking mode
must be passed back to the API." Workaround: stay on `deepseek-chat` until
the multi-turn handler ships.

### Qwen
Use base_url `https://dashscope.aliyuncs.com/compatible-mode/v1` (Alibaba
Cloud DashScope OpenAI-compatible endpoint). All model IDs are `qwen3.*-*`
(e.g. `qwen3.6-plus`, `qwen3.5-flash`).

## Troubleshooting

**`poker-play` exits with `session directory ... already exists`** —
session dirs include microseconds. Re-run; should auto-resolve.

**`API key not set` error** — confirm the env var name matches the provider:
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `QWEN_API_KEY`.

**Real LLM session takes minutes** — that's normal. Each turn = 1 API call
(~1-3s for Haiku, longer for Opus / Reasoner / Qwen-plus).

**Hand censored** — check `runs/<session>/censored_hands.jsonl`. Most common
cause is a permanent provider 4xx mid-hand (e.g. invalid tool spec,
unsupported parameter). Fix the upstream issue and re-run with the same
seed for byte-identical replay.

**`assertion failed: chip_pnl` in tests** — usually means the engine audit
failed mid-hand; check the test's `tmp_path` for `.jsonl` artifacts and
inspect `state` errors.

## Testing

```bash
# Backend
.venv/bin/pytest                        # 460+ unit + integration tests

# Web
cd web
npm test                                # vitest (component + selector + parser)
npm run lint                            # eslint
npm run type-check                      # tsc --noEmit
npm run test:e2e                        # playwright (chromium)
```

Real-API integration tests are gated behind `<PROVIDER>_INTEGRATION_TEST=1`
env vars and require the corresponding API key — they're skipped by default
to keep CI free.

## Architecture overview (one-paragraph)

The engine wraps PokerKit as a single canonical state. PlayerView /
PublicView projections cross the engine ↔ agent trust boundary as frozen
Pydantic DTOs. Agents (sync `decide` for Random/RuleBased/HumanCLI, async
for LLM) return `TurnDecisionResult`; `Session` orchestrates the multi-hand
loop and persists 3-layer JSONL artifacts. `LLMAgent` runs a bounded ReAct
loop (K+1 = `max_utility_calls` utility tool calls + 1 forced action commit)
with 4 independent retry counters per spec §4.1 BR2-05. The web UI is a
zero-backend static site that consumes the same artifacts.
