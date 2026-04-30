# ♠ LLM Poker Arena

[![python ci](https://github.com/JayCheng113/llm-poker-arena/actions/workflows/python.yml/badge.svg)](https://github.com/JayCheng113/llm-poker-arena/actions/workflows/python.yml)
[![web ci](https://github.com/JayCheng113/llm-poker-arena/actions/workflows/web.yml/badge.svg)](https://github.com/JayCheng113/llm-poker-arena/actions/workflows/web.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python ≥3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](pyproject.toml)

Six general-purpose LLMs sit at a No-Limit Hold'em table with the same tools a human pro would use — pot odds, equity vs. range, opponent stats — and play it out for chips. Every decision, every prose rationale, every tool call is replayable in a browser, side by side with the table state.

> **Same provider, three different fields, three different ranks.**
> Anthropic's seat finished **6th** in the mini-tier baseline (Haiku),
> **1st** in the single-flagship-swap (Sonnet against the same minis),
> and **6th again** in the all-flagship pilot (Opus against fellow
> flagships). Capability is not monotonic when the rest of the table
> upgrades too — and the only model that stays top-2 across all three
> tiers is Qwen, which never calls a single utility tool.

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

> **Same provider, three different fields, three different ranks.**
> Anthropic's seat finishes 6th → 1st → 6th. OpenAI goes 1st → 3rd → 3rd.
> The only seat that stays top-2 across all three demos is Qwen — which
> never calls a single utility tool in the 102-hand flagship session.

The headline isn't "model X is best." It's that **provider rank is not stable across opponent fields**, even when you upgrade every seat in lockstep. Here's the per-provider arc across all three demos (P&L in chips relative to the 10,000-chip starting stack):

| Provider | Baseline (mini, 30 h) | Single-flagship swap (Sonnet vs minis, 102 h) | All-flagship (30 h) |
|---|---|---|---|
| **Anthropic** | Haiku 4.5 — 6th, **−13,750** | **Sonnet 4.6 — 1st, +9,908** | Opus 4.7 — **6th, −4,700** |
| **OpenAI** | GPT-5.4-mini — **1st, +19,200** | GPT-5.4-mini — 3rd, −258 | GPT-5.5 — 3rd, +1,350 |
| **Qwen** | 3.6-plus — 2nd, +2,550 | 3.6-plus — 2nd, +7,950 | **3.6-Max-Preview — 1st, +4,200** |
| **DeepSeek** | chat — 3rd, −200 | chat — 4th, −1,300 | V4-Pro — **2nd, +1,800** |
| **Kimi** | K2.5 — 5th, −6,200 | K2.5 — 5th, −6,500 | K2.6 — 4th, −750 |
| **Gemini** | 2.5-flash — 4th, −1,600 | 2.5-flash — 6th, −9,800 | 3.1-Pro-Preview — 5th, −1,900 |

Three things fall out:

1. **A single seat upgrade swung the field by 24,000 chips.** Anthropic Haiku → Sonnet (only that one seat changed; all other five stayed at mini-tier) flipped the Anthropic seat from dead last to first against an unchanged opponent set. The baseline's "GPT-5.4-mini wins by 19k" headline was almost entirely 30-hand variance — over 102 hands with the field fixed, the strong-vs-weak gap opens up the way you'd expect.
2. **Capability is not monotonic when the rest of the table upgrades too.** Sonnet was the strongest seat in a field of minis. Opus 4.7 — Anthropic's flagship-of-flagships at 7× Sonnet's price — was the *weakest* seat in a field of fellow flagships. Anthropic's relative position depends on the field, not on absolute model power.
3. **The most expensive flagship lost the most chips. The cheapest flagship won the most.** Opus 4.7 burned $1.08 to lose 4,700 chips. Qwen 3.6-Max-Preview spent $0.44 to net +4,200. The all-flagship pilot was run twice at the same seed (independent stochastic outputs) — identical 1-2-3-4-5-6 ordering both times, so this isn't 30-hand luck.

The Opus collapse is concrete enough to point at. **[Hand 25 in the all-flagship demo](https://jaycheng113.github.io/llm-poker-arena/?session=pilot-flagship-30h&hand=25)** caught Opus literally hallucinating cards on a 5h-6s-9d-5d board with pocket 22 — wrote *"5-5-5-2-2 = fives full of deuces"* in its rationale (the board only has two 5s) and then over-bet 3,000 into a 5,000 pot. The same setup at the same seed with re-rolled LLM stochastic output had Opus self-correct on the turn and fold for a fraction of the loss. **Single hands are noisy; the aggregate ranking is stable.** That's the only useful claim a 30-hand pilot lets you make, and it's the one we make.

## How each LLM actually played

Cross-referencing the HUD with the per-provider arc above, six clear personalities. The flagship-session tool-call / VPIP / AF table is the cleanest snapshot we have — the all-flagship pilot's 30 hands aren't enough sample for postflop buckets, but the headline behaviors carry through:

| LLM (102 h flagship) | Util tools / hand | VPIP / PFR / AF | Style — and how it travelled across demos |
|---|---|---|---|
| **Sonnet 4.6** | 0.55 (highest) | 31 % / 26 % / **5.0** | The GTO student. Wins outright at the flagship-mini interface, **but** Anthropic's larger sibling Opus 4.7 — same school, more confident — is the bottom of the all-flagship table. Discipline beats minis; over-confidence loses to peers. |
| **Qwen 3.6-plus** | **0.00** (none) | 24 % / 9 % / 0.7 | The only top-2 finisher in *every* demo. Never opens a single utility tool over 102 hands. Just calls down with mid-strength, takes stacks at showdown. Qwen Max-Preview keeps the formula and wins the all-flagship outright. |
| **GPT-5.4-mini → GPT-5.5** | 0.08 → 0.00 | 40 % / 25 % / 1.5 | Loose-aggressive, summary-only reasoning surface. The 1st → 3rd → 3rd arc is exactly what regression-to-mean looks like once the sample is large enough. GPT-5.5 at `reasoning_effort=medium` (low nerfed it; see CHANGELOG) climbs to 3rd and breaks even. |
| **DeepSeek-chat → V4-Pro** | 0.43 → 0.20 | 16 % / 6 % / 1.1 | Tight-passive math nerd, computes pot odds and then second-guesses itself. The provider's only positive arc — V4-Pro takes 2nd in all-flagship by being the least confused mid-table seat. |
| **Kimi K2.5 → K2.6** | 0.19 → 0.00 | 18 % / 11 % / 1.3 | Verbose. Avg 1907 chars internal reasoning per turn at K2.5, often more analysis than the spot warrants. Folds 100 % of 3-bet pots (n=4). K2.6 walks back to 4th in the flagship field — same nit profile, but the field around it got worse, so it shed less. |
| **Gemini 2.5-flash → 3.1-Pro-Preview** | 0.02 → 0.17 | 15 % / 9 % / 2.0 | Pure-intuition seat. The phrase *"weak hand / out of position / take a free check"* shows up so often in 2.5-flash panels it reads like a template. 3.1-Pro-Preview opens up slightly (uses tools 5× per 30 hands vs 0.6) and trims the loss, but the bottom-third pattern persists. |

(VPIP = voluntary money in pot; PFR = preflop raise; AF = aggression factor = (bet+raise) / call.)

The clearest correlation isn't model size or price — it's **AF combined with whether the model actually consults the tools that are sitting in front of it**. Sonnet does both and wins the mini field. Qwen does neither and wins by being unbluffable. Gemini and Kimi do neither *and* play scared, and lose every demo. The two flagship-tier disasters (Opus, Gemini 3.1) suggest a third pattern: when a strong model gets *over*-confident in its read, the absence of tool-call discipline starts to bite — Opus's hand-25 hallucination is the cartoon version of what 4,700 chips of compounding small over-bets looks like.

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

- **All-flagship 102-hand marquee** — the 30-hand pilot already shows the Opus-bottom / Qwen-top order is reproducible across two stochastic runs at the same seed, but a full 102-hand run (~$12) would let the mid-pack ranking (DeepSeek V4-Pro ≈ GPT-5.5 ≈ Kimi K2.6) stop being noise-bounded.
- **Statistical significance bands** — even at 102 hands a 5,000-chip difference is inside one-orbit variance. A 500-hand run with paired bootstrap CIs would let the Qwen-vs-DeepSeek gap, and the all-flagship mid-pack, stop being anecdotal.
- **Live spectator mode** — current replay is post-hoc; a backend streaming session state over WebSocket would let visitors watch a tournament in progress.
- **Web-based human vs. LLM** — currently CLI-only; a hosted variant needs auth + BYOK key handling so visitors don't burn the host's API budget.
- **Animations** — chip slide actor → pot, card flip on reveal (~50 KB framer-motion).

## License

[MIT](LICENSE) © 2026 Jay Cheng
