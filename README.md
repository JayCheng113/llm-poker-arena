# ♠ LLM Poker Arena

A multi-agent platform where modern LLMs compete head-to-head at 6-max No-Limit Texas Hold'em — and you can watch every hand they play, with full reasoning traces, in your browser.

**[▶ Live demo](https://jaycheng113.github.io/llm-poker-arena/?session=demo-tournament)** · 4 LLMs (Claude · DeepSeek · GPT · Qwen) · 30-hand tournament · open every decision

![hero](docs/images/hero.png)

---

## What it does

- **Backend (Python).** A reproducible 6-max NLHE engine wraps PokerKit. Plug in any LLM as a player; the agent runs a bounded ReAct loop (think → tool → observe → commit) using a portable tool spec, with separate retry budgets for API errors / illegal actions / missing tool calls / tool misuse. Three providers ship out of the box (Anthropic, OpenAI / Chat Completions–compatible, DeepSeek-style), all four major LLM families validated end-to-end (Claude · GPT-5 · DeepSeek · Qwen).

- **Replay viewer (React).** A static web UI that fetches the JSONL artifacts a session emits and renders a poker table where every seat shows the actual provider logo, every reasoning step shows the LLM's prose + tool calls + tool results, and every decision is color-coded. Per-seat cumulative PnL chart, hand-by-hand timeline grouped by street, dev mode for raw debugging — all client-side, deployable to GitHub Pages with no backend.

The framework is designed for two end users: an engineer who wants to benchmark how well current LLMs play poker (open-ended, observable, reproducible), and a portfolio visitor who wants to see what a "research-grade" multi-agent LLM project looks like in practice.

## Why?

Existing poker AI work (Pluribus, ReBeL) uses purpose-built solvers. This project asks a different question: **how well do general-purpose LLMs play when given the same tools a human pro would use** (pot odds, equity, opponent stats), and how does that competence vary across providers?

The replay viewer is the answer's UI: it lets you open any decision and read the model's actual reasoning side-by-side with the table state, instead of treating the LLM as a black box.

## Live demos

| Session | Lineup | Hands | Cost |
|---|---|---|---|
| **[demo-tournament](https://jaycheng113.github.io/llm-poker-arena/?session=demo-tournament)** | Claude Haiku 4.5 + DeepSeek + GPT-5.4-mini + Qwen 3.6-plus + 2 RuleBased | 30 | $0.55 |
| [demo-1](https://jaycheng113.github.io/llm-poker-arena/?session=demo-1) | Claude Haiku 4.5 + 5 RuleBased | 6 | $0.05 |
| [demo-bots](https://jaycheng113.github.io/llm-poker-arena/?session=demo-bots) | 6 RuleBased | 60 | $0 |

URL parameters are stable: append `&hand=<n>&turn=<n>` to deep-link, `&dev=1` for raw JSON + retry/error badges, `&live=1` for the spectator's-camera view (cards face-down until showdown).

## Features

### Backend
- **6-max NLHE engine** built on PokerKit 0.7.3 — single canonical state + frozen Pydantic DTOs across the engine ↔ agent trust boundary
- **Bounded ReAct loop** per agent turn: K configurable utility-tool calls (`pot_odds`, `spr`, `hand_equity_vs_ranges`, `get_opponent_stats`) followed by a forced commit; 4 independent retry budgets
- **Multi-provider**: Anthropic (`AnthropicProvider`) and OpenAI Chat Completions–compatible (`OpenAICompatibleProvider`, used for OpenAI / DeepSeek / Qwen / any compatible endpoint)
- **Reasoning artifacts** captured per provider (raw text / summary / thinking_block / encrypted / redacted / unavailable) so post-hoc analysis can distinguish what the model actually emitted
- **Cost guard**: `SessionConfig.max_total_tokens` aborts cleanly at the next hand boundary
- **3-layer JSONL output**: canonical-private (engine truth, all hole cards), public-replay (UI-safe events), agent-view-snapshots (per-turn LLM iterations)
- **460+ unit / integration tests**, gated real-API tests for every provider

### Web UI
- **Provider-aware seats**: every seat shows the actual brand logo (Anthropic / OpenAI / DeepSeek / Qwen) and trimmed model name
- **Per-seat reasoning panel**: provider header → step-numbered iteration cards → tool-call code blocks → color-coded decision row
- **Cumulative PnL chart** (Tremor LineChart) with per-seat line, hover tooltip, signed legend
- **Action timeline** grouped by street (PREFLOP / FLOP / TURN / RIVER), action-type color coding (fold faded, call indigo, raise emerald)
- **god-view default**: every hole card visible — replay is for understanding, not guessing. Toggle to live spectator mode if you want to read the board yourself.
- **Multi-session selector** + custom-session file picker (dev mode)
- **Auto-play** with 0.5× / 1× / 2× / 4× speed
- **Mobile-responsive** (best-effort)
- Deployed to **GitHub Pages** as a fully static site — no backend needed for replay

## Screenshots

| | |
|---|---|
| ![Showdown](docs/images/showdown.png) | ![Session summary](docs/images/summary.png) |
| Showdown view with PnL chart and street-grouped action timeline | Per-seat session summary modal: PnL, tokens, retry status, utility-tool calls |

![Dev mode](docs/images/dev-mode.png)
*Dev mode (`?dev=1`): raw `agent_view_snapshot` JSON in the right panel for debugging.*

## Architecture

```
┌─ engine ─────────────────────────────────┐    ┌─ agents ──────────────────────────┐
│ PokerKit canonical state                 │    │ RuleBasedAgent                    │
│ ↓                                        │    │ HumanCLIAgent                     │
│ PlayerView / PublicView projections      │ ←→ │ LLMAgent                          │
│  (frozen Pydantic, trust-boundary DTOs)  │    │  ├ AnthropicProvider              │
│ ↓                                        │    │  └ OpenAICompatibleProvider       │
│ Session orchestrator                     │    │     (OpenAI / DeepSeek / Qwen)    │
└───┬──────────────────────────────────────┘    └───────────────────────────────────┘
    │ writes 3-layer JSONL
    ▼
┌─ runs/<session_id>/ ─────────────────────────────────────────────────────────────┐
│ canonical_private.jsonl  · public_replay.jsonl  · agent_view_snapshots.jsonl     │
│ censored_hands.jsonl     · meta.json            · config.json                    │
└──────────────────────────────────────────────────────────────────────────────────┘
    │ bundle-demos.mjs scans web/public/data/<id>/ → manifest.json
    ▼
┌─ web/ (static site → GitHub Pages) ──────────────────────────────────────────────┐
│ React 19 + Vite 8 + TypeScript 6 + Tailwind v3 + Tremor + @lobehub/icons         │
│ Fetches JSONL → parses → renders PokerTable / ReasoningPanel / PnlChart / etc.   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## Quick start

### CLI — play against an LLM

```bash
# install
git clone https://github.com/JayCheng113/llm-poker-arena.git
cd llm-poker-arena
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# set keys for whichever provider(s) you want
export ANTHROPIC_API_KEY=sk-ant-...
# (optional) export DEEPSEEK_API_KEY=sk-... ; export OPENAI_API_KEY=sk-...

# you sit at seat 3, Claude Haiku 4.5 plays seat 0, bots fill 1/2/4/5
poker-play \
  --llm-seat 0 --llm-provider anthropic --llm-model claude-haiku-4-5
```

### Generate the multi-LLM tournament demo locally

```bash
# requires all 4 keys: ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY, QWEN_API_KEY
.venv/bin/python web/scripts/generate-demo-tournament.py --hands 30
```

Output is bundled into `web/public/data/demo-tournament/` and auto-discovered by the manifest builder.

### Web UI — run locally

```bash
cd web
npm install --legacy-peer-deps
npm run dev          # http://localhost:5173
```

For more on session-config knobs, agent types, the cost guard, and the JSONL schema, see [USAGE.md](USAGE.md).

## Tech stack

- **Backend**: Python 3.12 · PokerKit 0.7.3 · Pydantic 2 · `pytest` · `mypy` · `ruff`
- **Providers**: `anthropic` · `openai` (used for OpenAI + DeepSeek + Qwen via base_url override)
- **Web**: React 19 · Vite 8 · TypeScript 6 · Tailwind CSS v3 · [Tremor](https://www.tremor.so/) · [@lobehub/icons](https://github.com/lobehub/lobe-icons) · `lucide-react`
- **Test**: Vitest · `@testing-library/react` · Playwright
- **Deploy**: GitHub Actions → GitHub Pages

## Roadmap

What's done is in [CHANGELOG.md](CHANGELOG.md). What isn't:

- **Live spectator mode** — current replay is post-hoc; a real backend service streaming session state over WebSocket would let visitors watch a live tournament in progress
- **Web-based human vs. LLM** — currently CLI-only; a hosted variant needs auth + BYOK key handling so visitors don't burn the host's API budget
- **DeepSeek thinking-mode roundtrip** — the legacy `deepseek-chat` alias works today; before its 2026-07-24 deprecation we need to handle `reasoning_content` in the multi-turn protocol so `deepseek-v4-flash` can be used directly
- **Persist HUD counters to meta.json** — currently in-memory only, so the web UI can't show per-seat VPIP / PFR / 3-bet / AF / WTSD aggregates
- **Cross-hand stats table** in the session summary modal
- **Animations** — chip slide actor → pot, card flip on reveal (would add framer-motion)

## License

[MIT](LICENSE) © 2026 Jay Cheng
