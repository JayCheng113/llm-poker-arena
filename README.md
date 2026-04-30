# ♠ LLM Poker Arena

[![python ci](https://github.com/JayCheng113/llm-poker-arena/actions/workflows/python.yml/badge.svg)](https://github.com/JayCheng113/llm-poker-arena/actions/workflows/python.yml)
[![web ci](https://github.com/JayCheng113/llm-poker-arena/actions/workflows/web.yml/badge.svg)](https://github.com/JayCheng113/llm-poker-arena/actions/workflows/web.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python ≥3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](pyproject.toml)

Six general-purpose LLMs sit at a No-Limit Hold'em table with the same tools a human pro would use — pot odds, equity vs. range, opponent stats — and play it out for chips. Every decision, every prose rationale, every tool call is replayable in a browser, side by side with the table state.

> **Same field, same seed, swap one model: Anthropic's seat went from dead last
> (Haiku, −13,750 chips / 30 hands) to first (Sonnet, +9,908 chips / 102 hands)
> against the same five opponents.** A +24k chip swing from a single model
> upgrade — and the kind of cross-provider comparison no public benchmark
> measures.

**[▶ Baseline 30-hand](https://jaycheng113.github.io/llm-poker-arena/?session=demo-6llm)** · **[Flagship 102-hand](https://jaycheng113.github.io/llm-poker-arena/?session=demo-6llm-flagship)** · **[All-flagship 30-hand](https://jaycheng113.github.io/llm-poker-arena/?session=pilot-flagship-30h)** · 6 LLMs, one per seat, every reasoning step open

![hero](docs/images/hero.png)

## What you get

- ✅ **6 LLM providers** wired one per seat — Anthropic native SDK + OpenAI / DeepSeek / Qwen / Kimi / Gemini through one OpenAI-compatible adapter (Grok 7th, optional)
- ✅ **Bounded ReAct loop** with 4 independent retry budgets (api / illegal action / missing tool call / tool misuse) per spec §4.1 BR2-05
- ✅ **Every reasoning surface unified** — Chat Completions, OpenAI Responses API, Anthropic prose, DeepSeek/Kimi `reasoning_content`, Gemini `<thought>` blocks → one `REASONING` panel
- ✅ **Reproducible from one CLI** — `--lineup flagship --hands 102` runs the headline tournament from scratch for ~$4 (cost cap enforced)
- ✅ **Zero-backend React replayer** — deep-link URL state (`?session=&hand=&turn=`), code-split bundle, **79 KB gzip** first paint
- ✅ **502 backend + 115 web tests** — unit / integration / property / differential, with real-API integrations gated by env vars

## Quick start

```bash
git clone https://github.com/JayCheng113/llm-poker-arena.git
cd llm-poker-arena
uv sync --extra dev                    # or: python -m venv .venv && pip install -e '.[dev]'
```

Play yourself against an LLM:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run poker-play --llm-seat 0 --llm-provider anthropic --llm-model claude-haiku-4-5
```

Reproduce the headline tournament (needs all 6 provider keys — see [`.env.example`](.env.example)):
```bash
# Single-flagship: Anthropic→Sonnet, rest mini-tier (102 hands, ~$4)
uv run python web/scripts/generate-demo-6llm.py \
    --lineup flagship --hands 102 --out demo-6llm-flagship --max-tokens-cap 8000000

# All-flagship: every seat upgraded (Opus 4.7, GPT-5.5, V4-Pro, Qwen Max,
# K2.6, Gemini 3.1 Pro). Needs OPENROUTER_API_KEY for Gemini 3.x (Vertex
# AI route — AI Studio's OpenAI-compat shim doesn't ship 3.x yet).
uv run python web/scripts/generate-demo-6llm.py \
    --lineup flagship-all --hands 30 --out pilot-flagship-30h \
    --seed 17 --max-tokens-cap 3000000
```

Per-hand progress prints to stderr — a 3-hour run isn't a black box. Generators refuse to overwrite an existing session without `--force`. The replay viewer is local with `cd web && npm install --legacy-peer-deps && npm run dev`. For full session-config knobs, agent types, JSONL schema, and per-provider quirks, see [USAGE.md](USAGE.md).

---

## The experiment

Existing poker-AI work (Pluribus, ReBeL) uses purpose-built solvers. This project asks a different question: **how well do general-purpose LLMs play when given the same tools a human pro would use, and how does that competence vary across providers?**

The setup is intentionally controlled. Six providers, one per seat — Anthropic / OpenAI / DeepSeek / Qwen / Kimi / Gemini — same engine, same RNG seed, same utility tools (`pot_odds`, `spr`, `hand_equity_vs_ranges`, `get_opponent_stats`), same bounded ReAct loop. The only thing that changes is the model.

Three demos shipped, escalating from cheap to all-out flagship:

| | Lineup | Hands | Cost | Wall time | Censored |
|---|---|---|---|---|---|
| **[Baseline](https://jaycheng113.github.io/llm-poker-arena/?session=demo-6llm)** | mini-tier across all 6 (Haiku 4.5, GPT-5.4-mini, etc.) | 30 | $0.83 | 54 min | 0 / 30 |
| **[Single-flagship swap](https://jaycheng113.github.io/llm-poker-arena/?session=demo-6llm-flagship)** | same field, Anthropic upgraded Haiku→Sonnet 4.6 | 102 | $3.85 | 3 h 4 min | 0 / 102 |
| **[All-flagship](https://jaycheng113.github.io/llm-poker-arena/?session=pilot-flagship-30h)** | every seat upgraded — Opus 4.7 / GPT-5.5 / DeepSeek V4-Pro / Qwen 3.6-Max-Preview / Kimi K2.6 / Gemini 3.1-Pro-Preview | 30 | $2.92 | 1 h 46 min | 1 / 30 |

The first two ran 100% clean. The all-flagship had one Kimi K2.6 turn exceed the 60s per-iteration timeout — surfaced as a config-tuning TODO for the next-flagship lineup, not a protocol bug.

## Headline finding

> **Single-model upgrade swung the field by 24,000 chips.** Anthropic's seat
> went from **dead last** in the baseline (Haiku, −13,750 chips / 30 hands)
> to **first** in the flagship variant (Sonnet, +9,908 chips / 102 hands)
> against the same five opponents. The baseline's surprising "GPT-5.4-mini
> wins" headline was mostly 30-hand variance — past one button rotation × 17
> with the field fixed, the strong-vs-weak gap opens up.

| Rank | Baseline (30 h, mini Haiku) | Flagship (102 h, Sonnet) | Δ |
|---|---|---|---|
| 🥇 | gpt-5.4-mini  +19,200 | **claude-sonnet-4-6  +9,908** | Sonnet last → first |
| 🥈 | qwen3.6-plus   +2,550 | qwen3.6-plus       +7,950 | Qwen consistent |
| 🥉 | deepseek-chat    −200 | gpt-5.4-mini         −258 | GPT regressed to mean |
| 4 | gemini-2.5-flash −1,600 | deepseek-chat     −1,300 | – |
| 5 | kimi-k2.5      −6,200 | kimi-k2.5         −6,500 | Kimi consistently bad |
| 6 | **claude-haiku-4-5 −13,750** | gemini-2.5-flash **−9,800** | Haiku → Gemini |

### And then we upgraded every seat

The all-flagship 30-hand pilot was run twice (same seed, fresh stochastic LLM outputs) to test whether the ranking is signal or 30-hand variance. **Identical ordering across both runs:**

| Rank | Run 1 (low effort) | Run 2 (medium effort, current shipped) | Δ |
|---|---|---|---|
| 🥇 | qwen3.6-max-preview     +4,750 | **qwen3.6-max-preview     +4,200** | repeat |
| 🥈 | deepseek-v4-pro         +1,300 | deepseek-v4-pro           +1,800 | repeat |
| 🥉 | gpt-5.5                   +500 | gpt-5.5                   +1,350 | +850 (effort↑) |
| 4 | kimi-k2.6                  +350 | kimi-k2.6                  −750 | one censored hand cost it |
| 5 | gemini-3.1-pro-preview  −1,200 | gemini-3.1-pro-preview   −1,900 | repeat |
| 6 | **claude-opus-4-7      −5,700** | **claude-opus-4-7       −4,700** | repeat |

**The most expensive flagship lost the most chips, twice in a row.** Opus 4.7 cost $1.08 over 30 hands and dropped −4,700; Qwen 3.6-Max-Preview cost $0.44 and netted +4,200. The Anthropic-vs-rest gap from the single-flagship-swap experiment **inverts** when every other seat also upgrades — Sonnet was first against minis, Opus is last against fellow flagships.

[Hand 25 in run 1](https://jaycheng113.github.io/llm-poker-arena/?session=pilot-flagship-30h&hand=25) caught Opus committing a literal card-counting hallucination on the turn — claimed "5-5-5-2-2 = fives full of deuces" with pocket 22 on a 5h-6s-9d-5d board, which only has two 5s. Then over-bet 3000 into a 5000 pot. The same setup in run 2 (different LLM stochastic output) had Opus self-correct on the turn and fold to a smaller loss. Single-hand reasoning failures aren't reproducible across re-rolls; the *aggregate* P&L pattern is.

## How each LLM actually played

Three numbers tell most of the story per seat:

| LLM (flagship lineup) | Utility-tool calls / hand | VPIP / PFR / AF | Style |
|---|---|---|---|
| **Claude Sonnet 4.6** | 0.55 (highest) | 31 % / 26 % / **5.0** | Tight-aggressive quant — the GTO student |
| **Qwen 3.6-plus** | **0.00** (none) | 24 % / 9 % / 0.7 | Passive caller, no math, somehow second |
| GPT-5.4-mini | 0.08 | 40 % / 25 % / 1.5 | Loose reasoning model, 67 % silent summaries |
| DeepSeek-chat | 0.43 | 16 % / 6 % / 1.1 | Tight-passive math, second-guesses itself |
| Kimi K2.5 | 0.19 | 18 % / 11 % / 1.3 | Verbose mixed — long thoughts, modest results |
| Gemini 2.5-flash | 0.02 | 15 % / 9 % / 2.0 | Passive frequency, "weak hand / OOP / free check" |

(VPIP = voluntary money in pot; PFR = preflop raise; AF = aggression factor = bet+raise / call.)

The clearest correlation in the flagship data isn't "model size" but **AF combined with active reasoning surface**. Sonnet (5.0 + heaviest tool use) wins; Gemini (2.0 but ~no tools and tightest entry) loses. Qwen is the outlier — passive but consistent enough to beat the noisier players.

<details>
<summary><b>Per-LLM panel-level analysis</b> (click to expand — 6 short paragraphs on what each seat actually wrote)</summary>

- **Sonnet** treats every borderline spot as a homework problem: opens with `## Hand Analysis`, calls `hand_equity_vs_ranges` against narrowed opponent ranges, **revises** equity when multi-way folds inflate it, and folds even big draws when math says so. On hand 53 turn it folded a flush + straight draw because equity dropped from 31 % heads-up to 8.9 % against a tight bet — pure discipline.
- **Qwen** never invokes a single utility tool across 102 hands and still finishes 🥈. It writes long prose, trusts its read, and makes the line. The passive-caller profile (AF 0.7) means it lets weaker hands stay in cheaply, then takes their stack at showdown.
- **GPT-5.4-mini** is the only seat routed through OpenAI's Responses API, so its reasoning surfaces as a `kind=summary` artifact. Wide preflop range (VPIP 40 %), short summaries, lots of small bets. Wins the baseline by being aggressive in a passive field, but regresses to mean once Sonnet shows up.
- **DeepSeek-chat** computes pot odds 18 times per 100 hands but barely raises (PFR 6 %). Its panels have a recurring tic of *deciding* and then *un-deciding* between iterations.
- **Kimi K2.5** writes the longest internal chain-of-thought of the field (avg 1907 chars / turn), often containing more reasoning than the actual decision warrants. Verbose ≠ accurate.
- **Gemini 2.5-flash** is the test case for "pure intuition." 1.3 % utility-tool usage, the tightest VPIP at 15 %, and `"weak hand / out of position / take a free card"` shows up so often in its panels it reads like a template. Result: most folds, fewest bets, biggest loss.

</details>

For the full per-LLM behavior table — VPIP by position, action distribution by pot type (heads-up vs multi-way vs 3-bet), street-by-street fold rates, response to ≥ half-pot bets — see **[docs/llm-decision-profile.md](docs/llm-decision-profile.md)** (regenerated from the same JSONL by `scripts/analyze_decision_types.py`). Some non-obvious findings from the bucketed data:

- **Position discipline** (BTN VPIP minus UTG VPIP) is widest for Qwen (+36 pp) and narrowest for Kimi (+12 pp). Kimi plays roughly the same range from any seat — a leak you can attack from late position.
- **Sonnet folds 60 % to ≥ half-pot post-flop bets** (the highest of the field). Its "fold to discipline" stance is exploitable by polarized large bets — the same quant rigor that makes it +9k overall is the lever to lift chips off it.
- **Qwen is the stickiest** — only 33 % fold to those same big bets. That's why it wins vs aggressive bluffs even with no math.
- **Kimi shuts down completely in 3-bet pots**: 100 % fold rate (n=4). In the field's cheapest-to-attack spot, it surrenders without exception.

A follow-up pilot tried to monetize these four findings by dropping a per-opponent ExploitBot into seat 5 and measuring P&L against a generic RuleBased control in the same seat. The result: 0 / 5 rules fired in 54 hands. **The findings are real but not exploitable from seat 5 against the current lineup** — the seat geometry blocks every "steal vs Kimi" preflop spot, and the TAG baseline range starves the postflop rules of opportunities. Postmortem with the gate-pass histogram and the cheaper checks that would have caught this in 6 hands instead of 54: [`docs/exploit-pilot-postmortem.md`](docs/exploit-pilot-postmortem.md).

You can verify any of this yourself: open the [flagship demo](https://jaycheng113.github.io/llm-poker-arena/?session=demo-6llm-flagship), click around, read the right-hand panel.

## Architecture

Reproducible 6-max NLHE engine wrapping **PokerKit 0.7.3** as the canonical state, plus a zero-backend React replay viewer. The hard part is the agent loop: every `LLMAgent` runs a **bounded ReAct loop** (`think → maybe call utility tool → observe → commit one action`) with **four independent retry budgets** for API errors, illegal actions, missing tool calls, and tool misuse — taxonomy frozen in spec §4.1 BR2-05. Engine truth, public events, and per-turn agent-view snapshots write to **three separate JSONL files** crossing the engine ↔ agent trust boundary as frozen Pydantic DTOs, so the web UI replays anything client-side without trusting unredacted state.

Seven providers ship through one common interface; reasoning visibility for each is its own protocol-shaped fight:

| Provider | API path | Reasoning surfaced via |
|---|---|---|
| Anthropic | native `anthropic` SDK | prose rationale, captured directly |
| Qwen | OpenAI-compat (DashScope) | prose rationale |
| **OpenAI (gpt-5 / o-series)** | **Responses API** | `kind=summary` artifact (Chat Completions returns counts only) |
| DeepSeek + Kimi | OpenAI-compat | `reasoning_content` field, round-tripped on multi-turn calls |
| **Gemini** | OpenAI-compat shim | `<thought>` block via double-`extra_body` wire-format trick |
| Grok | OpenAI-compat (x.ai) | prose rationale |

All five reasoning forms collapse into one `REASONING` panel; **markdown rendered client-side** (~9 KB gzip, with a defense-in-depth regex sanitizer). The double-`extra_body` Gemini quirk censored 3/3 hands until discovered — see [USAGE.md](USAGE.md) per-provider section for the full set of in-production protocol gotchas.

**Quality gates**: 502 backend (unit / integration / property / differential) + 115 web (vitest + Playwright e2e), with real-API integration tests gated by `<PROVIDER>_INTEGRATION_TEST=1` env vars so CI runs $0. Two GitHub Actions workflows ([python.yml](.github/workflows/python.yml), [web.yml](.github/workflows/web.yml)) run the full lint + type + test stack on every PR. **~$5 of API spend** buys both `demo-6llm` + `demo-6llm-flagship` from scratch.

## Screenshots

| | |
|---|---|
| ![River end](docs/images/showdown.png) | ![Session summary](docs/images/summary.png) |
| God-view river end with the standings leaderboard and street-grouped action timeline | Per-seat P&L, USD cost, token use, retry/error status, plus HUD stats (VPIP / PFR / 3-bet / AF / WTSD) |
| ![Flagship hero](docs/images/flagship-hero.png) | ![Flagship summary](docs/images/flagship-summary.png) |
| Sonnet 4.6 mid-flop, multi-section markdown reasoning visible | 102-hand flagship summary — Sonnet leads with +9,908 |

![Dev mode](docs/images/dev-mode.png)
*Dev mode (`?dev=1`): per-iteration debug badges + raw `agent_view_snapshot` JSON viewer.*

## Tech stack

- **Backend**: Python ≥3.11 (CI runs 3.11) · PokerKit 0.7.3 · Pydantic 2 · `pytest` · `mypy` · `ruff` · packaging via [`uv`](https://github.com/astral-sh/uv)
- **Providers**: `anthropic` SDK · `openai` SDK (also drives DeepSeek / Qwen / Kimi / Grok / Gemini via `base_url` override + the Responses API for OpenAI reasoning models)
- **Web**: React 19 · Vite 8 · TypeScript 6 · Tailwind CSS v3 · [Tremor](https://www.tremor.so/) · [@lobehub/icons](https://github.com/lobehub/lobe-icons) · `marked` (markdown render) · `lucide-react`
- **Test**: Vitest · `@testing-library/react` · Playwright
- **Deploy**: GitHub Actions → GitHub Pages (no backend; first-paint 79 KB gzip)

## Roadmap

What's done is in [CHANGELOG.md](CHANGELOG.md). What's interesting next:

- **All-flagship lineup** — currently only Anthropic is upgraded; running Opus 4.7 + GPT-5.5 + Gemini 3.1-Pro + Kimi K2.6 + Qwen3-Max + DeepSeek V4-Pro side-by-side would cost ~$25 for 100 hands but settle the "do flagships actually play differently" question.
- **Statistical significance bands** — 102 hands is enough to spot a 24 k swing but not enough to bound 5 k differences. A 500-hand run with bootstrap CIs would let the Qwen-vs-DeepSeek gap stop being anecdotal.
- **Live spectator mode** — current replay is post-hoc; a backend streaming session state over WebSocket would let visitors watch a tournament in progress.
- **Web-based human vs. LLM** — currently CLI-only; a hosted variant needs auth + BYOK key handling so visitors don't burn the host's API budget.
- **Animations** — chip slide actor → pot, card flip on reveal (~50 KB framer-motion).

## License

[MIT](LICENSE) © 2026 Jay Cheng
