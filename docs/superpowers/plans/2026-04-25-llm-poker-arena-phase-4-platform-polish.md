# Phase 4 Platform Polish: Codex Backlog + CLI LLM Support + Cost Guard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (inline mode chosen by user) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pay off codex deferred backlog (AgentDescriptor.temperature/seed + meta.json retry/token aggregation) AND extend the platform's daily-use ergonomics: SessionConfig token-based cost cap, `poker-play` CLI accepting LLM agents (3 providers), USAGE.md so a fresh user can run a session in 5 minutes. Pivots the project from "research artifact" to "usable competition platform" per user direction (agents compete normally now; humans participate next).

**Architecture:**
- AgentDescriptor temp/seed: introduce `Agent.metadata() -> dict | None` ABC method. LLMAgent returns `{"temperature": 0.7, "seed": 42}`; non-LLM agents return None. Session passes the dict into `build_agent_view_snapshot` which forwards to `AgentDescriptor`. Backward-compatible — existing agents (Random, RuleBased, HumanCLI) inherit None default.
- meta.json aggregation: Session accumulates per-seat counters during `_run_one_hand` from `decision.{api_retry_count, illegal_action_retry_count, no_tool_retry_count, tool_usage_error_count, default_action_fallback, turn_timeout_exceeded}` and `decision.total_tokens`. At session end, dump as `retry_summary_per_seat` + `tool_usage_summary` + `total_tokens` in meta.json.
- Cost cap: `SessionConfig.max_total_tokens: int | None = None`. After each hand, check session-cumulative token count against cap. If exceeded, log a soft abort signal in meta.json (`stop_reason: "max_total_tokens_exceeded"`) and break out of the multi-hand loop cleanly. NOT mid-hand abort — clean hand boundaries only.
- CLI LLM support: argparse `action='append'` for `--llm-seat`/`--llm-provider`/`--llm-model` triplet. API keys auto-loaded from env (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`). Provider construction reuses Phase 3b's `AnthropicProvider` and `OpenAICompatibleProvider` (`base_url=None` for OpenAI, `https://api.deepseek.com/v1` for DeepSeek).
- USAGE.md: ~80 lines covering quick start, agent type catalog, log file structure, common config knobs, troubleshooting.

**Tech Stack:** No new dependencies. Reuses Phase 3b providers, Phase 3c-equity tools, Phase 1 SessionConfig validation.

---

## Phase 4 Scope Decisions

1. **Cost cap unit = tokens, not USD**: simpler (no pricing matrix needed; that's Phase 5 candidate). User-facing knob `max_total_tokens=500_000` is intuitive for "stop if I burn ~$3 worth at Haiku rates". Pricing matrix conversion to USD lives in DuckDB analysis layer post-session.
2. **Cost cap abort = hand boundary, not mid-hand**: cleaner — finished hands have complete artifacts, partial hands are messy (mid-hand abort would need asyncio cancellation everywhere). After each `_run_one_hand` finishes, if cumulative tokens > cap, set `stop_reason="max_total_tokens_exceeded"` and break.
3. **CLI supports up to N LLM seats** (not just 1): multi-LLM tournaments via CLI valuable for "human spectates 2 Claudes vs RuleBased" demos. Argparse `action='append'` for seat/provider/model triplets.
4. **API keys via env vars only, never command line**: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`. Refuse to start if `--llm-seat` set but corresponding env var missing — fail-fast with clear message.

## Spec Items Now Closed (no longer deferred)

- **§7.4 AgentDescriptor.temperature/seed** ✅ Task 1
- **§7.6 retry_summary_per_seat / tool_usage_summary / total_tokens** ✅ Task 2

## Spec Items Still Deferred (consciously, not done in Phase 4)

- USD pricing matrix + estimated_cost_breakdown (Phase 5 if/when needed)
- LLMProvider.static_capability() (probably never needed)
- Anthropic extended-thinking enablement
- OpenAI Responses API (o-series)
- weighted range support in equity tool
- 3c-hud (HUD stats) — see plan §"3c/3e Status" for rationale
- 3e-experiment (1000-hand pure-LLM session) — academic/portfolio, not user priority
- Web UI / multi-human concurrent sessions — long-horizon

## 3c / 3e Status (FYI, not action items)

- **3c-math + 3c-equity**: shipped. Math + equity utility tools available to LLM agents.
- **3c-hud**: deferred indefinitely. 0/22 organic utility-call rate in real-Anthropic gated tests (3c-math + 3c-equity) suggests Claude doesn't use existing tools when 4/6 seats are Random. Adding HUD stats unlikely to change this without prompt-tuning. Re-evaluate trigger: human players join sessions and complain about LLM tool use, OR pure-LLM session shows tools ARE used.
- **3e-telemetry**: ✅ absorbed into Phase 4 Tier 1 (Tasks 1+2 close codex deferred items I8 + I9).
- **3e-experiment** (1000-hand academic): not in Phase 4 scope. User reframed away from portfolio/academic priority; can resurrect in 1 day if/when needed (all infra is ready post-Phase 4).

## Risks Acknowledged Up Front

- **Agent.metadata() ABC change is backward-incompatible at the Python level** but compatible at the runtime level (default returns None, Session handles None). Existing 3 non-LLM agents (Random, RuleBased, HumanCLI) need a 1-line `metadata` method addition each.
- **`max_total_tokens` cost cap requires Session to track tokens across hands**. Per-hand `decision.total_tokens` is already in the IterationRecord stream; aggregator is straightforward. No risk to existing test suite — `max_total_tokens=None` default preserves behavior.
- **CLI LLM extension exposes API keys env-driven** — if user accidentally pushes `.env` with real keys, that's their problem. We document `.env.example` already exists.
- **Multi-LLM CLI session can run for minutes** with stdin paused on human input. No risk if scripted; in real interactive use, user is the rate limiter.

---

## File Structure

**Modified files:**
- `src/llm_poker_arena/agents/human_cli.py:1-9` — docstring fix (one-line Phase 3 catch-up)
- `src/llm_poker_arena/agents/base.py` — add `Agent.metadata() -> dict[str, Any] | None` ABC method with default `None`
- `src/llm_poker_arena/agents/llm/llm_agent.py:_init_` — implement `metadata()` returning `{"temperature": self._temperature, "seed": self._seed}`
- `src/llm_poker_arena/storage/layer_builders.py:build_agent_view_snapshot` — accept optional `agent_temperature: float | None` and `agent_seed: int | None`; forward to `AgentDescriptor`
- `src/llm_poker_arena/session/session.py:_run_one_hand` — call `agent.metadata()`, pass into `build_agent_view_snapshot`
- `src/llm_poker_arena/session/session.py:run` — accumulate per-seat retry/token counters; check max_total_tokens after each hand
- `src/llm_poker_arena/storage/meta.py:build_session_meta` — accept new kwargs `retry_summary_per_seat`, `tool_usage_summary`, `total_tokens`, `stop_reason`
- `src/llm_poker_arena/engine/config.py:SessionConfig` — add `max_total_tokens: int | None = None` field
- `src/llm_poker_arena/cli/play.py` — extend `argparse` + `build_agents` to support `--llm-seat/--llm-provider/--llm-model` triplets

**New files:**
- `USAGE.md` (project root) — quick start + agent catalog + log structure + config knobs

**New tests:**
- `tests/unit/test_agent_metadata.py` — Agent.metadata default + LLMAgent override
- `tests/unit/test_layer_builders_temp_seed.py` — build_agent_view_snapshot writes temp/seed to AgentDescriptor
- `tests/unit/test_session_meta_aggregation.py` — Session aggregates retry/tokens correctly across multi-hand session
- `tests/unit/test_max_total_tokens_cap.py` — Session aborts cleanly at hand boundary when cap exceeded
- `tests/unit/test_cli_play_with_llm.py` — `build_agents` constructs LLM agents from CLI args
- `tests/integration/test_human_vs_llm_mock.py` — full 6-hand CLI session with HumanCLI + mock-LLM (verify wiring)
- `tests/integration/test_human_vs_llm_real_anthropic.py` — gated, scripted-stdin human + Claude session

**Files NOT touched** (intentionally):
- `src/llm_poker_arena/agents/random_agent.py` — inherits Agent.metadata() default (returns None)
- `src/llm_poker_arena/agents/rule_based.py` — same
- All Phase 3 provider code — unchanged

---

## Test Counts (cumulative, baseline = 405 pass + 7 skip after Phase 3c-equity, verified 2026-04-25)

| Task | New tests | Cumulative pass | Cumulative skip |
|---|---|---|---|
| 0 | 0 (docstring only) | 405 | 7 |
| 1 | 6 (Agent.metadata default×2 + LLMAgent override×2 + build_agent_view_snapshot temp/seed×2) | 411 | 7 |
| 2 | 3 (per-seat retry agg + tool_usage agg + total_tokens agg) | 414 | 7 |
| 3 | 4 (default cap None + cap None runs full + cap aborts after hand + cap above total no-abort) | 418 | 7 |
| 4 | 4 (build_agents one-LLM + two-LLM + missing API key + LLM seat collides with human) | 422 | 7 |
| 5 | 0 (docs only) | 422 | 7 |
| 6 | 1 (mock human + LLM CLI integration) | 423 | 7 |
| 7 | 0 unit + 1 gated | 423 | 8 |
| 8 | 0 (lint + format drift cleanup) | 423 | 8 |

**Final all-gates-on**: 431 pass + 0 skip (423 non-gated + 8 gated: 7 prior + 1 new human-vs-Claude).

---

## Task 0: HumanCLIAgent docstring fix

**Files:**
- Modify: `src/llm_poker_arena/agents/human_cli.py:1-10` (replace stale "sync Agent" preamble)

- [ ] **Step 1: Read current docstring**

Run: `head -15 src/llm_poker_arena/agents/human_cli.py`
Expected: docstring claims "sync Agent" + "Phase 3 will rewrite" — both stale.

- [ ] **Step 2: Replace docstring**

Edit `src/llm_poker_arena/agents/human_cli.py`. Replace lines 1-10 with:

```python
"""HumanCLIAgent: async Agent that reads actions from a terminal.

Reads from a configurable text input stream (defaults to sys.stdin) and
writes prompts/state to a configurable output stream (defaults to
sys.stdout). The decide() method is async to fit the Phase 3+ Agent ABC
contract, but stdin reads are synchronous (blocking) — that's acceptable
because Session.run is sequential per turn and the human IS the rate
limiter, so blocking the event loop on input() costs nothing.

I/O is injectable (via `input_stream` + `output_stream` constructor args)
so unit tests can drive it deterministically. Production default is
`sys.stdin` / `sys.stdout`.
"""
```

- [ ] **Step 3: Verify suite still passes**

Run: `.venv/bin/pytest tests/unit/test_human_cli_agent.py tests/unit/test_human_cli_integration.py tests/unit/test_cli_play_smoke.py -q 2>&1 | tail -3`
Expected: 16 passed (no behavior change, docstring only).

- [ ] **Step 4: Lint**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/human_cli.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/llm_poker_arena/agents/human_cli.py
git commit -m "$(cat <<'EOF'
docs(human-cli): update stale docstring (Phase 4 Task 0)

Phase 3a widened Agent ABC to async; HumanCLIAgent.decide was rewritten
in that round, but the module docstring still claims "sync Agent" and
"Phase 3 will rewrite". Catch up the docstring to reality.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Agent.metadata() + AgentDescriptor.temperature/seed persistence

**Files:**
- Modify: `src/llm_poker_arena/agents/base.py` (add `metadata()` method to Agent ABC with default None)
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py` (override `metadata()` returning `{"temperature": ..., "seed": ...}`)
- Modify: `src/llm_poker_arena/storage/layer_builders.py:build_agent_view_snapshot` (accept temp/seed kwargs)
- Modify: `src/llm_poker_arena/session/session.py:_run_one_hand` (call `agent.metadata()`, pass to builder)
- Test: `tests/unit/test_agent_metadata.py` (NEW)
- Test: `tests/unit/test_layer_builders_temp_seed.py` (NEW)

**Why this closes codex deferred I8**: spec §7.4 promises agent-descriptor includes temperature/seed. Phase 2a hardcoded both to None because mock agents don't have them; Phase 3a/b/d kept the stub even though LLMAgent has both as private fields. This task plumbs them through.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_agent_metadata.py`:

```python
"""Agent.metadata() ABC + LLMAgent override (Phase 4 Task 1)."""
from __future__ import annotations

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent


def test_random_agent_metadata_returns_none() -> None:
    """Non-LLM agents have no temp/seed; metadata() defaults to None."""
    assert RandomAgent().metadata() is None


def test_rule_based_agent_metadata_returns_none() -> None:
    assert RuleBasedAgent().metadata() is None


def test_llm_agent_metadata_returns_temperature_and_seed() -> None:
    """LLMAgent surfaces its temperature + seed for spec §7.4 persistence."""
    provider = MockLLMProvider(script=MockResponseScript(responses=()))
    agent = LLMAgent(
        provider=provider, model="m1",
        temperature=0.7, seed=42,
    )
    md = agent.metadata()
    assert md == {"temperature": 0.7, "seed": 42}


def test_llm_agent_metadata_handles_none_seed() -> None:
    """seed=None is valid (Anthropic doesn't accept seed); metadata reflects."""
    provider = MockLLMProvider(script=MockResponseScript(responses=()))
    agent = LLMAgent(provider=provider, model="m1", temperature=0.5, seed=None)
    md = agent.metadata()
    assert md == {"temperature": 0.5, "seed": None}
```

Create `tests/unit/test_layer_builders_temp_seed.py`:

```python
"""build_agent_view_snapshot writes temp/seed to AgentDescriptor (Phase 4 Task 1)."""
from __future__ import annotations

from llm_poker_arena.agents.llm.types import TokenCounts
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.storage.layer_builders import build_agent_view_snapshot


def _view() -> PlayerView:
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                           position_full="x", stack=10_000,
                           invested_this_hand=0, invested_this_round=0,
                           status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="fold", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params,
    )


def test_build_snapshot_default_temp_seed_none() -> None:
    """No metadata passed → AgentDescriptor.temperature/seed stay None."""
    snap = build_agent_view_snapshot(
        hand_id=1, session_id="s1", seat=3, street=Street.PREFLOP,
        timestamp="2026-04-25T10:00:00.000Z",
        view=_view(), action=Action(tool_name="fold", args={}),
        turn_index=0,
        agent_provider="random", agent_model="uniform",
        agent_version="phase1", default_action_fallback=False,
    )
    assert snap.agent.temperature is None
    assert snap.agent.seed is None


def test_build_snapshot_with_metadata_persists_temp_seed() -> None:
    """metadata kwarg → AgentDescriptor.temperature/seed populated."""
    snap = build_agent_view_snapshot(
        hand_id=1, session_id="s1", seat=3, street=Street.PREFLOP,
        timestamp="2026-04-25T10:00:00.000Z",
        view=_view(), action=Action(tool_name="fold", args={}),
        turn_index=0,
        agent_provider="anthropic", agent_model="claude-haiku-4-5",
        agent_version="phase3d", default_action_fallback=False,
        agent_temperature=0.7, agent_seed=42,
        total_tokens=TokenCounts(input_tokens=100, output_tokens=20,
                                  cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
    )
    assert snap.agent.temperature == 0.7
    assert snap.agent.seed == 42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_agent_metadata.py tests/unit/test_layer_builders_temp_seed.py -v 2>&1 | tail -10`
Expected: FAIL — `metadata()` doesn't exist on Agent ABC; `build_agent_view_snapshot` doesn't accept `agent_temperature` kwarg.

- [ ] **Step 3: Add `Agent.metadata()` to the ABC**

Read `src/llm_poker_arena/agents/base.py`. Find the `Agent` class. Add a non-abstract method:

```python
    def metadata(self) -> dict[str, Any] | None:
        """Optional per-agent metadata for snapshot persistence (spec §7.4).

        LLM-backed agents return a dict like
        `{"temperature": 0.7, "seed": 42}`. Non-LLM agents (Random,
        RuleBased, HumanCLI) return None — their AgentDescriptor.temperature
        and .seed stay None in the snapshot.

        This is intentionally a regular method (not @abstractmethod) so
        existing agents inherit the None default without modification.
        """
        return None
```

Verify imports — if `Any` isn't already imported in base.py, add `from typing import Any`.

- [ ] **Step 4: Override `metadata()` in LLMAgent**

Edit `src/llm_poker_arena/agents/llm/llm_agent.py`. Find `LLMAgent`. Add as a method (place near `provider_id`):

```python
    def metadata(self) -> dict[str, Any] | None:
        """spec §7.4: surface temperature + seed for snapshot persistence."""
        return {"temperature": self._temperature, "seed": self._seed}
```

`Any` is already imported in llm_agent.py.

- [ ] **Step 5: Extend `build_agent_view_snapshot` signature**

Edit `src/llm_poker_arena/storage/layer_builders.py`. Find `build_agent_view_snapshot`. Add two new keyword-only params:

```python
def build_agent_view_snapshot(
    *, hand_id: int, session_id: str, seat: int, street: Street,
    timestamp: str, view: PlayerView, action: Action, turn_index: int,
    agent_provider: str, agent_model: str, agent_version: str,
    default_action_fallback: bool,
    iterations: tuple[IterationRecord, ...] = (),
    total_tokens: TokenCounts | Mapping[str, int] | None = None,
    wall_time_ms: int = 0,
    api_retry_count: int = 0,
    illegal_action_retry_count: int = 0,
    no_tool_retry_count: int = 0,
    tool_usage_error_count: int = 0,
    agent_temperature: float | None = None,
    agent_seed: int | None = None,
) -> AgentViewSnapshot:
```

Inside the function, the `AgentDescriptor(...)` construction. Find the line `seed=None,` (currently around line 240) and replace the descriptor construction with:

```python
        agent=AgentDescriptor(
            provider=agent_provider,
            model=agent_model,
            version=agent_version,
            temperature=agent_temperature,
            seed=agent_seed,
        ),
```

(Replaces the hardcoded `temperature=None, seed=None`.)

- [ ] **Step 6: Plumb metadata through Session._run_one_hand**

Edit `src/llm_poker_arena/session/session.py`. In `_run_one_hand`, find the `build_agent_view_snapshot(...)` call (around line 290+). Before the call, extract metadata:

```python
            agent_md = self._agents[actor].metadata() or {}
            snapshot = build_agent_view_snapshot(
                hand_id=hand_id, session_id=self._session_id, seat=actor,
                street=street, timestamp=_now_iso(), view=view,
                action=chosen, turn_index=turn_counter,
                agent_provider=provider, agent_model=model,
                agent_version="phase3a",
                default_action_fallback=fallback,
                iterations=decision.iterations,
                total_tokens=decision.total_tokens,
                wall_time_ms=decision.wall_time_ms,
                api_retry_count=decision.api_retry_count,
                illegal_action_retry_count=decision.illegal_action_retry_count,
                no_tool_retry_count=decision.no_tool_retry_count,
                tool_usage_error_count=decision.tool_usage_error_count,
                agent_temperature=agent_md.get("temperature"),
                agent_seed=agent_md.get("seed"),
            )
```

(Adding the two new kwargs at the end of the call.)

- [ ] **Step 7: Run all 4 new tests + verify regressions**

Run: `.venv/bin/pytest tests/unit/test_agent_metadata.py tests/unit/test_layer_builders_temp_seed.py -v 2>&1 | tail -10`
Expected: 4 tests pass.

Run full suite to verify no existing tests break:
`.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 411 pass + 7 skip.

- [ ] **Step 8: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add src/llm_poker_arena/agents/base.py \
        src/llm_poker_arena/agents/llm/llm_agent.py \
        src/llm_poker_arena/storage/layer_builders.py \
        src/llm_poker_arena/session/session.py \
        tests/unit/test_agent_metadata.py \
        tests/unit/test_layer_builders_temp_seed.py
git commit -m "$(cat <<'EOF'
feat(agents): Agent.metadata() persists temperature/seed (Phase 4 Task 1)

Closes codex deferred I8 (carried from Phase 3b/3c-math/3c-equity).
spec §7.4 promises AgentDescriptor.temperature/seed; Phase 2a/3a left
both hardcoded to None even though LLMAgent has them as private fields.

Architecture: new non-abstract Agent.metadata() returns None by default;
LLMAgent overrides to return {"temperature": self._temperature, "seed":
self._seed}. Session calls agent.metadata() and forwards to
build_agent_view_snapshot via two new optional kwargs (agent_temperature,
agent_seed). Backward-compatible: Random/RuleBased/HumanCLI inherit
None default.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: meta.json retry/token aggregation

**Files:**
- Modify: `src/llm_poker_arena/storage/meta.py:build_session_meta` (accept new kwargs)
- Modify: `src/llm_poker_arena/session/session.py` (accumulate per-seat counters; pass to meta builder)
- Test: `tests/unit/test_session_meta_aggregation.py` (NEW)

**Why this closes codex deferred I9**: spec §7.6 promises retry_summary_per_seat / tool_usage_summary / total_tokens to be populated. Phase 2a/3a left them as empty dicts. With Phase 3a-3c-equity all retry counters/tokens already in TurnDecisionResult, aggregation is straightforward.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_session_meta_aggregation.py`:

```python
"""Session aggregates per-seat retry/token counters into meta.json (Phase 4 Task 2)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _fold(uid: str, in_tok: int = 50, out_tok: int = 10) -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
        text_content="folding",
        tokens=TokenCounts(input_tokens=in_tok, output_tokens=out_tok,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def test_meta_total_tokens_aggregated_per_seat(tmp_path: Path) -> None:
    """Per-seat total_tokens dict reflects accumulated TurnDecisionResult.total_tokens."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    script = MockResponseScript(responses=tuple(
        _fold(f"t{i}") for i in range(200)
    ))
    provider = MockLLMProvider(script=script)
    llm_agent = LLMAgent(provider=provider, model="m", temperature=0.7)
    agents = [
        RandomAgent(),  # 0
        llm_agent,      # 1
        RandomAgent(),  # 2
        RandomAgent(),  # 3
        RandomAgent(),  # 4
        RandomAgent(),  # 5
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="meta_agg_test")
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    # Seat 1 (LLM) accumulated tokens. Random seats: not present (no LLM, no tokens).
    tokens = meta["total_tokens"]
    assert "1" in tokens, f"LLM seat 1 missing from total_tokens: {tokens}"
    assert tokens["1"]["input_tokens"] > 0
    assert tokens["1"]["output_tokens"] > 0
    # Random seats have no LLM iterations — they should not appear or have zero entries.
    for s in ("0", "2", "3", "4", "5"):
        if s in tokens:
            assert tokens[s]["input_tokens"] == 0
            assert tokens[s]["output_tokens"] == 0


def test_meta_retry_summary_per_seat_aggregated(tmp_path: Path) -> None:
    """Per-seat retry_summary dict has 6 entries (one per seat) with all
    4 retry counters + default_action_fallback_count + turn_timeout_exceeded_count."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="retry_agg_test")
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    rs = meta["retry_summary_per_seat"]
    assert set(rs.keys()) == {"0", "1", "2", "3", "4", "5"}
    for seat_str, summary in rs.items():
        assert "total_turns" in summary
        assert "api_retry_count" in summary
        assert "illegal_action_retry_count" in summary
        assert "no_tool_retry_count" in summary
        assert "tool_usage_error_count" in summary
        assert "default_action_fallback_count" in summary
        assert "turn_timeout_exceeded_count" in summary
        # Random agents never trip any retries.
        assert summary["api_retry_count"] == 0
        assert summary["illegal_action_retry_count"] == 0


def test_meta_tool_usage_summary_aggregated(tmp_path: Path) -> None:
    """tool_usage_summary tracks utility calls per seat (math/equity tools)."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="tool_agg_test")
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    tu = meta["tool_usage_summary"]
    assert set(tu.keys()) == {"0", "1", "2", "3", "4", "5"}
    for seat_str, summary in tu.items():
        assert "total_utility_calls" in summary
        # Random agents never call utility tools.
        assert summary["total_utility_calls"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_session_meta_aggregation.py -v 2>&1 | tail -10`
Expected: FAIL — `total_tokens`, `retry_summary_per_seat`, `tool_usage_summary` are empty dicts (Phase 2a stubs).

- [ ] **Step 3: Add Session-level accumulator state**

Edit `src/llm_poker_arena/session/session.py`. In `Session.__init__`, after the existing `self._chip_pnl = ...` line, add:

```python
        # Phase 4 Task 2: per-seat aggregation for meta.json. Initialized as
        # empty dicts (one entry per seat appears as turns accumulate).
        n = config.num_players
        self._retry_summary_per_seat: dict[int, dict[str, int]] = {
            i: {
                "total_turns": 0,
                "api_retry_count": 0,
                "illegal_action_retry_count": 0,
                "no_tool_retry_count": 0,
                "tool_usage_error_count": 0,
                "default_action_fallback_count": 0,
                "turn_timeout_exceeded_count": 0,
            }
            for i in range(n)
        }
        self._tool_usage_summary: dict[int, dict[str, int]] = {
            i: {"total_utility_calls": 0} for i in range(n)
        }
        self._total_tokens_per_seat: dict[int, dict[str, int]] = {
            i: {
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            }
            for i in range(n)
        }
```

- [ ] **Step 4: Increment counters in `_run_one_hand`**

Edit `src/llm_poker_arena/session/session.py:_run_one_hand`. After the `decision = await self._agents[actor].decide(view)` line and BEFORE the censor check, add accumulator updates:

```python
            # Phase 4 Task 2: per-seat retry/token aggregation for meta.json.
            rs = self._retry_summary_per_seat[actor]
            rs["total_turns"] += 1
            rs["api_retry_count"] += decision.api_retry_count
            rs["illegal_action_retry_count"] += decision.illegal_action_retry_count
            rs["no_tool_retry_count"] += decision.no_tool_retry_count
            rs["tool_usage_error_count"] += decision.tool_usage_error_count
            if decision.default_action_fallback:
                rs["default_action_fallback_count"] += 1
            if decision.turn_timeout_exceeded:
                rs["turn_timeout_exceeded_count"] += 1

            tu = self._tool_usage_summary[actor]
            for ir in decision.iterations:
                if ir.tool_result is not None:
                    tu["total_utility_calls"] += 1

            tt = self._total_tokens_per_seat[actor]
            tt["input_tokens"] += decision.total_tokens.input_tokens
            tt["output_tokens"] += decision.total_tokens.output_tokens
            tt["cache_read_input_tokens"] += decision.total_tokens.cache_read_input_tokens
            tt["cache_creation_input_tokens"] += decision.total_tokens.cache_creation_input_tokens
```

(Place these immediately after the `decision = await self._agents[actor].decide(view)` line, before `if decision.api_error is not None or decision.final_action is None:`.)

- [ ] **Step 5: Pass aggregated dicts to `build_session_meta`**

Edit `src/llm_poker_arena/session/session.py:run`. The `meta = build_session_meta(...)` call should pass the new dicts. Update:

```python
            meta = build_session_meta(
                session_id=self._session_id, config=self._config,
                started_at=started_at_iso, ended_at=ended_at_iso,
                total_hands_played=self._total_hands_played,
                seat_assignment={i: self._agents[i].provider_id()
                                 for i in range(self._config.num_players)},
                initial_button_seat=initial_button_seat,
                chip_pnl=self._chip_pnl,
                session_wall_time_sec=wall_time_sec,
                provider_capabilities=provider_capabilities,
                retry_summary_per_seat=self._retry_summary_per_seat,
                tool_usage_summary=self._tool_usage_summary,
                total_tokens_per_seat=self._total_tokens_per_seat,
            )
```

- [ ] **Step 6: Update `build_session_meta` to accept new kwargs**

Edit `src/llm_poker_arena/storage/meta.py:build_session_meta`. Add three new optional kwargs and write them into the meta dict:

```python
def build_session_meta(
    *,
    session_id: str,
    config: SessionConfig,
    started_at: str,
    ended_at: str,
    total_hands_played: int,
    seat_assignment: dict[int, str],
    initial_button_seat: int,
    chip_pnl: dict[int, int],
    session_wall_time_sec: int,
    provider_capabilities: dict[str, dict[str, Any]] | None = None,
    retry_summary_per_seat: dict[int, dict[str, int]] | None = None,
    tool_usage_summary: dict[int, dict[str, int]] | None = None,
    total_tokens_per_seat: dict[int, dict[str, int]] | None = None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "version": 2,
        "schema_version": "v2.0",
        "started_at": started_at,
        "ended_at": ended_at,
        "total_hands_played": total_hands_played,
        "planned_hands": config.num_hands,
        "git_commit": _git_commit(),
        "prompt_profile_version": "default-v2",
        "provider_capabilities": (provider_capabilities or {}),
        "chip_pnl": {str(s): int(v) for s, v in chip_pnl.items()},
        "retry_summary_per_seat": (
            {str(s): v for s, v in (retry_summary_per_seat or {}).items()}
        ),
        "tool_usage_summary": (
            {str(s): v for s, v in (tool_usage_summary or {}).items()}
        ),
        "censored_hands_count": 0,
        "censored_hand_ids": [],
        "total_tokens": (
            {str(s): v for s, v in (total_tokens_per_seat or {}).items()}
        ),
        "estimated_cost_breakdown": {},
        "session_wall_time_sec": int(session_wall_time_sec),
        "seat_assignment": {str(s): label for s, label in seat_assignment.items()},
        "initial_button_seat": initial_button_seat,
        "seat_permutation_id": "phase2a_default",
    }
```

(Replaces the empty `{}` for retry_summary_per_seat / tool_usage_summary / total_tokens.)

- [ ] **Step 7: Run tests + full suite**

Run: `.venv/bin/pytest tests/unit/test_session_meta_aggregation.py -v 2>&1 | tail -10`
Expected: 3 tests pass.

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 414 pass + 7 skip.

- [ ] **Step 8: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add src/llm_poker_arena/storage/meta.py \
        src/llm_poker_arena/session/session.py \
        tests/unit/test_session_meta_aggregation.py
git commit -m "$(cat <<'EOF'
feat(session): meta.json retry/token aggregation per seat (Phase 4 Task 2)

Closes codex deferred I9 (carried from Phase 3b/3c-math/3c-equity).
spec §7.6 promised retry_summary_per_seat + tool_usage_summary +
total_tokens populated; Phase 2a stub left them as empty dicts.

Session.__init__ initializes 3 per-seat accumulator dicts (one entry
per seat). _run_one_hand increments counters from decision.{api_retry_count,
illegal_action_retry_count, no_tool_retry_count, tool_usage_error_count,
default_action_fallback, turn_timeout_exceeded} and decision.total_tokens.
tool_usage_summary counts iterations with non-None tool_result (matches
build_agent_view_snapshot's total_utility_calls semantics).

build_session_meta accepts the 3 new kwargs and serializes per-seat
dicts with string keys (matches existing chip_pnl + provider_capabilities
JSON convention).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: SessionConfig.max_total_tokens cost cap

**Files:**
- Modify: `src/llm_poker_arena/engine/config.py:SessionConfig` (add `max_total_tokens` field)
- Modify: `src/llm_poker_arena/session/session.py:run` (post-hand cap check + clean abort)
- Modify: `src/llm_poker_arena/storage/meta.py:build_session_meta` (add `stop_reason` kwarg)
- Test: `tests/unit/test_max_total_tokens_cap.py` (NEW)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_max_total_tokens_cap.py`:

```python
"""SessionConfig.max_total_tokens cost cap (Phase 4 Task 3)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _bigfold(uid: str, in_tok: int = 10_000, out_tok: int = 0) -> LLMResponse:
    """A 'fold' response that consumes a lot of tokens (for cap-test setup)."""
    return LLMResponse(
        provider="mock", model="m", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
        text_content="big folding",
        tokens=TokenCounts(input_tokens=in_tok, output_tokens=out_tok,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def test_default_max_total_tokens_is_none() -> None:
    """Backward-compat: no cap by default."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    assert cfg.max_total_tokens is None


def test_cap_none_runs_full_session(tmp_path: Path) -> None:
    """max_total_tokens=None preserves Phase 3 behavior (no abort)."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
        max_total_tokens=None,
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="no_cap")
    asyncio.run(sess.run())
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["total_hands_played"] == 6
    assert meta.get("stop_reason") in (None, "completed")


def test_cap_aborts_after_hand_when_exceeded(tmp_path: Path) -> None:
    """Set a low cap so the LLM seat blows it within first hand. Session
    aborts cleanly at hand boundary; meta.json shows stop_reason."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=12, max_utility_calls=5,  # 12 hands; cap will trip earlier
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
        max_total_tokens=5_000,  # very small; first LLM turn exceeds
    )
    script = MockResponseScript(responses=tuple(
        _bigfold(f"t{i}") for i in range(200)
    ))
    provider = MockLLMProvider(script=script)
    llm = LLMAgent(provider=provider, model="m", temperature=0.7)
    agents = [
        RandomAgent(), llm, RandomAgent(), RandomAgent(),
        RandomAgent(), RandomAgent(),
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="cap_trip")
    asyncio.run(sess.run())
    meta = json.loads((tmp_path / "meta.json").read_text())
    # Aborted before all 12 hands.
    assert meta["total_hands_played"] < 12
    assert meta["stop_reason"] == "max_total_tokens_exceeded"


def test_cap_above_session_total_does_not_abort(tmp_path: Path) -> None:
    """Cap higher than session's actual usage → completes normally."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
        max_total_tokens=10_000_000,  # huge — won't trip
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="cap_unreached")
    asyncio.run(sess.run())
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["total_hands_played"] == 6
    assert meta.get("stop_reason") in (None, "completed")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_max_total_tokens_cap.py -v 2>&1 | tail -10`
Expected: FAIL on first test — `SessionConfig` doesn't have `max_total_tokens` field.

- [ ] **Step 3: Add `max_total_tokens` to SessionConfig**

Edit `src/llm_poker_arena/engine/config.py:SessionConfig`. Add field after `rng_seed`:

```python
class SessionConfig(BaseModel):
    """Top-level session configuration. Immutable after construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    num_players: int = Field(ge=2, le=10)
    starting_stack: int = Field(gt=0)
    sb: int = Field(gt=0)
    bb: int = Field(gt=0)
    num_hands: int = Field(gt=0)
    max_utility_calls: int = Field(ge=0)
    enable_math_tools: bool
    enable_hud_tool: bool
    rationale_required: bool
    opponent_stats_min_samples: int = Field(ge=1)
    rng_seed: int
    # Phase 4: optional session-level token cost cap. None = no cap (backward
    # compat). When set, Session aborts at the next hand boundary if cumulative
    # input+output tokens across all seats exceed this threshold. Tracks raw
    # tokens — USD pricing matrix is Phase 5.
    max_total_tokens: int | None = Field(default=None, gt=0)
```

(`Field(default=None, gt=0)` allows `None` OR a positive int.)

- [ ] **Step 4: Implement Session abort logic**

Edit `src/llm_poker_arena/session/session.py:run`. Replace the entire `run` method body (Task 2 already updated the `build_session_meta(...)` call to add 3 aggregation kwargs; this step adds `stop_reason`):

```python
    async def run(self) -> None:
        started_at_iso = _now_iso()
        started_at_monotonic = time.monotonic()
        initial_button_seat = 0
        provider_capabilities: dict[str, dict[str, Any]] = {}
        # Phase 4 Task 3: track stop reason for meta.json. Defaults to
        # "completed" when the session finishes all configured hands; updated
        # to a sentinel string if cost cap aborts.
        stop_reason = "completed"
        try:
            provider_capabilities = await self._probe_providers()
            for hand_id in range(self._config.num_hands):
                await self._run_one_hand(hand_id)
                self._total_hands_played += 1
                # Cost cap check at hand boundary (clean abort, complete artifacts).
                if self._config.max_total_tokens is not None:
                    total_tokens = sum(
                        seat["input_tokens"] + seat["output_tokens"]
                        for seat in self._total_tokens_per_seat.values()
                    )
                    if total_tokens > self._config.max_total_tokens:
                        stop_reason = "max_total_tokens_exceeded"
                        break
        finally:
            ended_at_iso = _now_iso()
            wall_time_sec = max(0, int(time.monotonic() - started_at_monotonic))
            meta = build_session_meta(
                session_id=self._session_id, config=self._config,
                started_at=started_at_iso, ended_at=ended_at_iso,
                total_hands_played=self._total_hands_played,
                seat_assignment={i: self._agents[i].provider_id()
                                 for i in range(self._config.num_players)},
                initial_button_seat=initial_button_seat,
                chip_pnl=self._chip_pnl,
                session_wall_time_sec=wall_time_sec,
                provider_capabilities=provider_capabilities,
                retry_summary_per_seat=self._retry_summary_per_seat,
                tool_usage_summary=self._tool_usage_summary,
                total_tokens_per_seat=self._total_tokens_per_seat,
                stop_reason=stop_reason,
            )
            (self._output_dir / "meta.json").write_text(
                json.dumps(meta, sort_keys=True, indent=2)
            )
            for w in (self._private_writer, self._public_writer,
                      self._snapshot_writer, self._censor_writer):
                w.close()
```

- [ ] **Step 5: Add `stop_reason` to build_session_meta**

Edit `src/llm_poker_arena/storage/meta.py:build_session_meta`. Task 2 step 6 already added 3 kwargs and 3 dict entries. This step adds one more kwarg + one more entry. Final signature + return dict:

```python
def build_session_meta(
    *,
    session_id: str,
    config: SessionConfig,
    started_at: str,
    ended_at: str,
    total_hands_played: int,
    seat_assignment: dict[int, str],
    initial_button_seat: int,
    chip_pnl: dict[int, int],
    session_wall_time_sec: int,
    provider_capabilities: dict[str, dict[str, Any]] | None = None,
    retry_summary_per_seat: dict[int, dict[str, int]] | None = None,
    tool_usage_summary: dict[int, dict[str, int]] | None = None,
    total_tokens_per_seat: dict[int, dict[str, int]] | None = None,
    stop_reason: str = "completed",
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "version": 2,
        "schema_version": "v2.0",
        "started_at": started_at,
        "ended_at": ended_at,
        "total_hands_played": total_hands_played,
        "planned_hands": config.num_hands,
        "git_commit": _git_commit(),
        "prompt_profile_version": "default-v2",
        "provider_capabilities": (provider_capabilities or {}),
        "chip_pnl": {str(s): int(v) for s, v in chip_pnl.items()},
        "retry_summary_per_seat": (
            {str(s): v for s, v in (retry_summary_per_seat or {}).items()}
        ),
        "tool_usage_summary": (
            {str(s): v for s, v in (tool_usage_summary or {}).items()}
        ),
        "censored_hands_count": 0,
        "censored_hand_ids": [],
        "total_tokens": (
            {str(s): v for s, v in (total_tokens_per_seat or {}).items()}
        ),
        "estimated_cost_breakdown": {},
        "session_wall_time_sec": int(session_wall_time_sec),
        "stop_reason": stop_reason,
        "seat_assignment": {str(s): label for s, label in seat_assignment.items()},
        "initial_button_seat": initial_button_seat,
        "seat_permutation_id": "phase2a_default",
    }
```

`stop_reason` placed near `session_wall_time_sec` (lifecycle/timing cluster).

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_max_total_tokens_cap.py -v 2>&1 | tail -10`
Expected: 4 tests pass.

Run full suite:
`.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 418 pass + 7 skip.

- [ ] **Step 7: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/llm_poker_arena/engine/config.py \
        src/llm_poker_arena/session/session.py \
        src/llm_poker_arena/storage/meta.py \
        tests/unit/test_max_total_tokens_cap.py
git commit -m "$(cat <<'EOF'
feat(session): max_total_tokens cost cap + clean hand-boundary abort (Phase 4 Task 3)

SessionConfig.max_total_tokens (default None = no cap). When set,
Session.run checks cumulative input+output tokens across all seats
after each finished hand. If exceeded, finalize cleanly with
stop_reason="max_total_tokens_exceeded" written into meta.json.

Hand-boundary abort (NOT mid-hand) keeps artifacts complete: every hand
written to JSONL is a finished hand. No mid-hand asyncio cancellation
needed.

Tracks raw tokens, not USD — USD pricing matrix is Phase 5+. User
intuition: max_total_tokens=500_000 ≈ ~$3 at Claude Haiku 4.5 rates.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `poker-play` CLI accepts LLM agents

**Files:**
- Modify: `src/llm_poker_arena/cli/play.py:build_agents` + `main` (argparse + provider construction)
- Test: `tests/unit/test_cli_play_with_llm.py` (NEW)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cli_play_with_llm.py`:

```python
"""poker-play CLI accepts --llm-seat / --llm-provider / --llm-model triplets (Phase 4 Task 4)."""
from __future__ import annotations

import io

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.cli.play import build_agents


def test_build_agents_with_one_llm_seat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Single LLM agent at seat 0 (anthropic), bots elsewhere."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    inp = io.StringIO()
    out = io.StringIO()
    agents = build_agents(
        num_players=6, my_seat=3,
        human_input=inp, human_output=out,
        llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
    )
    assert isinstance(agents[0], LLMAgent)
    # seat 3 is HumanCLI (always); other seats are bots or LLMs.
    from llm_poker_arena.agents.human_cli import HumanCLIAgent
    assert isinstance(agents[3], HumanCLIAgent)


def test_build_agents_with_two_llm_seats(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two LLM agents (Anthropic seat 0 + DeepSeek seat 1), human at seat 3."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    agents = build_agents(
        num_players=6, my_seat=3,
        human_input=io.StringIO(), human_output=io.StringIO(),
        llm_specs=[
            ("anthropic", "claude-haiku-4-5", 0),
            ("deepseek", "deepseek-chat", 1),
        ],
    )
    assert isinstance(agents[0], LLMAgent)
    assert isinstance(agents[1], LLMAgent)
    # seat 0's provider is anthropic; seat 1's is deepseek.
    assert agents[0].provider_id().startswith("anthropic:")
    assert agents[1].provider_id().startswith("deepseek:")


def test_build_agents_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ANTHROPIC_API_KEY when an anthropic LLM seat is requested → fail-fast."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_agents(
            num_players=6, my_seat=3,
            human_input=io.StringIO(), human_output=io.StringIO(),
            llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
        )


def test_build_agents_llm_seat_collides_with_human_seat_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM-seat must not equal human seat."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with pytest.raises(ValueError, match="cannot equal"):
        build_agents(
            num_players=6, my_seat=3,
            human_input=io.StringIO(), human_output=io.StringIO(),
            llm_specs=[("anthropic", "claude-haiku-4-5", 3)],  # seat 3 is human!
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_cli_play_with_llm.py -v 2>&1 | tail -10`
Expected: FAIL — `build_agents` doesn't accept `llm_specs` kwarg.

- [ ] **Step 3: Extend `build_agents` to accept LLM specs**

Edit `src/llm_poker_arena/cli/play.py`. Add new imports near the top of file (place after existing `from typing import TextIO`):

```python
import os
from typing import Any, TextIO  # extend existing TextIO import

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
```

Then replace `build_agents` and add the `_PROVIDER_TABLE` module-level constant before it:

```python
# Provider tag → (env_var_name, factory(model, api_key) -> Provider).
_PROVIDER_TABLE: dict[str, tuple[str, Any]] = {
    "anthropic": (
        "ANTHROPIC_API_KEY",
        lambda model, key: AnthropicProvider(model=model, api_key=key),
    ),
    "openai": (
        "OPENAI_API_KEY",
        lambda model, key: OpenAICompatibleProvider(
            provider_name_value="openai", model=model, api_key=key,
        ),
    ),
    "deepseek": (
        "DEEPSEEK_API_KEY",
        lambda model, key: OpenAICompatibleProvider(
            provider_name_value="deepseek", model=model, api_key=key,
            base_url="https://api.deepseek.com/v1",
        ),
    ),
}


def build_agents(
    *,
    num_players: int,
    my_seat: int,
    human_input: TextIO | None = None,
    human_output: TextIO | None = None,
    llm_specs: list[tuple[str, str, int]] | None = None,
) -> list[Agent]:
    """Construct `num_players` agents: HumanCLIAgent at `my_seat`, LLMAgents at
    seats listed in `llm_specs`, bots elsewhere.

    `llm_specs` is a list of (provider, model, seat) triples. Each `provider`
    must be one of "anthropic" / "openai" / "deepseek". The corresponding
    env var (ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY) MUST be
    set or build_agents raises ValueError.

    Bots fill remaining seats: alternate `RandomAgent` / `RuleBasedAgent`
    by seat parity.
    """
    if not 0 <= my_seat < num_players:
        raise ValueError(
            f"my_seat must be in [0, {num_players}), got {my_seat}"
        )
    llm_specs = llm_specs or []
    llm_seats: dict[int, tuple[str, str]] = {}
    for provider_tag, model, seat in llm_specs:
        if not 0 <= seat < num_players:
            raise ValueError(
                f"--llm-seat {seat} out of range [0, {num_players})"
            )
        if seat == my_seat:
            raise ValueError(
                f"--llm-seat {seat} cannot equal --my-seat {my_seat} "
                f"(human seat is reserved for HumanCLIAgent)"
            )
        if seat in llm_seats:
            raise ValueError(
                f"duplicate --llm-seat {seat}; pass each seat at most once"
            )
        if provider_tag not in _PROVIDER_TABLE:
            raise ValueError(
                f"unknown --llm-provider {provider_tag!r}; "
                f"supported: {sorted(_PROVIDER_TABLE)}"
            )
        env_name, _factory = _PROVIDER_TABLE[provider_tag]
        if not os.environ.get(env_name):
            raise ValueError(
                f"--llm-provider {provider_tag} requires {env_name} env "
                f"var to be set"
            )
        llm_seats[seat] = (provider_tag, model)

    agents: list[Agent] = []
    for i in range(num_players):
        if i == my_seat:
            agents.append(
                HumanCLIAgent(input_stream=human_input, output_stream=human_output)
            )
        elif i in llm_seats:
            provider_tag, model = llm_seats[i]
            env_name, factory = _PROVIDER_TABLE[provider_tag]
            api_key = os.environ[env_name]
            provider = factory(model, api_key)
            agents.append(LLMAgent(
                provider=provider, model=model,
                temperature=0.7,
            ))
        elif i % 2 == 0:
            agents.append(RandomAgent())
        else:
            agents.append(RuleBasedAgent())
    return agents
```

- [ ] **Step 4: Extend argparse + main()**

Update `main` in `src/llm_poker_arena/cli/play.py`:

```python
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="poker-play",
        description=(
            "Play poker against bots and/or LLM agents in the terminal. "
            "Use --llm-seat/--llm-provider/--llm-model in tandem (repeatable) "
            "to mix LLM opponents into the lineup."
        ),
    )
    parser.add_argument("--num-hands", type=int, default=6)
    parser.add_argument("--my-seat", type=int, default=3)
    parser.add_argument("--rng-seed", type=int, default=42)
    parser.add_argument(
        "--output-root", type=Path, default=Path("runs").resolve(),
        help="Where to write session artefacts (default: ./runs/).",
    )
    parser.add_argument(
        "--llm-seat", type=int, action="append", default=[],
        help="Seat to assign an LLM agent. Repeat for multiple LLMs.",
    )
    parser.add_argument(
        "--llm-provider", action="append", default=[],
        choices=["anthropic", "openai", "deepseek"],
        help="Provider for the corresponding --llm-seat (must repeat in tandem).",
    )
    parser.add_argument(
        "--llm-model", action="append", default=[],
        help="Model name for the corresponding --llm-seat "
             "(e.g. claude-haiku-4-5, deepseek-chat).",
    )
    args = parser.parse_args(argv)

    if not (len(args.llm_seat) == len(args.llm_provider) == len(args.llm_model)):
        parser.error(
            "--llm-seat, --llm-provider, --llm-model must be repeated the "
            f"same number of times (got {len(args.llm_seat)} / "
            f"{len(args.llm_provider)} / {len(args.llm_model)})"
        )

    llm_specs = list(zip(args.llm_provider, args.llm_model, args.llm_seat,
                         strict=True))

    args.output_root.mkdir(parents=True, exist_ok=True)
    return run_cli(
        num_hands=args.num_hands,
        my_seat=args.my_seat,
        rng_seed=args.rng_seed,
        output_root=args.output_root,
        llm_specs=llm_specs,
    )
```

Update `run_cli` to accept and forward `llm_specs`. Replace the entire function (the body after `agents = ...` is unchanged from current play.py:115-129; reproduced here for completeness):

```python
def run_cli(
    *,
    num_hands: int,
    my_seat: int,
    rng_seed: int,
    output_root: Path,
    human_input: TextIO | None = None,
    human_output: TextIO | None = None,
    llm_specs: list[tuple[str, str, int]] | None = None,
) -> int:
    """Programmatic entry point; returns shell-style return code."""
    out_stream = human_output if human_output is not None else sys.stdout
    if num_hands % 6 != 0:
        # SessionConfig requires num_hands % num_players == 0; round UP to 6x.
        num_hands = ((num_hands + 5) // 6) * 6
        out_stream.write(
            f"[poker-play] num_hands rounded up to {num_hands} "
            f"(must be multiple of num_players=6)\n"
        )

    # Phase 4: enable_math_tools auto-True if any LLM seat is configured.
    has_llm = bool(llm_specs)
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=has_llm,
        enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )
    agents = build_agents(
        num_players=6, my_seat=my_seat,
        human_input=human_input, human_output=human_output,
        llm_specs=llm_specs,
    )

    session_dir = output_root / _session_dir_name(rng_seed=rng_seed)
    if session_dir.exists():
        out_stream.write(
            f"[poker-play] session directory {session_dir} already exists; "
            f"aborting to avoid appending to stale artifacts\n"
        )
        return 1
    sess = Session(
        config=cfg, agents=agents, output_dir=session_dir,
        session_id=session_dir.name,
    )
    asyncio.run(sess.run())

    _print_session_summary(session_dir, my_seat=my_seat, output_stream=out_stream)
    return 0
```

- [ ] **Step 5: Run tests + suite**

Run: `.venv/bin/pytest tests/unit/test_cli_play_with_llm.py -v 2>&1 | tail -8`
Expected: 4 tests pass.

Run full suite:
`.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 422 pass + 7 skip.

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/cli/play.py tests/unit/test_cli_play_with_llm.py && .venv/bin/mypy --strict src/llm_poker_arena/cli/play.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/cli/play.py tests/unit/test_cli_play_with_llm.py
git commit -m "$(cat <<'EOF'
feat(cli): poker-play accepts --llm-seat/--llm-provider/--llm-model (Phase 4 Task 4)

argparse `action='append'` for the LLM triplet, repeatable for multiple
LLM seats. _PROVIDER_TABLE maps anthropic/openai/deepseek to
(env_var_name, factory) pairs reusing Phase 3b providers
(AnthropicProvider, OpenAICompatibleProvider with base_url=None for
OpenAI canonical and https://api.deepseek.com/v1 for DeepSeek).

API keys via env vars only — refuse to start if --llm-seat set without
the corresponding env var. Validates --llm-seat doesn't collide with
--my-seat (human seat).

When any LLM seat is configured, enable_math_tools auto-True (so utility
tools are available — pot_odds/spr/equity from 3c-math + 3c-equity).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: USAGE.md docs

**Files:**
- Create: `USAGE.md` (project root)

- [ ] **Step 1: Create the file**

Create `USAGE.md`:

```markdown
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
```

- [ ] **Step 2: Verify rendering**

Run: `head -40 USAGE.md`
Expected: clean markdown, no syntax errors visible.

(Optionally render via `pandoc USAGE.md -o /tmp/usage.html` if pandoc available, but not required.)

- [ ] **Step 3: Commit**

```bash
git add USAGE.md
git commit -m "$(cat <<'EOF'
docs: USAGE.md — quick start + agent catalog + log structure (Phase 4 Task 5)

~150 lines covering: install + first session, adding LLM opponents,
multi-LLM CLI, agent type catalog (6 types), cost guard, log file
structure (3-layer JSONL), troubleshooting common issues, SessionConfig
knobs reference, one-paragraph architecture overview.

Pivots project from "research artifact" to "usable competition platform"
per user direction. Future contributors / external users now have a
5-minute on-ramp without reading the v2 spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Mock human + LLM CLI integration test

**Files:**
- Create: `tests/integration/test_human_vs_llm_mock.py`

- [ ] **Step 1: Write the test**

Create `tests/integration/test_human_vs_llm_mock.py`:

```python
"""Full CLI session with HumanCLIAgent + mock LLM agents (Phase 4 Task 6).

Verifies the end-to-end wire: CLI argparse → build_agents (LLM specs) →
Session.run → meta.json + JSONL artifacts. Uses MockLLMProvider so no
real API calls.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from llm_poker_arena.cli.play import run_cli


def test_human_plus_anthropic_mock_session_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 human (scripted stdin) + 1 mock anthropic + 4 bots; 6 hands; clean."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-mock")

    # Monkeypatch AnthropicProvider to be MockLLMProvider so we don't actually
    # call the API. The factory in build_agents instantiates AnthropicProvider —
    # we replace that class with a stub that returns a MockLLMProvider-backed
    # LLMResponse.
    from llm_poker_arena.agents.llm.providers.mock import (
        MockLLMProvider,
        MockResponseScript,
    )
    from llm_poker_arena.agents.llm.types import (
        AssistantTurn,
        LLMResponse,
        TokenCounts,
        ToolCall,
    )

    def _fold(uid: str) -> LLMResponse:
        return LLMResponse(
            provider="anthropic", model="claude-haiku-4-5",
            stop_reason="tool_use",
            tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
            text_content="folding",
            tokens=TokenCounts(input_tokens=50, output_tokens=10,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="anthropic", blocks=()),
        )

    script = MockResponseScript(responses=tuple(
        _fold(f"t{i}") for i in range(200)
    ))

    # Patch AnthropicProvider class within the cli.play module's _PROVIDER_TABLE.
    # The override MUST also have `provider_name() == "anthropic"` so that
    # LLMAgent.provider_id() emits "anthropic:claude-haiku-4-5" (matches
    # what real anthropic flow would produce; persisted to meta.json
    # seat_assignment).
    from llm_poker_arena.cli import play as play_mod

    class _MockAnthropic(MockLLMProvider):
        def __init__(self, *, model: str, api_key: str) -> None:
            super().__init__(script=script)

        def provider_name(self) -> str:
            return "anthropic"

    monkeypatch.setitem(
        play_mod._PROVIDER_TABLE, "anthropic",
        ("ANTHROPIC_API_KEY",
         lambda model, key: _MockAnthropic(model=model, api_key=key)),
    )

    # Cyclic stdin so human always has SOME legal action to pick.
    human_input = io.StringIO("call\ncheck\nfold\nall_in\n" * 100)
    human_output = io.StringIO()

    rc = run_cli(
        num_hands=6, my_seat=3, rng_seed=42,
        output_root=tmp_path,
        human_input=human_input, human_output=human_output,
        llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
    )
    assert rc == 0

    session_dirs = list(tmp_path.glob("session_*"))
    assert len(session_dirs) == 1
    sd = session_dirs[0]
    meta = json.loads((sd / "meta.json").read_text())
    assert meta["total_hands_played"] == 6
    # seat 0 is mock-LLM with "anthropic" provider tag.
    assert meta["seat_assignment"]["0"] == "anthropic:claude-haiku-4-5"
    # seat 3 is human.
    assert meta["seat_assignment"]["3"] == "human:cli_v1"
    # Token aggregation populated for the LLM seat.
    assert meta["total_tokens"]["0"]["input_tokens"] > 0
    # chip P&L conservation.
    assert sum(meta["chip_pnl"].values()) == 0
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_human_vs_llm_mock.py -v 2>&1 | tail -8`
Expected: PASS.

- [ ] **Step 3: Lint**

Run: `.venv/bin/ruff check tests/integration/test_human_vs_llm_mock.py`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_human_vs_llm_mock.py
git commit -m "$(cat <<'EOF'
test(integration): full CLI session with HumanCLI + mock LLM (Phase 4 Task 6)

End-to-end verification: argparse → build_agents (LLM specs) →
Session.run → meta.json + JSONL artifacts. MockLLMProvider replaces
the real Anthropic SDK via monkeypatch on _PROVIDER_TABLE — no API
calls.

Asserts:
  - run_cli returns 0
  - meta.json.seat_assignment shows seat 0 = anthropic, seat 3 = human
  - meta.json.total_tokens populated for LLM seat (Phase 4 Task 2)
  - chip_pnl conserves

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Gated real human + Claude live test

**Files:**
- Create: `tests/integration/test_human_vs_llm_real_anthropic.py`

**Activation:**
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_human_vs_llm_real_anthropic.py -v
```

Cost: ~$0.01 per run (6 hands, 1 LLM seat with 6 random fillers).

- [ ] **Step 1: Create the gated test**

Create `tests/integration/test_human_vs_llm_real_anthropic.py`:

```python
"""Real Anthropic + scripted human via CLI (gated, NOT in CI).

Run only when:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Verifies the human-vs-LLM CLI path end-to-end on the real Anthropic API.
Cost ~$0.01 (6 hands, 1 Claude Haiku 4.5 seat).

Wire-only assertions (mirror Phase 3 gated patterns):
  - run_cli returns 0
  - meta.json.seat_assignment / total_tokens populated
  - chip_pnl conserves
  - all final_actions in legal set (per snapshot)
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

from llm_poker_arena.cli.play import run_cli

pytestmark = pytest.mark.skipif(
    os.getenv("ANTHROPIC_INTEGRATION_TEST") != "1"
    or not os.getenv("ANTHROPIC_API_KEY"),
    reason="needs ANTHROPIC_INTEGRATION_TEST=1 and ANTHROPIC_API_KEY set",
)


def test_human_plus_real_claude_session_completes(tmp_path: Path) -> None:
    """Scripted stdin so test runs unattended (no real human at keyboard)."""
    # Cyclic stdin: alternating call/check/fold/all_in covers every legal set.
    human_input = io.StringIO("call\ncheck\nfold\nall_in\n" * 100)
    human_output = io.StringIO()

    rc = run_cli(
        num_hands=6, my_seat=3, rng_seed=42,
        output_root=tmp_path,
        human_input=human_input, human_output=human_output,
        llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
    )
    assert rc == 0

    session_dirs = list(tmp_path.glob("session_*"))
    assert len(session_dirs) == 1
    sd = session_dirs[0]

    # meta.json basics.
    meta = json.loads((sd / "meta.json").read_text())
    assert meta["total_hands_played"] == 6
    assert meta["seat_assignment"]["0"] == "anthropic:claude-haiku-4-5"
    assert meta["seat_assignment"]["3"] == "human:cli_v1"
    assert meta["total_tokens"]["0"]["input_tokens"] > 0
    assert sum(meta["chip_pnl"].values()) == 0

    # Every snapshot's final_action is in its legal set.
    snaps = (sd / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    for line in snaps:
        rec = json.loads(line)
        legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
        assert rec["final_action"]["type"] in legal_names, (
            f"seat {rec['seat']} {rec['turn_id']} final {rec['final_action']!r} "
            f"not in legal {legal_names}"
        )
```

- [ ] **Step 2: Verify gate-skipped run still passes**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 423 pass + 8 skip (the new gated joins existing 7).

- [ ] **Step 3: Live verify against real Anthropic API**

Run:
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_human_vs_llm_real_anthropic.py -v --basetemp=/tmp/human_vs_claude_smoke 2>&1 | tail -10
```

Expected: PASS in 30-90s, ~$0.01 cost. Inspect `/tmp/human_vs_claude_smoke/.../agent_view_snapshots.jsonl` to see Claude's actual decisions in the human-mixed session.

- [ ] **Step 4: Lint**

Run: `.venv/bin/ruff check tests/integration/test_human_vs_llm_real_anthropic.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_human_vs_llm_real_anthropic.py
git commit -m "$(cat <<'EOF'
test(integration): gated real human + Claude CLI live test (Phase 4 Task 7)

Mirrors Phase 3 gated pattern. Scripted stdin so the test runs unattended
(no actual human at keyboard) but exercises the same code path a real
human session would. 6 hands with Claude Haiku 4.5 at seat 0 + scripted
human at seat 3 + 4 bots.

Wire-only assertions (codex IMPORTANT-5 style): rc=0, meta.json
populated, chip_pnl conserves, all final_actions in legal sets.

Cost ~$0.01 / run. Verified manually pre-commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Lint sweep + ruff format drift cleanup + memory update

**Files:**
- Touch any source file flagged by final ruff/mypy
- (Optional) Apply `ruff format` to ~24 pre-Phase-3 files with format drift
- Update `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`

- [ ] **Step 1: Final ruff check**

Run: `.venv/bin/ruff check src/ tests/`
Expected: clean. Fix any inline.

- [ ] **Step 2: Final mypy strict**

Run: `.venv/bin/mypy --strict src/ tests/`
Expected: clean.

- [ ] **Step 3: Optional — clean ruff format drift**

Run: `.venv/bin/ruff format --check src/ tests/`

If drift is reported (~24 files per Phase 1 memory note), apply:

```bash
.venv/bin/ruff format src/ tests/
.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3
```

If suite stays green after format, commit as a separate housekeeping commit:

```bash
git add -u
git commit -m "$(cat <<'EOF'
chore: ruff format pre-Phase-3 drift cleanup (Phase 4 Task 8)

Pre-existing format drift on ~24 files predates Phase 2a (memory note
from Phase 1). Phase 3+ files were always formatted. Bulk apply ruff
format now for consistency. Zero behavior change; suite stays green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If drift is large or suite breaks, skip and note in commit.

- [ ] **Step 4: Final all-gates run**

Run:
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 DEEPSEEK_INTEGRATION_TEST=1 \
  .venv/bin/pytest tests/ 2>&1 | tail -5
```

Expected: 431 pass + 0 skip (423 non-gated + 8 gated: 7 prior + 1 new human-vs-Claude).

- [ ] **Step 5: Update memory**

Read `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`. Insert a new "Phase 4 COMPLETE" block following the existing pattern. Update `description` field to reflect Phase 4 completion. Capture key non-obvious learnings (e.g., "Agent.metadata() default-None pattern preserves backward compat without modifying 3 non-LLM agents", "Cost cap at hand boundary keeps artifacts complete", etc.).

Update `~/.claude/projects/-Users-zcheng256/memory/MEMORY.md` index entry's one-liner if it changed.

- [ ] **Step 6: Final inventory**

Run: `git log --oneline 1f42954..HEAD && git status`

Expected: clean tree, ~9 commits since Phase 3c-equity (1 plan baseline + 8 task commits, possibly +1 ruff format commit).

---

## Self-Review Checklist (auditor-facing summary)

After all 9 tasks land:

1. **Codex deferred backlog closed:**
   - I8 AgentDescriptor.temperature/seed ✅ Task 1
   - I9 meta.json retry/token aggregation ✅ Task 2
2. **Platform usability:**
   - Cost cap (max_total_tokens) ✅ Task 3
   - CLI accepts LLM agents (3 providers) ✅ Task 4
   - USAGE.md docs ✅ Task 5
   - Mock + gated end-to-end tests ✅ Tasks 6, 7
3. **Cleanup:**
   - HumanCLIAgent docstring ✅ Task 0
   - Optional ruff format drift cleanup ✅ Task 8 step 3
4. **Spec coverage:**
   - §7.4 AgentDescriptor.temperature/seed populated ✅
   - §7.6 retry_summary_per_seat / tool_usage_summary / total_tokens populated ✅
5. **Backward compat preserved:**
   - Agent.metadata() defaults to None — Random/RuleBased/HumanCLI unchanged ✅
   - SessionConfig.max_total_tokens defaults to None — existing sessions unchanged ✅
   - poker-play CLI without --llm-* args behaves identically to Phase 3 ✅
   - Existing 405 tests + 7 skip still pass; 19 new tests added (6+3+4+4+0+1+0 + 1 gated) ✅
6. **No placeholders:** every step has executable code or commands.
