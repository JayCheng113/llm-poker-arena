# llm-poker-arena Usage Guide

A multi-agent simulation framework for No-Limit Texas Hold'em 6-max
poker. Mix human players, rule-based bots, and LLM agents (Anthropic /
OpenAI / DeepSeek) in the same session; replay any hand from the
3-layer JSONL artifacts.

## Quick start

### Run a session with bots

    pip install -e .
    poker-play

Plays 6 hands with HumanCLIAgent at seat 3 and Random/RuleBased bots
elsewhere. Logs land in `runs/session_<timestamp>_seed42/`.

### Add an LLM opponent

    export ANTHROPIC_API_KEY=sk-ant-...
    poker-play \
      --llm-seat 0 --llm-provider anthropic --llm-model claude-haiku-4-5

You're at seat 3, Claude Haiku 4.5 plays seat 0, bots fill 1/2/4/5.

### Two LLMs (you spectate)

    export ANTHROPIC_API_KEY=sk-ant-...
    export DEEPSEEK_API_KEY=sk-...
    poker-play \
      --llm-seat 0 --llm-provider anthropic --llm-model claude-haiku-4-5 \
      --llm-seat 4 --llm-provider deepseek  --llm-model deepseek-chat

## Agent types

| Type | Status | Tools | Notes |
|------|--------|-------|-------|
| `RandomAgent` | shipped | none | Uniform over legal actions |
| `RuleBasedAgent` | shipped | none | TAG baseline (preflop pair-strength + position) |
| `HumanCLIAgent` | shipped | none | Reads stdin (one human per session) |
| `LLMAgent` + Anthropic | shipped | math + equity | Claude Haiku 4.5 / Opus 4.7 / Sonnet 4.6 |
| `LLMAgent` + OpenAI | shipped | math + equity | GPT-4o, etc. — Chat Completions API |
| `LLMAgent` + DeepSeek | shipped | math + equity | deepseek-chat / deepseek-reasoner |

## Cost guard

Set `SessionConfig.max_total_tokens` to abort cleanly when cumulative
tokens (input+output across all seats) exceed the cap:

    cfg = SessionConfig(..., max_total_tokens=500_000)

500K tokens ≈ $3 at Claude Haiku 4.5 rates. Abort happens at the next
hand boundary (clean artifacts). `meta.json.stop_reason` records
`"max_total_tokens_exceeded"`.

CLI flag for this is not yet exposed — set programmatically via
SessionConfig in a Python script.

## Log file structure

Each session writes to `runs/session_<ts>_seed<N>/`:

- `config.json` — frozen SessionConfig snapshot (reproducibility)
- `canonical_private.jsonl` — engine truth, one line per hand (all hole cards)
- `public_replay.jsonl` — UI-safe events, one line per hand
- `agent_view_snapshots.jsonl` — per-turn per-seat views + LLM iterations
- `censored_hands.jsonl` — hands aborted by API error (BR2-01)
- `meta.json` — session-level summary (chip P&L, retry/token aggregations,
  provider capabilities, stop reason)

For analysis, use the DuckDB query layer:

    from llm_poker_arena.storage.duckdb_query import open_session
    con = open_session("runs/session_xxx", access_token=...)
    con.execute("SELECT seat, COUNT(*) FROM actions GROUP BY seat").fetchall()

## Troubleshooting

**`poker-play` exits with `session directory ... already exists`** —
session dirs include microseconds. Re-run; should auto-resolve.

**`API key not set` error** — confirm the env var name matches
provider: `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`.

**Real LLM session takes minutes** — that's normal. Each turn = 1 API
call (~1-3s for Haiku, longer for Opus/Reasoner).

**`assertion failed: chip_pnl` in tests** — usually means the engine
audit failed mid-hand; check the test's `tmp_path` for `.jsonl`
artifacts and inspect `state` errors.

## Configuration knobs (SessionConfig)

- `num_players` — currently fixed at 6 (engine assumption)
- `num_hands` — must be multiple of `num_players` (balanced button rotation)
- `enable_math_tools` — exposes pot_odds + spr + hand_equity_vs_ranges to LLMs
- `enable_hud_tool` — opponent stats tool (NOT yet implemented; Phase 5+)
- `rationale_required` — strict mode: empty text + tool call triggers retry
- `max_utility_calls` — per-turn LLM tool-call budget (default 5)
- `max_total_tokens` — session-level cost cap (None = no cap)

## Architecture overview (one-paragraph)

The engine wraps PokerKit as a single canonical state. PlayerView /
PublicView projections cross the engine/agent trust boundary as frozen
Pydantic DTOs. Agents (sync `decide` for Random/RuleBased/HumanCLI,
async for LLM) return TurnDecisionResult; Session orchestrates the
multi-hand loop and persists 3-layer JSONL artifacts. LLMAgent runs a
bounded ReAct loop (K+1 = max_utility_calls utility tool calls + 1
forced action commit) with 4 independent retry counters per spec
§4.1 BR2-05.
