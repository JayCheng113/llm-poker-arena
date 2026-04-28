# Usage Guide

A multi-agent platform for No-Limit Texas Hold'em 6-max. Mix human players,
rule-based bots, and LLM agents (Anthropic / OpenAI / DeepSeek / Qwen /
Kimi / Gemini / Grok / any OpenAI-compatible endpoint) in the same
session; replay any hand from the 3-layer JSONL artifacts in your browser.

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

### 6-LLM showdown demo (the one shipped on Pages)

The headline tournament — every seat is a different provider:

```bash
# all six keys required
export ANTHROPIC_API_KEY=sk-ant-...
export DEEPSEEK_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
export QWEN_API_KEY=sk-...
export KIMI_API_KEY=sk-...
export GEMINI_API_KEY=AIza...

.venv/bin/python web/scripts/generate-demo-6llm.py --hands 30
# → runs/demo-6llm/ + web/public/data/demo-6llm/ + manifest auto-rebuilt
```

Default lineup (`--lineup mini`, also the default):
Claude Haiku 4.5 / deepseek-chat / gpt-5.4-mini / qwen3.6-plus /
kimi-k2.5 / gemini-2.5-flash. The shipped 30-hand reference run cost
**$0.83** and took **54 min** wall time with **30/30 clean hands** (no
censors) and a visible reasoning artifact on every LLM seat.

Flagship lineup (`--lineup flagship`):

```bash
.venv/bin/python web/scripts/generate-demo-6llm.py \
    --lineup flagship --hands 102 \
    --out demo-6llm-flagship --max-tokens-cap 8000000
```

Same five mini-tier seats, but Anthropic's seat upgrades to
`claude-sonnet-4-6`. Single-variable change so any P&L delta is
attributable to the upgrade. The shipped 102-hand reference run cost
**$3.85** and took **3h 4min** with 102/102 clean. Sonnet went from
last (Haiku, −13,750 in 30 hands) to first (+9,908 in 102 hands), so
the larger sample also surfaces what the 30-hand baseline mostly
buried in noise.

Token cap defaults to 2M (~$0.83 mini); pass `--max-tokens-cap 8000000`
for the 102-hand flagship's ~$5 spend. Per-hand progress prints to stderr
so the run isn't a black box.

The generator refuses to overwrite an existing run unless you pass
`--force` — useful when iterating on a test, dangerous for finished
tournaments. Use `--hands 6` for a one-rotation smoke check.

### Other demo scripts (local only)

Three smaller generators ship for offline experimentation but are not bundled
into the Pages deploy:

- `web/scripts/generate-demo-tournament.py` — 4-LLM mixed lineup (2 RuleBased
  + Claude/DeepSeek/GPT-mini/Qwen), 30 hands, ~$0.55
- `web/scripts/generate-demo-bots.py` — 6 RuleBased agents, no API cost
- `web/scripts/generate-demo.py` — single Claude Haiku seat among 5 bots, ~$0.05

All three accept `--force` and auto-rebuild the manifest the same way.

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
`SessionConfig` in a Python script (see `web/scripts/generate-demo-6llm.py`
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
con = open_session("runs/demo-6llm", access_token=...)
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

All `web/scripts/generate-demo-*.py` generators handle the three steps
(run → copy to `web/public/data/` → rebuild manifest) automatically:

```bash
.venv/bin/python web/scripts/generate-demo-6llm.py --hands 30
cd web && npm run dev
```

For a session you produced by hand (e.g. via `poker-play`):

```bash
cp -r runs/<your-id> web/public/data/
node web/scripts/bundle-demos.mjs                      # writes web/public/data/manifest.json
```

The manifest sorts by a curated marquee order (`demo-6llm` floats to
the top, others fall to alphabetical) — adjust `MARQUEE_ORDER` in
`bundle-demos.mjs` if you want a different default landing demo. The
shipped Pages deploy contains only `demo-6llm`; other ids are
local-experiment scaffolding.

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
`gpt-5.x` and `o1`/`o3`/`o4` families are reasoning models — the provider
auto-routes them through the **Responses API** (`client.responses.create`)
to get user-visible reasoning summaries. Other OpenAI models stay on Chat
Completions. The Responses-path adapter translates Chat-format history
(role+content+tool_calls) into Responses input items
(developer/user/assistant + function_call + function_call_output) on each
turn, so the LLMAgent doesn't have to know which path is in use.

Reasoning summaries surface as `kind=SUMMARY` artifacts. OpenAI compresses
the chain-of-thought before returning it (low effort = sometimes empty;
high effort = paragraph-form). Token billing includes reasoning tokens.

Older OpenAI models still use `max_tokens` for output budget; the
provider routes by model-name prefix.

### DeepSeek
Use base_url `https://api.deepseek.com/v1`. Current model IDs:
`deepseek-v4-flash` (non-thinking + thinking-mode capable) and
`deepseek-v4-pro` (premium). The legacy aliases `deepseek-chat` /
`deepseek-reasoner` are deprecated 2026-07-24.

DeepSeek thinking-mode roundtrips `reasoning_content` on multi-turn
calls. The provider preserves this field for replay; the whitelist
also covers Kimi for the same reason. Other OpenAI-compatible providers
strip it (it's informational only and a few endpoints reject it on
replay round trips).

### Qwen
Use base_url `https://dashscope.aliyuncs.com/compatible-mode/v1` (Alibaba
Cloud DashScope OpenAI-compatible endpoint). Current model IDs are
`qwen3.*-*` (e.g. `qwen3.6-plus`, `qwen3.5-flash`).

### Kimi (Moonshot AI)
Two endpoints — pick by your account region:
- **International** (`api.moonshot.ai/v1`) — for keys provisioned via
  the `.ai` console
- **China** (`api.moonshot.cn/v1`) — for keys from the `.cn` console.
  Wrong endpoint → 401 "Invalid Authentication" even on a valid key.

The shipped `registry.py` defaults to `.cn` (matches the most common
key in this codebase). Edit `PROVIDERS["kimi"].base_url` locally if
your key is `.ai`.

Current models: `kimi-k2.6` (256K context flagship), `kimi-k2.5`
(stable), `kimi-k2-thinking` (reasoning variant). Legacy `kimi-k2`
deprecates 2026-05-25.

Quirks observed in production:
- `kimi-k2.5` enforces `temperature=1.0`. Any other value → 400
  "invalid temperature: only 1 is allowed for this model".
- Latency is noticeably higher than other providers (China-region +
  verbose internal reasoning). Bump `total_turn_timeout_sec` to ≥120s
  for stability.
- Kimi K2.5 emits `reasoning_content` (raw chain-of-thought) and
  REQUIRES the field to be round-tripped on multi-turn calls — the
  provider's reasoning_content whitelist covers Kimi for this reason.
  Without it: 400 "thinking is enabled but reasoning_content is
  missing in assistant tool call message at index N".
- Empty-content assistant messages (which Kimi itself sometimes emits
  on a no-tool-call turn) get rejected on multi-turn replay with
  "message at position N with role 'assistant' must not be empty" —
  the `_normalize_assistant_content` helper in `OpenAICompatibleProvider`
  handles this transparently for all OpenAI-compat providers.

### Grok (xAI)
Use base_url `https://api.x.ai/v1`. Current models (April 2026):
- `grok-4.3` — flagship (Beta), supports video input + slides generation
- `grok-4.20-beta-2` — public flagship, multi-agent architecture
- `grok-4.1-fast` — non-reasoning, latency-sensitive (cheapest)

Grok 5 is in training (Q2 2026 expected).

### Gemini (Google AI Studio)
Use base_url `https://generativelanguage.googleapis.com/v1beta/openai/`
(trailing slash matters — without it the request can hit
`/openai/chat/completions` or `/openai/v1/chat/completions` depending
on the SDK and Google's edge has historically been strict). The
OpenAI-compat shim removes the need for the `google-genai` SDK.

Production-tested models on AI Studio (April 2026):
- `gemini-2.5-pro` — flagship, paid tier
- `gemini-2.5-flash` — Flash tier (recommended)
- `gemini-2.0-flash` / `gemini-2.0-flash-lite` — deprecated 2026-06-01

The `gemini-3.x` family that public docs reference is on Vertex AI,
not AI Studio's OpenAI-compat endpoint — use `gemini-2.5-*` here.

Quirks:
- The shim rejects unknown OpenAI parameters (`seed` etc.) as
  "Unknown name `seed`: Cannot find field". Our seed-unsupported
  detector matches this format and falls back to a no-seed retry.
- The shim also rejects assistant messages whose null OpenAI legacy
  fields (`function_call: null`, `audio: null`, etc.) reach it with
  "Value is not a struct: null" — `_normalize_assistant_content`
  strips them before send.
- Free / paid tiers can both hit transient 503 "high demand". Paid
  tier hits it less frequently but doesn't eliminate it. The shipped
  `registry.py` bumps `sdk_max_retries=5` for Gemini so AsyncOpenAI's
  exponential backoff covers ~30-60s of spike.

**Thinking summaries**: Gemini's OpenAI-compat shim accepts
`extra_body.google.thinking_config.include_thoughts=True` and inlines
a `<thought>...</thought>` block at the start of `content`. The provider
extracts that block as a `kind=SUMMARY` reasoning artifact and strips
the tag from visible content. Wire-format quirk: AsyncOpenAI's
`extra_body=` kwarg spreads its dict to the request body's top level,
so the provider double-wraps as `extra_body={"extra_body": {...}}` to
get a literal `extra_body` key in the wire JSON (Gemini's compat
endpoint requires it that way; verified 2026-04-27).

## Troubleshooting

**`poker-play` exits with `session directory ... already exists`** —
session dirs include microseconds. Re-run; should auto-resolve.

**`API key not set` error** — confirm the env var name matches the provider:
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `QWEN_API_KEY` /
`KIMI_API_KEY` / `GEMINI_API_KEY` / `GROK_API_KEY`. The canonical mapping
lives in `src/llm_poker_arena/agents/llm/providers/registry.py`.

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
