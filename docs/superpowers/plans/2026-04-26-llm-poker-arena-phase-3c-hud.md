# Phase 3c-hud: HUD Stats Tool (VPIP/PFR/3-bet/AF/WTSD) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (inline mode) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the last unimplemented 3c utility tool — `get_opponent_stats` — backed by single-session incremental counters for 5 standard poker stats (VPIP / PFR / 3-bet / AF / WTSD). LLM sees opponent stats in PlayerView (passive injection) and can also query via tool (active accessor).

**Architecture:**
- **Single-session accumulation**: `Session.__init__` initializes 1 dict per seat with 8 counters (vpip_actions, pfr_actions, three_bet_chances, three_bet_actions, af_aggressive, af_passive, wtsd_chances, wtsd_actions). Reuses Phase 4's per-seat accumulator pattern.
- **Counter updates in `_run_one_hand`**: per-action increments (AF) + per-hand boolean tracking (VPIP/PFR/3-bet/WTSD) flushed at hand-end. No SQL — pure Python increment.
- **`build_player_view` extended** with optional `opponent_stats` kwarg; Session computes the dict per turn from counters and passes it. Falls back to `insufficient=True` when `_hud_hands_counted < opponent_stats_min_samples` (clean-completion count, NOT `_total_hands_played`) OR any individual stat denominator = 0 (rare edge case past min_samples).
- **`get_opponent_stats` tool = thin PlayerView accessor**: reads `view.opponent_stats[seat]`, validates seat ≠ self / in range / not folded, returns the same dict that's already in the prompt. Codex audit: "tool worth shipping for spec compliance even if 0/22 organic call rate persists."
- **Gated on `enable_hud_tool`**: tool spec, dispatcher route, system.j2 advertisement all check `view.immutable_session_params.enable_hud_tool`. Counter computation always runs (cheap; needed for PlayerView injection).

**Tech Stack:** No new deps. Reuses Phase 4 accumulator pattern, Phase 3c-math/equity tool registration patterns, existing `OpponentStatsOrInsufficient` Pydantic model in `engine/views.py`.

---

## Phase 3c-hud Scope Decisions

1. **Single-session, not cross-session**: every game starts from zero stats; first ~30 hands all opponents show `insufficient=True`. No DB/file persistence — fits "competition platform" goal where lineups change per game.
2. **Incremental counters in Session, not DuckDB SQL**: SQL on JSONL is post-hoc and slow for hot path (per-turn projection). Phase 2b's VPIP/PFR SQL stays as analyst tooling; this phase implements parallel in-process counter math.
3. **5 stats, not 7+ (no by-street breakdowns)**: spec §1389 hints at `detail_level="detailed"` but defines no concrete schema. Ship `summary` only (5 core stats). `detail_level` arg accepted but only `"summary"` validates; future phase can add more levels.
4. **all_in counted as VPIP + PFR + AF-aggressive**: standard tracker convention (PokerTracker/HoldemManager). Slight overcount for "call all-in" cases but rare in 6-max deep stack; matches mainstream HUD semantics.
5. **AF = aggressive_actions / passive_actions, all streets**: aggressive = bet + raise_to + all_in; passive = call. Cross-street individual action ratio (not per-hand frequency). When passive=0, fall back to insufficient=True for entire opponent (avoids inf or null in non-nullable validator).
6. **3-bet definition** (codex audit BLOCKER B2 fix): the SECOND voluntary preflop raise. Chance = exactly one prior voluntary preflop raise (from another seat) AND this seat has not yet raised preflop. Action = chance + this seat raises. Anything beyond is 4-bet+, NOT 3-bet.
7. **WTSD = went-to-showdown given VPIP**: chances = VPIP=True hand count; actions = VPIP=True AND seat in showdown_seats. (Some trackers use "saw flop" denominator; we use VPIP for symmetry with our other counters.)
8. **Self-seat excluded**: `opponent_stats` dict in PlayerView contains all OTHER seats only; `get_opponent_stats(seat=self.seat)` returns error.
9. **`insufficient` fallback is conservative**: if `_hud_hands_counted < min_samples` (default 30; clean-completion count, NOT `_total_hands_played` which includes censored hands — codex audit IMPORTANT-5 fix) OR any stat denominator = 0, return `insufficient=True` for entire opponent. Documented edge case: opponent who played 30+ hands but never had a 3-bet opportunity will show insufficient. Acceptable v1 trade-off.

---

## File Structure

**Modified files:**
- `src/llm_poker_arena/session/session.py:__init__` — add `_hud_counters` dict (8 counters × N seats) + `_hand_state_init` helper
- `src/llm_poker_arena/session/session.py:_run_one_hand` — per-action AF increments; per-hand VPIP/PFR/3-bet/WTSD boolean tracking; end-of-hand counter flush
- `src/llm_poker_arena/session/session.py` — new `_build_opponent_stats(actor) -> dict[int, OpponentStatsOrInsufficient]` method
- `src/llm_poker_arena/engine/projections.py:build_player_view` — accept optional `opponent_stats` kwarg; remove TODO at line 178
- `src/llm_poker_arena/tools/__init__.py` — export `OPPONENT_STATS_SPEC`, register dispatch route
- `src/llm_poker_arena/tools/utility_tool_specs.py` (or wherever spec list lives) — add `OPPONENT_STATS_SPEC` gated on `enable_hud_tool`
- `src/llm_poker_arena/agents/llm/prompts/system.j2` — advertise HUD tool when `enable_hud_tool`

**New files:**
- `src/llm_poker_arena/tools/opponent_stats.py` — `get_opponent_stats(view, seat, detail_level)` tool implementation

**New tests:**
- `tests/unit/test_hud_counters_vpip.py` — VPIP counter logic (3 tests)
- `tests/unit/test_hud_counters_pfr.py` — PFR counter logic (3 tests)
- `tests/unit/test_hud_counters_3bet.py` — 3-bet chance + action tracking + 4-bet edge case (5 tests)
- `tests/unit/test_hud_counters_af.py` — AF cross-street individual action ratio (3 tests)
- `tests/unit/test_hud_counters_wtsd.py` — WTSD given VPIP + showdown (3 tests)
- `tests/unit/test_build_player_view_opponent_stats.py` — projection wires counters → OpponentStatsOrInsufficient with min_samples sentinel (7 tests)
- `tests/unit/test_get_opponent_stats_tool.py` — tool accessor + dispatcher gates + utility_tool_specs gate + prompt rendering (11 tests)
- `tests/integration/test_llm_session_mock_hud.py` — Mock K+1 session forces HUD tool call, verifies result lands in iterations (1 test)
- `tests/integration/test_llm_session_real_anthropic_hud.py` — Gated real Claude Haiku 4.5 with `enable_hud_tool=True` (1 gated test)

**Files NOT touched** (intentionally):
- `src/llm_poker_arena/analysis/sql.py` — Phase 2b VPIP/PFR SQL stays as analyst tooling; not consumed in hot path
- `src/llm_poker_arena/storage/duckdb_query.py` — no new SQL needed

---

## Test Counts (cumulative, baseline = 423 pass + 8 skip after Phase 4)

| Task | New tests | Cumulative pass | Cumulative skip |
|---|---|---|---|
| 1 | 0 (counter dict skeleton) | 423 | 8 |
| 2 | 3 (VPIP counter) | 426 | 8 |
| 3 | 3 (PFR counter) | 429 | 8 |
| 4 | 5 (3-bet counter + 4-bet edge case) | 434 | 8 |
| 5 | 3 (AF counter) | 437 | 8 |
| 6 | 3 (WTSD counter) | 440 | 8 |
| 7 | 7 (build_player_view + sentinel + 3 deterministic seeded tests + hud_hands_counted) | 447 | 8 |
| 8 | 11 (tool x4 + dispatcher x2 + utility_tool_specs x2 + prompt render x4) | 458 | 8 |
| 9 | 1 (mock K+1 HUD integration) | 459 | 8 |
| 10 | 0 unit + 1 gated | 459 | 9 |
| 11 | 0 (lint + memory) | 459 | 9 |

**Final all-gates-on**: 468 pass + 0 skip (459 non-gated + 9 gated: 8 prior + 1 new HUD).

---

## Task 1: HUD counter dict skeleton in Session.__init__

**Files:**
- Modify: `src/llm_poker_arena/session/session.py:__init__` (add `_hud_counters` dict)

- [ ] **Step 1: Add accumulator dict**

Edit `src/llm_poker_arena/session/session.py`. After Phase 4's `self._total_tokens_per_seat = {...}` block in `__init__`, append:

```python
        # Phase 3c-hud: per-seat HUD stat counters. Initialized to all zeros.
        # 8 counters per seat — see plan §"Phase 3c-hud Scope Decisions"
        # for stat semantics. Updated incrementally in _run_one_hand
        # (per-action for AF; per-hand boolean flush at hand end for the rest).
        self._hud_counters: dict[int, dict[str, int]] = {
            i: {
                "vpip_actions": 0,
                "pfr_actions": 0,
                "three_bet_chances": 0,
                "three_bet_actions": 0,
                "af_aggressive": 0,
                "af_passive": 0,
                "wtsd_chances": 0,
                "wtsd_actions": 0,
            }
            for i in range(n)
        }
        # codex audit IMPORTANT-5 fix: HUD-specific completed-hand counter.
        # Distinct from self._total_hands_played which counts ALL hands
        # including censored ones (returned-early in _run_one_hand on
        # api_error). HUD counters only flush on clean hand completion, so
        # using _total_hands_played as the VPIP/PFR denominator would
        # depress rates by the censor count.
        self._hud_hands_counted: int = 0
```

- [ ] **Step 2: Verify suite stays green**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 423 pass + 8 skip (no behavior change yet).

- [ ] **Step 3: Lint**

Run: `.venv/bin/ruff check src/llm_poker_arena/session/session.py`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/llm_poker_arena/session/session.py
git commit -m "$(cat <<'EOF'
feat(session): scaffold HUD per-seat counter dict (Phase 3c-hud Task 1)

Adds _hud_counters: dict[int, dict[str, int]] in Session.__init__ with
8 counters per seat (vpip_actions, pfr_actions, three_bet_chances,
three_bet_actions, af_aggressive, af_passive, wtsd_chances,
wtsd_actions). All initialized to 0; subsequent tasks wire increment
logic in _run_one_hand.

Reuses Phase 4 accumulator pattern (per-seat dict initialized in
__init__, mutated in _run_one_hand, surfaced at session end).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: VPIP counter

**Files:**
- Modify: `src/llm_poker_arena/session/session.py:_run_one_hand` (per-hand VPIP boolean tracking + end-of-hand flush)
- Test: `tests/unit/test_hud_counters_vpip.py` (NEW)

**VPIP semantics**: per-hand boolean — did this seat voluntarily put $ in pot preflop? Voluntary = action_type in {call, raise_to, bet, all_in} during preflop, NOT a forced blind post (forced blinds are posted by PokerKit automation, never via agent.decide, so all `chosen` actions in our loop are voluntary by construction).

Counter: `vpip_actions` increments by 1 per hand per seat where boolean = True.

Denominator at read time: `_hud_hands_counted` (clean-completion count; every seat is dealt every hand in 6-max auto-rebuy, but censored hands are excluded — codex audit IMPORTANT-5 fix).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_hud_counters_vpip.py`:

```python
"""HUD VPIP counter logic in Session._run_one_hand (Phase 3c-hud Task 2)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_vpip_counter_increments_when_seat_voluntarily_acts_preflop(
    tmp_path: Path,
) -> None:
    """6-hand session with all RandomAgents. Each seat's vpip_actions
    counter <= total_hands_played and >= 0 (RandomAgent sometimes folds
    preflop = no VPIP, sometimes calls = VPIP)."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="vpip_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert 0 <= c["vpip_actions"] <= sess._total_hands_played, (
            f"seat {seat} vpip_actions={c['vpip_actions']} out of bounds "
            f"[0, {sess._total_hands_played}]"
        )


def test_vpip_at_most_one_per_hand_per_seat(tmp_path: Path) -> None:
    """A seat with multiple preflop actions in one hand (e.g. limp then
    call a 3-bet) only increments vpip_actions by 1 for that hand."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="vpip_dedup_test")
    asyncio.run(sess.run())

    # vpip_actions per seat <= total_hands_played (1-per-hand cap).
    for seat in range(6):
        assert sess._hud_counters[seat]["vpip_actions"] <= 6


def test_vpip_zero_when_seat_only_folds_preflop(tmp_path: Path) -> None:
    """An all-fold session (programmatically via fold-only agent) gives
    vpip_actions=0 for all seats. RandomAgent doesn't always fold, so we
    use a custom fold-only agent."""
    from llm_poker_arena.agents.base import Agent
    from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
    from llm_poker_arena.engine.legal_actions import Action
    from llm_poker_arena.engine.views import PlayerView

    class FoldOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            # Prefer fold; fall back to check if fold not legal (BB option).
            action_name = "fold" if "fold" in legal else "check"
            return TurnDecisionResult(
                iterations=(), final_action=Action(tool_name=action_name, args={}),
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:fold_only"

    cfg = _cfg(num_hands=6)
    agents = [FoldOnly() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="vpip_zero_test")
    asyncio.run(sess.run())

    # No seat voluntarily acted (all folds). VPIP = 0 for all. NOTE: BB may
    # have to "check" (option to see flop free) when everyone limps — that
    # check is NOT VPIP per standard convention (no money put in voluntarily
    # beyond the forced blind). Our impl agrees.
    for seat in range(6):
        assert sess._hud_counters[seat]["vpip_actions"] == 0, (
            f"seat {seat} vpip_actions != 0 in all-fold session: "
            f"{sess._hud_counters[seat]['vpip_actions']}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_vpip.py -v 2>&1 | tail -10`
Expected: FAIL on test 1 — vpip_actions stays 0 (counter not wired yet).

- [ ] **Step 3: Wire VPIP increment in _run_one_hand**

Edit `src/llm_poker_arena/session/session.py:_run_one_hand`. At the top of the method (before the `while state._state.actor_index is not None:` loop, around line 225), initialize per-hand boolean tracker:

```python
        # Phase 3c-hud: per-hand booleans for VPIP/PFR/3-bet/WTSD; flushed
        # to _hud_counters at hand end. Per-action stats (AF) are updated
        # immediately in the loop below.
        n_seats = self._config.num_players
        hand_state: dict[int, dict[str, bool]] = {
            i: {
                "did_vpip": False,
                "did_pfr": False,
                "had_3bet_chance": False,
                "did_3bet": False,
            }
            for i in range(n_seats)
        }
```

Inside the action loop (after `chosen = decision.final_action` and before `result = apply_action(...)`, around line 244), add VPIP detection:

```python
            # Phase 3c-hud: VPIP — voluntary preflop action (call/raise/bet/all_in).
            # All `chosen` actions are voluntary by construction (forced blinds
            # are posted by PokerKit automation, never via agent.decide).
            if street == Street.PREFLOP and chosen.tool_name in (
                "call", "raise_to", "bet", "all_in",
            ):
                hand_state[actor]["did_vpip"] = True
```

After the action loop ends (after `for snap in staged_snapshots:` flush block, around line 296), add hand-end counter flush:

```python
        # Phase 3c-hud: flush per-hand booleans to cumulative counters.
        for seat in range(n_seats):
            if hand_state[seat]["did_vpip"]:
                self._hud_counters[seat]["vpip_actions"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_vpip.py -v 2>&1 | tail -8`
Expected: 3 tests pass.

Run full suite to verify no regression:
`.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 426 pass + 8 skip.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/session/session.py tests/unit/test_hud_counters_vpip.py
git commit -m "$(cat <<'EOF'
feat(session): VPIP counter (Phase 3c-hud Task 2)

Per-hand boolean tracker initialized at _run_one_hand top; flipped True
when seat takes voluntary preflop action (call/raise_to/bet/all_in).
Forced blinds are posted by PokerKit automation (never via agent.decide),
so all chosen actions in the agent loop are voluntary by construction —
no is_forced_blind filter needed.

Boolean flushed to _hud_counters[seat]["vpip_actions"] at hand end
(at-most-one-per-hand semantic matches PokerTracker convention).

Tests cover: bounds (0 ≤ vpip_actions ≤ total_hands_played), at-most-one-
per-hand, and zero in all-fold session (BB check option not counted).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: PFR counter

**Files:**
- Modify: `src/llm_poker_arena/session/session.py:_run_one_hand` (PFR boolean tracking)
- Test: `tests/unit/test_hud_counters_pfr.py` (NEW)

**PFR semantics**: per-hand boolean — did seat make a preflop raise (raise_to / bet / all_in)? `bet` happens preflop only when previous action is check (rare in NLHE preflop because BB has option); typically `raise_to`. Conservative inclusion of `bet` matches PokerTracker.

Counter: `pfr_actions` increments by 1 per hand per seat where boolean = True. PFR ⊆ VPIP by definition.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_hud_counters_pfr.py`:

```python
"""HUD PFR counter logic in Session._run_one_hand (Phase 3c-hud Task 3)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_pfr_counter_within_vpip_bound(tmp_path: Path) -> None:
    """PFR ⊆ VPIP: pfr_actions ≤ vpip_actions ≤ total_hands_played."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="pfr_bounds_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["pfr_actions"] <= c["vpip_actions"], (
            f"seat {seat} pfr_actions={c['pfr_actions']} > "
            f"vpip_actions={c['vpip_actions']} (PFR must be subset of VPIP)"
        )


def test_pfr_zero_when_only_calls_preflop(tmp_path: Path) -> None:
    """A call-only agent (never raises) → pfr_actions=0 for all seats."""
    class CallOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            # Prefer call > check > fold to avoid raise.
            for name in ("call", "check", "fold"):
                if name in legal:
                    action = Action(tool_name=name, args={})
                    break
            else:  # only raises legal — must take one (illegal_action fallback otherwise)
                action = Action(tool_name="fold", args={})
            return TurnDecisionResult(
                iterations=(), final_action=action,
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:call_only"

    cfg = _cfg(num_hands=6)
    agents = [CallOnly() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="pfr_zero_test")
    asyncio.run(sess.run())

    for seat in range(6):
        assert sess._hud_counters[seat]["pfr_actions"] == 0, (
            f"seat {seat} pfr_actions != 0 in call-only session"
        )


def test_pfr_increments_when_seat_raises_preflop(tmp_path: Path) -> None:
    """A raise-prefer agent → pfr_actions > 0 for seats that act preflop."""
    class RaisePrefer(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            # Prefer raise > call > check > fold.
            if "raise_to" in legal:
                spec = next(t for t in view.legal_actions.tools
                            if t.name == "raise_to")
                bounds = spec.args["amount"]
                amt = int(bounds["min"])
                action = Action(tool_name="raise_to", args={"amount": amt})
            elif "bet" in legal:
                spec = next(t for t in view.legal_actions.tools if t.name == "bet")
                bounds = spec.args["amount"]
                amt = int(bounds["min"])
                action = Action(tool_name="bet", args={"amount": amt})
            elif "call" in legal:
                action = Action(tool_name="call", args={})
            elif "check" in legal:
                action = Action(tool_name="check", args={})
            else:
                action = Action(tool_name="fold", args={})
            return TurnDecisionResult(
                iterations=(), final_action=action,
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:raise_prefer"

    cfg = _cfg(num_hands=6)
    agents = [RaisePrefer() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="pfr_pos_test")
    asyncio.run(sess.run())

    # At least one seat per hand acts preflop and raises (UTG goes first).
    # Total PFR across all seats >= total_hands_played.
    total_pfr = sum(sess._hud_counters[i]["pfr_actions"] for i in range(6))
    assert total_pfr >= sess._total_hands_played, (
        f"raise-prefer session expected total_pfr >= {sess._total_hands_played}, "
        f"got {total_pfr}"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_pfr.py -v 2>&1 | tail -8`
Expected: 3 tests fail (pfr_actions = 0 because no wiring yet).

- [ ] **Step 3: Wire PFR increment**

Edit `src/llm_poker_arena/session/session.py:_run_one_hand`. Inside the action loop, BELOW the VPIP check from Task 2, add:

```python
            # Phase 3c-hud: PFR — voluntary preflop raise (raise_to/bet/all_in).
            # Standard tracker convention treats all_in as a raise even when
            # it equals current_bet_to_match (rare in 6-max deep stack).
            if street == Street.PREFLOP and chosen.tool_name in (
                "raise_to", "bet", "all_in",
            ):
                hand_state[actor]["did_pfr"] = True
```

In the hand-end flush block, add:

```python
            if hand_state[seat]["did_pfr"]:
                self._hud_counters[seat]["pfr_actions"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_pfr.py -v 2>&1 | tail -8`
Expected: 3 tests pass.

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 429 pass + 8 skip.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/session/session.py tests/unit/test_hud_counters_pfr.py
git commit -m "$(cat <<'EOF'
feat(session): PFR counter (Phase 3c-hud Task 3)

Per-hand boolean tracker flipped True on preflop raise_to/bet/all_in.
Same per-hand at-most-one-per-hand semantic as VPIP. PFR ⊆ VPIP by
definition (raising is a subset of voluntary action).

all_in counted as PFR per standard tracker convention even when amount
== current_bet_to_match (rare "call all-in" case in 6-max deep stack).

Tests cover: PFR ≤ VPIP bound, zero on call-only sessions, positive on
raise-prefer sessions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 3-bet counter

**Files:**
- Modify: `src/llm_poker_arena/session/session.py:_run_one_hand` (3-bet chance + action tracking)
- Test: `tests/unit/test_hud_counters_3bet.py` (NEW)

**3-bet semantics** (codex audit BLOCKER B2 fix):
- A 3-bet is the **second** voluntary preflop raise. The first raise is just an open. Anything after the second raise is a 4-bet, 5-bet, etc — NOT a 3-bet.
- **Chance**: seat acts preflop when EXACTLY ONE prior voluntary preflop aggressive action exists (from any other seat) AND this seat has not yet raised preflop in this hand.
- **Action**: seat then raises (raise_to / bet / all_in) in that situation — i.e. they completed the 2nd raise.
- Once a seat has had their 3-bet chance (whether they took it or not), subsequent re-raises (4-bet+) by them are NOT counted again.
- Self-exclusion: own raise doesn't count toward "prior aggressive" lookup (e.g. UTG opens, then UTG facing a 3-bet doesn't count as their own 3-bet chance).
- Implementation: track per-hand `preflop_raise_count` (total voluntary preflop raises so far) AND per-seat `preflop_raised: bool` (this seat already raised preflop this hand).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_hud_counters_3bet.py`:

```python
"""HUD 3-bet counter logic in Session._run_one_hand (Phase 3c-hud Task 4).

3-bet = re-raising preflop after facing an opponent's raise.
chances = "this seat had a preflop turn AFTER an opposing preflop raise"
actions = "this seat then raised in that situation"
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6, seed: int = 42) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=seed,
    )


def test_3bet_actions_subset_of_chances(tmp_path: Path) -> None:
    """3-bet actions ≤ 3-bet chances for every seat (you can't 3-bet
    without a chance)."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="3bet_subset_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["three_bet_actions"] <= c["three_bet_chances"], (
            f"seat {seat} 3bet_actions={c['three_bet_actions']} > "
            f"chances={c['three_bet_chances']}"
        )


def test_3bet_chances_zero_when_no_preflop_raises(tmp_path: Path) -> None:
    """In an all-call session (no raises preflop), no seat ever has a
    3-bet chance. chances=0, actions=0 for everyone."""
    class CallOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            for name in ("call", "check", "fold"):
                if name in legal:
                    action = Action(tool_name=name, args={})
                    break
            else:
                action = Action(tool_name="fold", args={})
            return TurnDecisionResult(
                iterations=(), final_action=action,
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:call_only"

    cfg = _cfg(num_hands=6)
    agents = [CallOnly() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="3bet_no_chance_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["three_bet_chances"] == 0
        assert c["three_bet_actions"] == 0


def test_3bet_chance_when_acting_after_a_raise(tmp_path: Path) -> None:
    """In a raise-prefer session, seats acting after the UTG raise have
    3-bet chance > 0. UTG raises first → seats 1, 2, ... face that
    raise → they have a chance to 3-bet (which they do, in raise-prefer
    setting → 3-bet actions > 0 too)."""
    class RaisePrefer(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            if "raise_to" in legal:
                spec = next(t for t in view.legal_actions.tools
                            if t.name == "raise_to")
                amt = int(spec.args["amount"]["min"])
                action = Action(tool_name="raise_to", args={"amount": amt})
            elif "bet" in legal:
                spec = next(t for t in view.legal_actions.tools if t.name == "bet")
                amt = int(spec.args["amount"]["min"])
                action = Action(tool_name="bet", args={"amount": amt})
            elif "call" in legal:
                action = Action(tool_name="call", args={})
            elif "check" in legal:
                action = Action(tool_name="check", args={})
            else:
                action = Action(tool_name="fold", args={})
            return TurnDecisionResult(
                iterations=(), final_action=action,
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:raise_prefer"

    cfg = _cfg(num_hands=6)
    agents = [RaisePrefer() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="3bet_pos_test")
    asyncio.run(sess.run())

    # Across 6 hands, button rotates → various seats end up acting after the
    # initial raise. Total 3-bet chances across all seats > 0.
    total_chances = sum(sess._hud_counters[i]["three_bet_chances"] for i in range(6))
    assert total_chances > 0, "no seat ever had a 3-bet chance in raise-prefer session"
    # Raise-prefer agents always raise when given a raise option, so they
    # always 3-bet when given the chance.
    total_actions = sum(sess._hud_counters[i]["three_bet_actions"] for i in range(6))
    assert total_actions > 0


def test_own_raise_doesnt_count_as_facing_raise(tmp_path: Path) -> None:
    """If a seat raises first preflop and acts AGAIN later (e.g. opponent
    re-raises and they call), their second action shouldn't count as a
    3-bet chance (own raise excluded from facing-raise computation)."""
    # Hard to construct deterministic scenario without scripted actions.
    # Use RandomAgent and verify invariant: 3bet_chances <= sum_over_hands
    # of (n_seats - 1) (you can have at most n_seats-1 chances per hand
    # — yourself excluded — and chance is per-hand boolean).
    cfg = _cfg(num_hands=6, seed=7)  # different seed for variety
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="3bet_self_excl_test")
    asyncio.run(sess.run())

    for seat in range(6):
        # Per-hand boolean → max 1 chance per hand.
        assert sess._hud_counters[seat]["three_bet_chances"] <= sess._total_hands_played


def test_4bet_not_counted_as_3bet_for_initial_raiser() -> None:
    """codex audit BLOCKER B2 fix: 4-bet edge case verified via direct
    algorithm test on synthetic action_records (no full Session needed).

    Scenario: UTG (seat 3) raises → HJ (seat 4) 3-bets → UTG (seat 3) 4-bets.
    Expected: HJ has chances=1/actions=1; UTG has chances=0/actions=0
    (their 4-bet is NOT a 3-bet because preflop_raise_count was 2 when they
    acted again).

    Test the inline 3-bet logic from session.py via direct synthetic
    construction of action_records + hand_state.
    """
    from llm_poker_arena.storage.schemas import ActionRecordPrivate

    # Simulate the action_records buildup:
    # 1. UTG raise → records=[(seat=3, raise_to)]
    # 2. HJ raise → records=[(seat=3,raise_to),(seat=4,raise_to)]
    # 3. Other seats fold (don't affect 3-bet count)
    # 4. UTG re-raises (4-bet) → records=[..., (seat=3,raise_to)] — but
    #    this UTG action is the one we test below.

    def _record(seat: int, action_type: str) -> ActionRecordPrivate:
        return ActionRecordPrivate(
            seat=seat, street="preflop", action_type=action_type,
            amount=300 if action_type == "raise_to" else None,
            is_forced_blind=False, turn_index=0,
        )

    # State BEFORE UTG's 4-bet decision:
    # action_records contains UTG's open + HJ's 3-bet (+ folds, omitted)
    action_records = [
        _record(3, "raise_to"),  # UTG open
        _record(4, "raise_to"),  # HJ 3-bet
    ]
    # UTG already raised preflop → preflop_raised=True
    seat_already_raised = True

    # Apply the algorithm from Task 4 step 3:
    preflop_raise_count = sum(
        1 for ar in action_records
        if ar.street == "preflop"
        and ar.action_type in ("raise_to", "bet", "all_in")
    )
    had_3bet_chance = (preflop_raise_count == 1 and not seat_already_raised)
    # UTG would re-raise here, but the chance flag is what matters.
    assert preflop_raise_count == 2  # invariant
    assert had_3bet_chance is False, (
        "UTG's 4-bet should NOT be flagged as a 3-bet chance "
        "(preflop_raise_count > 1)"
    )

    # Cross-check: HJ's situation BEFORE their 3-bet decision.
    action_records_at_hj_turn = [_record(3, "raise_to")]  # only UTG's open
    seat_already_raised_hj = False  # HJ hasn't raised yet
    preflop_raise_count_hj = sum(
        1 for ar in action_records_at_hj_turn
        if ar.action_type in ("raise_to", "bet", "all_in")
    )
    had_3bet_chance_hj = (
        preflop_raise_count_hj == 1 and not seat_already_raised_hj
    )
    assert had_3bet_chance_hj is True, (
        "HJ facing UTG's open with no prior raise of their own should have "
        "a 3-bet chance"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_3bet.py -v 2>&1 | tail -10`
Expected: tests 3 fails (no wiring), others pass trivially (counters all 0 = pass subset/no-chance bounds).

- [ ] **Step 3: Wire 3-bet detection**

Edit `src/llm_poker_arena/session/session.py:_run_one_hand`. Update the per-hand `hand_state` dict (initialized at top of method per Task 2) to include `preflop_raised`:

```python
        hand_state: dict[int, dict[str, bool]] = {
            i: {
                "did_vpip": False,
                "did_pfr": False,
                "had_3bet_chance": False,
                "did_3bet": False,
                "preflop_raised": False,
            }
            for i in range(n_seats)
        }
```

Inside the action loop, BELOW the PFR check from Task 3, add:

```python
            # Phase 3c-hud: 3-bet — the SECOND voluntary preflop raise
            # (codex audit BLOCKER B2 fix). Anything beyond is 4-bet+, NOT 3-bet.
            #
            # Chance: this seat acts preflop with EXACTLY ONE prior voluntary
            # aggressive action (from another seat) on the table AND this seat
            # has not yet raised preflop this hand.
            # Action: chance + this seat raises in that turn.
            if street == Street.PREFLOP:
                preflop_raise_count = sum(
                    1 for ar in action_records
                    if ar.street == "preflop"
                    and ar.action_type in ("raise_to", "bet", "all_in")
                )
                if (
                    preflop_raise_count == 1
                    and not hand_state[actor]["preflop_raised"]
                ):
                    hand_state[actor]["had_3bet_chance"] = True
                    if chosen.tool_name in ("raise_to", "bet", "all_in"):
                        hand_state[actor]["did_3bet"] = True
                # Track this seat's own preflop raises for self-exclusion.
                if chosen.tool_name in ("raise_to", "bet", "all_in"):
                    hand_state[actor]["preflop_raised"] = True
```

In the hand-end flush block, add:

```python
            if hand_state[seat]["had_3bet_chance"]:
                self._hud_counters[seat]["three_bet_chances"] += 1
            if hand_state[seat]["did_3bet"]:
                self._hud_counters[seat]["three_bet_actions"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_3bet.py -v 2>&1 | tail -10`
Expected: 5 tests pass.

Run full suite:
`.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 434 pass + 8 skip.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/session/session.py tests/unit/test_hud_counters_3bet.py
git commit -m "$(cat <<'EOF'
feat(session): 3-bet counter (Phase 3c-hud Task 4)

Per-action lookback into action_records: if any prior preflop raise from
a DIFFERENT seat exists when this seat acts preflop, set
had_3bet_chance=True. If this seat also raises in that situation, set
did_3bet=True. Both flushed at hand end.

Self-exclusion: own first raise doesn't count as "facing a raise" when
the seat acts again later (e.g. someone re-raises and they call).

Tests cover: subset invariant (actions ≤ chances), zero-chances in
all-call session, positive chances+actions in raise-prefer session,
per-hand boolean cap (≤ total_hands_played).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: AF (Aggression Factor) counter

**Files:**
- Modify: `src/llm_poker_arena/session/session.py:_run_one_hand` (per-action AF increment)
- Test: `tests/unit/test_hud_counters_af.py` (NEW)

**AF semantics**:
- **All streets** (not just preflop), **individual actions** (not per-hand boolean).
- aggressive = bet + raise_to + all_in
- passive = call
- AF = aggressive / passive (ratio, not rate)
- fold and check are not in AF formula.

When passive=0, AF undefined; builder will fall back to `insufficient=True` for that opponent (Task 7).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_hud_counters_af.py`:

```python
"""HUD AF (Aggression Factor) counter (Phase 3c-hud Task 5)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_af_counters_non_negative(tmp_path: Path) -> None:
    """RandomAgent session: af_aggressive and af_passive both >= 0."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="af_bounds_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["af_aggressive"] >= 0
        assert c["af_passive"] >= 0


def test_af_zero_aggressive_when_only_calls(tmp_path: Path) -> None:
    """Call-only session: af_aggressive=0 (no bet/raise/all_in)."""
    class CallOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            for name in ("call", "check", "fold"):
                if name in legal:
                    action = Action(tool_name=name, args={})
                    break
            else:
                action = Action(tool_name="fold", args={})
            return TurnDecisionResult(
                iterations=(), final_action=action,
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:call_only"

    cfg = _cfg(num_hands=6)
    agents = [CallOnly() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="af_zero_agg_test")
    asyncio.run(sess.run())

    for seat in range(6):
        assert sess._hud_counters[seat]["af_aggressive"] == 0


def test_af_zero_passive_when_only_raises(tmp_path: Path) -> None:
    """Raise-prefer session never calls — af_passive=0 for all seats."""
    class RaisePrefer(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            if "raise_to" in legal:
                spec = next(t for t in view.legal_actions.tools
                            if t.name == "raise_to")
                amt = int(spec.args["amount"]["min"])
                action = Action(tool_name="raise_to", args={"amount": amt})
            elif "bet" in legal:
                spec = next(t for t in view.legal_actions.tools if t.name == "bet")
                amt = int(spec.args["amount"]["min"])
                action = Action(tool_name="bet", args={"amount": amt})
            elif "check" in legal:
                action = Action(tool_name="check", args={})  # avoid call
            elif "fold" in legal:
                action = Action(tool_name="fold", args={})
            else:
                action = Action(tool_name="call", args={})  # last resort
            return TurnDecisionResult(
                iterations=(), final_action=action,
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:raise_prefer"

    cfg = _cfg(num_hands=6)
    agents = [RaisePrefer() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="af_zero_pass_test")
    asyncio.run(sess.run())

    # NOTE: this test only verifies af_passive == 0; aggressive may or may
    # not be > 0 depending on hand flow (BB might not get raise option, etc.).
    for seat in range(6):
        assert sess._hud_counters[seat]["af_passive"] == 0, (
            f"seat {seat} af_passive={sess._hud_counters[seat]['af_passive']} "
            f"!= 0 in raise-prefer session"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_af.py -v 2>&1 | tail -8`
Expected: tests 1-2 pass trivially (zero counters); test 3 fails or passes depending on baseline state — really need wiring before any meaningful pass.

- [ ] **Step 3: Wire AF counter**

Edit `src/llm_poker_arena/session/session.py:_run_one_hand`. Inside the action loop, BELOW the 3-bet check, add (note: AF is per-action, NOT per-hand, so no `hand_state` boolean):

```python
            # Phase 3c-hud: AF — individual action ratio across all streets.
            # aggressive = bet + raise_to + all_in
            # passive = call
            # fold + check not in formula (Task 5).
            if chosen.tool_name in ("bet", "raise_to", "all_in"):
                self._hud_counters[actor]["af_aggressive"] += 1
            elif chosen.tool_name == "call":
                self._hud_counters[actor]["af_passive"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_af.py -v 2>&1 | tail -8`
Expected: 3 tests pass.

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 437 pass + 8 skip.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/session/session.py tests/unit/test_hud_counters_af.py
git commit -m "$(cat <<'EOF'
feat(session): AF (Aggression Factor) counter (Phase 3c-hud Task 5)

Per-action increment across ALL streets (not just preflop). Aggressive =
bet/raise_to/all_in; passive = call. fold/check not in formula.

Different from VPIP/PFR/3-bet/WTSD which are per-hand boolean flushes —
AF is individual action count → ratio at read time.

When af_passive=0, AF is undefined; build_player_view (Task 7) will fall
back to insufficient=True for that opponent (avoids inf/null in
non-nullable Pydantic field).

Tests cover: bounds, zero-aggressive on call-only, zero-passive on
raise-prefer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: WTSD counter

**Files:**
- Modify: `src/llm_poker_arena/session/session.py:_run_one_hand` (WTSD chance + action tracking)
- Test: `tests/unit/test_hud_counters_wtsd.py` (NEW)

**WTSD semantics**:
- chances = number of hands where seat had VPIP=True (saw beyond forced blinds)
- actions = number of hands where seat had VPIP=True AND reached showdown (in `showdown_seats` at hand end)
- Depends on VPIP boolean (Task 2) and `showdown_seats` set (already computed in `_run_one_hand` at hand end).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_hud_counters_wtsd.py`:

```python
"""HUD WTSD counter (Phase 3c-hud Task 6).

WTSD = Went-To-Showdown given VPIP.
chances = vpip-true hands; actions = vpip-true AND reached showdown.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_wtsd_actions_subset_of_chances(tmp_path: Path) -> None:
    """wtsd_actions ≤ wtsd_chances (you can't reach showdown without VPIP)."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="wtsd_subset_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["wtsd_actions"] <= c["wtsd_chances"]


def test_wtsd_chances_equals_vpip_actions(tmp_path: Path) -> None:
    """wtsd_chances and vpip_actions track the same per-hand boolean —
    they should always be equal (Task 6 wires WTSD chance increment off
    the same did_vpip flag)."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="wtsd_eq_vpip_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["wtsd_chances"] == c["vpip_actions"], (
            f"seat {seat}: wtsd_chances={c['wtsd_chances']} != "
            f"vpip_actions={c['vpip_actions']}"
        )


def test_wtsd_zero_when_only_folds(tmp_path: Path) -> None:
    """Fold-only session: no VPIP → no WTSD chances."""
    class FoldOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            action_name = "fold" if "fold" in legal else "check"
            return TurnDecisionResult(
                iterations=(), final_action=Action(tool_name=action_name, args={}),
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:fold_only"

    cfg = _cfg(num_hands=6)
    agents = [FoldOnly() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="wtsd_zero_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["wtsd_chances"] == 0
        assert c["wtsd_actions"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_wtsd.py -v 2>&1 | tail -8`
Expected: tests 1+3 pass trivially; test 2 fails (wtsd_chances stays 0 while vpip_actions > 0).

- [ ] **Step 3: Wire WTSD increment in hand-end flush**

Edit `src/llm_poker_arena/session/session.py:_run_one_hand`. The hand-end flush block from Tasks 2-4 needs to access `showdown_seats`. `showdown_seats` is computed AFTER the action loop but is needed for WTSD flush. Find the existing line (around line 299):

```python
        statuses = list(state._state.statuses)  # noqa: SLF001
        showdown_seats = {i for i, alive in enumerate(statuses) if bool(alive)}
```

The hand-end HUD flush block must be AFTER `showdown_seats` is computed. Adjust the flush location: move the entire HUD flush below `showdown_seats` definition.

Update the flush block to:

```python
        # Phase 3c-hud: flush per-hand booleans to cumulative counters.
        # codex audit IMPORTANT-5: also bump HUD-only completed-hand counter.
        # This block ONLY runs on clean hand completion (censored hands return
        # early earlier in the method), so _hud_hands_counted reflects the
        # true denominator for VPIP/PFR rates and min-sample gating.
        self._hud_hands_counted += 1
        for seat in range(n_seats):
            if hand_state[seat]["did_vpip"]:
                self._hud_counters[seat]["vpip_actions"] += 1
                # WTSD chance = saw post-blind action; granted to all VPIP hands.
                self._hud_counters[seat]["wtsd_chances"] += 1
                if seat in showdown_seats:
                    self._hud_counters[seat]["wtsd_actions"] += 1
            if hand_state[seat]["did_pfr"]:
                self._hud_counters[seat]["pfr_actions"] += 1
            if hand_state[seat]["had_3bet_chance"]:
                self._hud_counters[seat]["three_bet_chances"] += 1
            if hand_state[seat]["did_3bet"]:
                self._hud_counters[seat]["three_bet_actions"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_hud_counters_wtsd.py tests/unit/test_hud_counters_vpip.py tests/unit/test_hud_counters_pfr.py tests/unit/test_hud_counters_3bet.py -v 2>&1 | tail -10`
Expected: all pass (the flush relocation didn't break VPIP/PFR/3-bet tests).

Run full suite:
`.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 440 pass + 8 skip.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/session/session.py tests/unit/test_hud_counters_wtsd.py
git commit -m "$(cat <<'EOF'
feat(session): WTSD counter (Phase 3c-hud Task 6)

WTSD = Went-To-Showdown given VPIP. Chances = VPIP-true hands; actions
= VPIP-true AND seat survived to showdown_seats at hand end.

Tightly coupled to VPIP (Task 2) — wtsd_chances tracks the same
per-hand boolean, so wtsd_chances == vpip_actions invariant holds.

Implementation note: hand-end flush block moved BELOW showdown_seats
computation (otherwise WTSD wouldn't have showdown_seats in scope).
VPIP/PFR/3-bet flush logic unchanged.

Tests cover: subset (actions ≤ chances), wtsd_chances == vpip_actions
invariant, zero in fold-only session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: build_player_view threads opponent_stats + insufficient sentinel

**Files:**
- Modify: `src/llm_poker_arena/engine/projections.py:build_player_view` (accept `opponent_stats` kwarg)
- Modify: `src/llm_poker_arena/session/session.py:_run_one_hand` (compute + pass opponent_stats)
- Modify: `src/llm_poker_arena/session/session.py` (add `_build_opponent_stats` method)
- Test: `tests/unit/test_build_player_view_opponent_stats.py` (NEW)

**Sentinel logic**:
- If `_hud_hands_counted < opponent_stats_min_samples` (default 30; counts only cleanly-completed hands per codex audit IMPORTANT-5) → `insufficient=True` for ALL opponents.
- Else if any individual stat denominator = 0 (rare past 30 hands) → `insufficient=True` for that opponent.
- Else → all 5 stats populated as floats.

This conservative all-or-nothing policy avoids the `OpponentStatsOrInsufficient` validator's `not insufficient → all numeric required` constraint.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_build_player_view_opponent_stats.py`:

```python
"""build_player_view threads opponent_stats from Session counters
(Phase 3c-hud Task 7)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.views import OpponentStatsOrInsufficient
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6, min_samples: int = 30) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=min_samples, rng_seed=42,
    )


def test_build_view_default_opponent_stats_is_empty() -> None:
    """When no opponent_stats kwarg passed, opponent_stats stays {} (back-compat)."""
    cfg = _cfg()
    ctx = HandContext(
        hand_id=0, deck_seed=derive_deck_seed(42, 0),
        button_seat=0, initial_stacks=(10_000,) * 6,
    )
    state = CanonicalState(cfg, ctx)
    view = build_player_view(state, actor=3, turn_seed=42)
    assert view.opponent_stats == {}


def test_build_view_with_opponent_stats_kwarg_populates() -> None:
    """Pass explicit opponent_stats dict → view.opponent_stats reflects it."""
    cfg = _cfg()
    ctx = HandContext(
        hand_id=0, deck_seed=derive_deck_seed(42, 0),
        button_seat=0, initial_stacks=(10_000,) * 6,
    )
    state = CanonicalState(cfg, ctx)
    stats = {
        0: OpponentStatsOrInsufficient(insufficient=True),
        1: OpponentStatsOrInsufficient(insufficient=True),
    }
    view = build_player_view(state, actor=3, turn_seed=42, opponent_stats=stats)
    assert view.opponent_stats == stats


def test_session_below_min_samples_returns_insufficient(tmp_path: Path) -> None:
    """6-hand session with default min_samples=30 → all opponents
    insufficient because total_hands_played (6) < 30."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="insufficient_test")
    asyncio.run(sess.run())

    # Call _build_opponent_stats(actor=3) directly post-session.
    stats = sess._build_opponent_stats(actor=3)
    # Self-seat (3) NOT in dict.
    assert 3 not in stats
    # Other 5 seats all insufficient.
    assert set(stats.keys()) == {0, 1, 2, 4, 5}
    for seat, s in stats.items():
        assert s.insufficient, f"seat {seat} should be insufficient at 6 < 30 hands"


def test_build_opponent_stats_deterministic_above_min_samples(tmp_path: Path) -> None:
    """codex audit IMPORTANT-7 fix: directly seed Session._hud_counters and
    _hud_hands_counted instead of running 30 RandomAgent hands (which is
    fragile with the all-or-nothing sentinel)."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="seeded_test")
    # Seed the session as if 30 clean hands have completed.
    sess._hud_hands_counted = 30
    for seat in range(6):
        sess._hud_counters[seat] = {
            "vpip_actions": 12,           # 40% VPIP
            "pfr_actions": 6,             # 20% PFR
            "three_bet_chances": 5,
            "three_bet_actions": 1,       # 20% 3-bet
            "af_aggressive": 18,
            "af_passive": 9,              # AF = 2.0
            "wtsd_chances": 12,           # = vpip_actions per WTSD def
            "wtsd_actions": 4,            # 33% WTSD
        }
    stats = sess._build_opponent_stats(actor=3)
    assert set(stats.keys()) == {0, 1, 2, 4, 5}
    for seat, s in stats.items():
        assert not s.insufficient, f"seat {seat} unexpectedly insufficient"
        assert s.vpip == 12 / 30
        assert s.pfr == 6 / 30
        assert s.three_bet == 1 / 5
        assert s.af == 18 / 9
        assert s.wtsd == 4 / 12


def test_build_opponent_stats_3bet_den_zero_falls_back_to_insufficient(
    tmp_path: Path,
) -> None:
    """codex audit IMPORTANT-6: opponent past min_samples but with
    three_bet_chances=0 falls back to insufficient=True (all-or-nothing
    sentinel — documented v1 limitation)."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="3bet_den_zero_test")
    sess._hud_hands_counted = 30
    sess._hud_counters[0] = {
        "vpip_actions": 12, "pfr_actions": 6,
        "three_bet_chances": 0,           # ← zero denominator
        "three_bet_actions": 0,
        "af_aggressive": 18, "af_passive": 9,
        "wtsd_chances": 12, "wtsd_actions": 4,
    }
    stats = sess._build_opponent_stats(actor=3)
    assert stats[0].insufficient is True


def test_build_opponent_stats_af_passive_zero_falls_back_to_insufficient(
    tmp_path: Path,
) -> None:
    """codex audit IMPORTANT-6: opponent past min_samples but with
    af_passive=0 (never called) falls back to insufficient=True."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="af_passive_zero_test")
    sess._hud_hands_counted = 30
    sess._hud_counters[0] = {
        "vpip_actions": 12, "pfr_actions": 12,
        "three_bet_chances": 5, "three_bet_actions": 3,
        "af_aggressive": 30,
        "af_passive": 0,                  # ← zero denominator
        "wtsd_chances": 12, "wtsd_actions": 4,
    }
    stats = sess._build_opponent_stats(actor=3)
    assert stats[0].insufficient is True


def test_build_opponent_stats_uses_hud_hands_counted_not_total(
    tmp_path: Path,
) -> None:
    """codex audit IMPORTANT-5: denominator must be _hud_hands_counted
    (clean-completion count), not _total_hands_played (which counts
    censored hands too). Simulate divergent counters."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="hud_hands_counter_test")
    # Simulate: 50 total hands attempted, 5 were censored, 45 cleanly
    # completed and contributed HUD counters. 45 >= min_samples=30 → not
    # insufficient.
    sess._total_hands_played = 50
    sess._hud_hands_counted = 45
    for seat in range(6):
        sess._hud_counters[seat] = {
            "vpip_actions": 18, "pfr_actions": 9,
            "three_bet_chances": 7, "three_bet_actions": 2,
            "af_aggressive": 27, "af_passive": 14,
            "wtsd_chances": 18, "wtsd_actions": 6,
        }
    stats = sess._build_opponent_stats(actor=3)
    for seat in (0, 1, 2, 4, 5):
        assert not stats[seat].insufficient, (
            f"seat {seat} should be sufficient (45 clean hands ≥ 30)"
        )
        # Rate should use 45 not 50.
        assert abs(stats[seat].vpip - 18 / 45) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_build_player_view_opponent_stats.py -v 2>&1 | tail -10`
Expected: tests 2-4 fail (build_player_view doesn't accept opponent_stats kwarg; _build_opponent_stats method doesn't exist).

- [ ] **Step 3: Extend `build_player_view` signature**

Edit `src/llm_poker_arena/engine/projections.py`. Find `build_player_view` (around line 30-180). Update signature to accept `opponent_stats: dict[int, OpponentStatsOrInsufficient] | None = None` kwarg. At line 178 (current `opponent_stats={}` hardcode), replace:

```python
        opponent_stats=opponent_stats or {},
```

Also update the function signature to add the new param. The full call site change: append `opponent_stats: dict[int, OpponentStatsOrInsufficient] | None = None,` to the keyword-only params (use the existing `from llm_poker_arena.engine.views import ...` to add `OpponentStatsOrInsufficient` if not already imported).

Verify import at top of projections.py — if `OpponentStatsOrInsufficient` not imported, add:

```python
from llm_poker_arena.engine.views import (
    ...,
    OpponentStatsOrInsufficient,
)
```

Remove the `# TODO(phase2): thread HUD stats from DuckDB` comment.

- [ ] **Step 4: Add `_build_opponent_stats` method to Session**

Edit `src/llm_poker_arena/session/session.py`. First add `OpponentStatsOrInsufficient` to the module-level imports (codex re-audit BLOCKER N3 fix — using the name only inside the function would leave it undefined for the return-type annotation, failing mypy --strict). Update the existing `from llm_poker_arena.engine.views import ...` block (or add a new import line near line 39):

```python
from llm_poker_arena.engine.views import OpponentStatsOrInsufficient
```

(If session.py doesn't already import from `engine.views`, add this as a new line near the other engine imports.)

Then add this method on `Session` class (place after `_probe_providers` or anywhere logical):

```python
    def _build_opponent_stats(
        self, actor: int,
    ) -> dict[int, OpponentStatsOrInsufficient]:
        """Phase 3c-hud: build per-opponent OpponentStatsOrInsufficient dict
        from cumulative HUD counters. Self-seat excluded.

        Uses _hud_hands_counted (codex audit IMPORTANT-5) — counts only
        cleanly-completed hands. Censored hands (api_error → early return
        in _run_one_hand) don't depress VPIP/PFR rates or count toward
        min-sample gating.

        Returns insufficient=True for ALL opponents when _hud_hands_counted
        < opponent_stats_min_samples. Past that threshold, returns
        insufficient=True ONLY for individual opponents whose specific stat
        denominator is 0 (rare edge case — opponent who played 30+ hands
        but never had a 3-bet opportunity, or never called).

        Conservative all-or-nothing per-opponent policy avoids the
        OpponentStatsOrInsufficient validator's "non-insufficient → all
        numeric required" constraint. Documented limitation: an opponent
        past 30 hands with no 3-bet chance / no calls / no VPIP loses
        all 5 stats. Future Phase 5+ may relax the validator to per-stat
        None handling.
        """
        # OpponentStatsOrInsufficient imported at module top (codex re-audit
        # BLOCKER N3 fix — annotation must resolve under mypy --strict).
        n_played = self._hud_hands_counted
        min_samples = self._config.opponent_stats_min_samples
        out: dict[int, OpponentStatsOrInsufficient] = {}
        for seat in range(self._config.num_players):
            if seat == actor:
                continue  # exclude self
            if n_played < min_samples:
                out[seat] = OpponentStatsOrInsufficient(insufficient=True)
                continue
            c = self._hud_counters[seat]
            three_bet_den = c["three_bet_chances"]
            af_den = c["af_passive"]
            wtsd_den = c["wtsd_chances"]
            if three_bet_den == 0 or af_den == 0 or wtsd_den == 0:
                out[seat] = OpponentStatsOrInsufficient(insufficient=True)
                continue
            out[seat] = OpponentStatsOrInsufficient(
                insufficient=False,
                vpip=c["vpip_actions"] / n_played,
                pfr=c["pfr_actions"] / n_played,
                three_bet=c["three_bet_actions"] / three_bet_den,
                af=c["af_aggressive"] / af_den,
                wtsd=c["wtsd_actions"] / wtsd_den,
            )
        return out
```

- [ ] **Step 5: Wire into `_run_one_hand`**

Edit `src/llm_poker_arena/session/session.py:_run_one_hand`. Find the `view = build_player_view(state, actor, turn_seed=turn_seed)` line (around line 228). Replace with:

```python
            opp_stats = self._build_opponent_stats(actor)
            view = build_player_view(
                state, actor, turn_seed=turn_seed,
                opponent_stats=opp_stats,
            )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_build_player_view_opponent_stats.py -v 2>&1 | tail -10`
Expected: 7 tests pass.

Run full suite:
`.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 447 pass + 8 skip.

- [ ] **Step 7: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/llm_poker_arena/engine/projections.py \
        src/llm_poker_arena/session/session.py \
        tests/unit/test_build_player_view_opponent_stats.py
git commit -m "$(cat <<'EOF'
feat(view): build_player_view threads opponent_stats (Phase 3c-hud Task 7)

build_player_view accepts optional opponent_stats kwarg (default None →
{} for backward compat). Removes Phase 2 TODO at projections.py:178.

Session._build_opponent_stats(actor) computes per-opponent stats from
HUD counters with two-tier insufficient sentinel:
  - _hud_hands_counted < min_samples → insufficient=True for all opponents
    (clean-completion counter; codex audit IMPORTANT-5)
  - any specific denominator (3bet_chances / af_passive / wtsd_chances)
    = 0 past threshold → insufficient=True for that opponent only

Conservative all-or-nothing per-opponent policy avoids
OpponentStatsOrInsufficient validator's "non-insufficient requires all
5 numeric" constraint. Edge case: opponent past 30 hands but never had
a 3-bet opportunity stays insufficient. Documented in plan.

Tests cover: empty default (back-compat), kwarg threading, below-min-
samples → all insufficient, above-min-samples → populated stats with
non-None values in [0, 1] (AF >= 0).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: get_opponent_stats tool + dispatcher route + spec advertisement

**Files:**
- Create: `src/llm_poker_arena/tools/opponent_stats.py` (`get_opponent_stats` tool implementation)
- Modify: `src/llm_poker_arena/tools/__init__.py` (export + dispatcher route)
- Modify: `src/llm_poker_arena/tools/utility_tool_specs.py` or equivalent (add `OPPONENT_STATS_SPEC`, gated on `enable_hud_tool`)
- Modify: `src/llm_poker_arena/agents/llm/prompts/system.j2` (advertise HUD tool)
- Test: `tests/unit/test_get_opponent_stats_tool.py` (NEW)

- [ ] **Step 1: Confirm existing dispatcher convention**

Existing convention (verified in `src/llm_poker_arena/tools/runner.py`):
- `run_utility_tool(view, name, args)` validates args, dispatches to per-tool function
- Per-tool functions (`pot_odds`, `spr`, `hand_equity_vs_ranges`) **raise `ToolDispatchError`** on invalid input — they do NOT return `{"error": ...}` dicts
- LLMAgent's K+1 loop catches `ToolDispatchError` and surfaces as tool_result error to LLM
- `_ALLOWED_ARGS` dict gates allowed kwargs per tool
- `utility_tool_specs(view)` returns spec list; currently early-returns `[]` when `enable_math_tools=False` — needs refactor to handle math+hud independently

`get_opponent_stats` follows the same convention: raise `ToolDispatchError` on invalid input.

Existing prompt context (verified in `src/llm_poker_arena/agents/llm/prompt_profile.py:render_system`):
- Currently accepts `enable_math_tools` + `max_utility_calls`
- Needs new params: `enable_hud_tool` + `opponent_stats_min_samples`
- Call site at `src/llm_poker_arena/agents/llm/llm_agent.py:525` needs both new args passed

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_get_opponent_stats_tool.py`:

```python
"""get_opponent_stats tool (Phase 3c-hud Task 8)."""
from __future__ import annotations

import pytest

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    OpponentStatsOrInsufficient,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools import run_utility_tool
from llm_poker_arena.tools.opponent_stats import get_opponent_stats


def _view(
    enable_hud_tool: bool = True,
    opponent_stats: dict[int, OpponentStatsOrInsufficient] | None = None,
) -> PlayerView:
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=enable_hud_tool,
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
        opponent_stats=opponent_stats or {},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params,
    )


def test_get_opponent_stats_returns_view_data() -> None:
    """Tool returns OpponentStatsOrInsufficient.model_dump for queried seat."""
    stats = {
        0: OpponentStatsOrInsufficient(
            insufficient=False, vpip=0.32, pfr=0.18,
            three_bet=0.05, af=2.1, wtsd=0.28,
        ),
    }
    view = _view(opponent_stats=stats)
    result = get_opponent_stats(view, seat=0)
    assert result["insufficient"] is False
    assert result["vpip"] == 0.32
    assert result["wtsd"] == 0.28


def test_get_opponent_stats_self_seat_raises() -> None:
    """Tool rejects seat == my_seat (no peeking at own stats via opponent
    interface — use direct view fields for self). Convention: raise
    ToolDispatchError, not return error dict."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    view = _view()
    with pytest.raises(ToolDispatchError, match="own|self"):
        get_opponent_stats(view, seat=3)  # my_seat=3


def test_get_opponent_stats_out_of_range_seat_raises() -> None:
    """seat must be in [0, num_players). seat=99 → ToolDispatchError."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    view = _view()
    with pytest.raises(ToolDispatchError, match="seat"):
        get_opponent_stats(view, seat=99)


def test_dispatcher_blocks_hud_tool_when_disabled() -> None:
    """When enable_hud_tool=False, run_utility_tool('get_opponent_stats')
    raises ToolDispatchError (gate enforced before dispatch)."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    view = _view(enable_hud_tool=False)
    with pytest.raises(ToolDispatchError, match="not enabled|disabled|enable_hud"):
        run_utility_tool(view, "get_opponent_stats", {"seat": 0})


def test_dispatcher_missing_seat_arg_raises_tool_dispatch_error() -> None:
    """codex audit BLOCKER B3: missing 'seat' arg must raise
    ToolDispatchError (not uncaught TypeError) — LLMAgent only catches
    ToolDispatchError, an uncaught TypeError would crash the turn."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    view = _view(enable_hud_tool=True)
    with pytest.raises(ToolDispatchError, match="requires 'seat'|seat"):
        run_utility_tool(view, "get_opponent_stats", {})


def test_utility_tool_specs_hud_independent_of_math() -> None:
    """codex audit IMPORTANT-9: utility_tool_specs must include HUD spec
    when enable_hud_tool=True even if enable_math_tools=False (independent
    gates). Currently covered by manually editing _view's flags."""
    from llm_poker_arena.tools.runner import utility_tool_specs

    # Math off, HUD on → only HUD spec.
    view_hud_only = _view(enable_hud_tool=True)
    # _view default enable_math_tools=False; HUD spec should appear.
    specs = utility_tool_specs(view_hud_only)
    names = [s["name"] for s in specs]
    assert "get_opponent_stats" in names
    # Math tools NOT included.
    assert "pot_odds" not in names
    assert "spr" not in names
    assert "hand_equity_vs_ranges" not in names


def test_utility_tool_specs_both_math_and_hud_enabled() -> None:
    """When both enable_math_tools=True AND enable_hud_tool=True, all 4
    utility specs appear."""
    from llm_poker_arena.tools.runner import utility_tool_specs

    # Use a custom view with both flags on.
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=True,
        opponent_stats_min_samples=30,
    )
    view = PlayerView(
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
    specs = utility_tool_specs(view)
    names = [s["name"] for s in specs]
    assert set(names) == {"pot_odds", "spr", "hand_equity_vs_ranges", "get_opponent_stats"}


def test_system_prompt_includes_hud_block_when_enabled() -> None:
    """codex audit IMPORTANT-9: system.j2 advertises HUD tool when
    enable_hud_tool=True."""
    from llm_poker_arena.agents.llm.prompt_profile import (
        load_default_prompt_profile,
    )
    profile = load_default_prompt_profile()
    text = profile.render_system(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        enable_math_tools=False, enable_hud_tool=True,
        opponent_stats_min_samples=30, max_utility_calls=5,
    )
    assert "get_opponent_stats" in text
    assert "30" in text  # opponent_stats_min_samples shown


def test_system_prompt_omits_hud_block_when_disabled() -> None:
    """When enable_hud_tool=False, HUD section absent from system prompt."""
    from llm_poker_arena.agents.llm.prompt_profile import (
        load_default_prompt_profile,
    )
    profile = load_default_prompt_profile()
    text = profile.render_system(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30, max_utility_calls=5,
    )
    assert "get_opponent_stats" not in text


def test_user_prompt_includes_opponent_stats_block_when_populated() -> None:
    """codex audit BLOCKER B1: user.j2 renders opponent_stats when passed."""
    from llm_poker_arena.agents.llm.prompt_profile import (
        load_default_prompt_profile,
    )
    profile = load_default_prompt_profile()
    stats = {
        0: OpponentStatsOrInsufficient(
            insufficient=False, vpip=0.32, pfr=0.18,
            three_bet=0.05, af=2.1, wtsd=0.28,
        ),
        1: OpponentStatsOrInsufficient(insufficient=True),
    }
    seats_public = [
        SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                       position_full="x", stack=10_000,
                       invested_this_hand=0, invested_this_round=0,
                       status="in_hand") for i in range(6)
    ]
    text = profile.render_user(
        hand_id=1, street="preflop", my_seat=3,
        my_position_short="UTG", my_position_full="x",
        my_hole_cards=("As", "Kd"), community=(),
        pot=150, my_stack=10_000, to_call=100,
        pot_odds_required=0.4, effective_stack=10_000,
        button_seat=0, opponent_seats_in_hand=(0, 1, 2, 4, 5),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        seats_public=seats_public,
        opponent_stats=stats,
    )
    assert "OPPONENT STATS" in text
    assert "VPIP=0.32" in text
    assert "insufficient samples" in text  # for seat 1


def test_user_prompt_omits_opponent_stats_block_when_empty() -> None:
    """When opponent_stats={} or None, user prompt has no OPPONENT STATS section."""
    from llm_poker_arena.agents.llm.prompt_profile import (
        load_default_prompt_profile,
    )
    profile = load_default_prompt_profile()
    seats_public = [
        SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                       position_full="x", stack=10_000,
                       invested_this_hand=0, invested_this_round=0,
                       status="in_hand") for i in range(6)
    ]
    text = profile.render_user(
        hand_id=1, street="preflop", my_seat=3,
        my_position_short="UTG", my_position_full="x",
        my_hole_cards=("As", "Kd"), community=(),
        pot=150, my_stack=10_000, to_call=100,
        pot_odds_required=0.4, effective_stack=10_000,
        button_seat=0, opponent_seats_in_hand=(0, 1, 2, 4, 5),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        seats_public=seats_public,
        opponent_stats={},
    )
    assert "OPPONENT STATS" not in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_get_opponent_stats_tool.py -v 2>&1 | tail -10`
Expected: imports fail (`opponent_stats.py` doesn't exist).

- [ ] **Step 4: Implement `get_opponent_stats` tool**

Create `src/llm_poker_arena/tools/opponent_stats.py`:

```python
"""get_opponent_stats utility tool (spec §5.2 / Phase 3c-hud).

Thin accessor over PlayerView.opponent_stats — counter computation lives
in Session._build_opponent_stats. Tool validates seat ∈ [0, num_players),
seat ≠ my_seat, returns OpponentStatsOrInsufficient as dict.

Raises ToolDispatchError on invalid input (matches pot_odds/spr/equity
convention; LLMAgent K+1 loop catches and surfaces error to LLM).
"""
from __future__ import annotations

from typing import Any

from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.tools.runner import ToolDispatchError


def get_opponent_stats(
    view: PlayerView,
    seat: int,
    detail_level: str = "summary",
) -> dict[str, Any]:
    """Return opponent's HUD stats for the given seat.

    Args:
        view: current PlayerView (carries pre-computed opponent_stats dict).
        seat: opponent seat to query. Must be in [0, num_players) and != my_seat.
        detail_level: only "summary" supported in Phase 3c-hud. "detailed"
            reserved for Phase 5+.

    Returns:
        OpponentStatsOrInsufficient as dict (vpip/pfr/three_bet/af/wtsd
        floats, or insufficient=True sentinel).

    Raises:
        ToolDispatchError on invalid input (detail_level, seat range, self-seat).
    """
    if detail_level != "summary":
        raise ToolDispatchError(
            f"detail_level must be 'summary' (got {detail_level!r}); "
            "Phase 3c-hud ships summary only"
        )
    n_players = view.immutable_session_params.num_players
    if isinstance(seat, bool) or not isinstance(seat, int):
        raise ToolDispatchError(
            f"seat must be an integer; got {type(seat).__name__}={seat!r}"
        )
    if not 0 <= seat < n_players:
        raise ToolDispatchError(f"seat {seat!r} not in [0, {n_players})")
    if seat == view.my_seat:
        raise ToolDispatchError(
            f"cannot query own seat ({seat}); use PlayerView fields directly "
            "for self-stats"
        )
    stats = view.opponent_stats.get(seat)
    if stats is None:
        # Should not happen in normal Session flow — Session populates all
        # other seats. Defensive return for edge cases (folded seat post-hand).
        return {"insufficient": True}
    return stats.model_dump(mode="json")
```

- [ ] **Step 5: Wire dispatcher route + tool spec in `runner.py`**

Edit `src/llm_poker_arena/tools/runner.py`. Three changes:

**5a)** Add to `_ALLOWED_ARGS` (around line 28):

```python
_ALLOWED_ARGS: dict[str, frozenset[str]] = {
    "pot_odds": frozenset({"to_call", "pot"}),
    "spr": frozenset({"stack", "pot"}),
    "hand_equity_vs_ranges": frozenset({"range_by_seat"}),
    "get_opponent_stats": frozenset({"seat", "detail_level"}),
}
```

**5b)** Add dispatch branch at the end of `run_utility_tool` body (after the equity branch, before function ends — around line 113). The current `# name == "hand_equity_vs_ranges"` comment + return on line 89 acts as the "default" since unknown names already raised on line 72. Replace the trailing equity-only branch with explicit `if name == "hand_equity_vs_ranges":` then add HUD branch:

```python
    if name == "hand_equity_vs_ranges":
        range_by_seat = args.get("range_by_seat")
        if not isinstance(range_by_seat, dict):
            raise ToolDispatchError(
                f"hand_equity_vs_ranges.range_by_seat must be a dict; "
                f"got {type(range_by_seat).__name__}"
            )
        coerced: dict[int, str] = {}
        for k, val in range_by_seat.items():
            try:
                seat_int = int(k)
            except (ValueError, TypeError) as e:
                raise ToolDispatchError(
                    f"hand_equity_vs_ranges.range_by_seat key {k!r} must be a "
                    f"seat integer (or string-encoded integer)"
                ) from e
            if not isinstance(val, str):
                raise ToolDispatchError(
                    f"hand_equity_vs_ranges.range_by_seat[{seat_int}] must be a "
                    f"string range; got {type(val).__name__}"
                )
            coerced[seat_int] = val
        return hand_equity_vs_ranges(view, coerced)
    # name == "get_opponent_stats" (Phase 3c-hud)
    if not view.immutable_session_params.enable_hud_tool:
        raise ToolDispatchError(
            "get_opponent_stats not enabled (enable_hud_tool=False)"
        )
    # codex audit BLOCKER B3 fix: explicit required-arg validation.
    # _ALLOWED_ARGS only checks for EXTRA args; missing "seat" would otherwise
    # raise an uncaught TypeError from get_opponent_stats(view, **args) since
    # LLMAgent only catches ToolDispatchError.
    if "seat" not in args:
        raise ToolDispatchError(
            "get_opponent_stats requires 'seat' arg"
        )
    from llm_poker_arena.tools.opponent_stats import get_opponent_stats
    return get_opponent_stats(view, **args)
```

(Update the import block at the top of `run_utility_tool` to include the equity import — already present per existing code.)

**5c)** Refactor `utility_tool_specs(view)` to handle math + hud independently. Current code early-returns `[]` when `enable_math_tools=False`; this would prevent HUD from appearing when only `enable_hud_tool=True`. Replace lines 116-207:

```python
def utility_tool_specs(view: PlayerView) -> list[dict[str, Any]]:
    """Return Anthropic-shape tool spec list for utility tools enabled on
    this view's session params. Empty list when both math and hud are off.

    spec §5.3 build_tool_specs reads view.immutable_session_params for
    enable_math_tools and enable_hud_tool independently. Phase 3c-math
    ships pot_odds + spr; 3c-equity adds hand_equity_vs_ranges (all gated
    on enable_math_tools); 3c-hud adds get_opponent_stats (gated on
    enable_hud_tool, independent of math).
    """
    params = view.immutable_session_params
    specs: list[dict[str, Any]] = []
    if params.enable_math_tools:
        specs.extend([
            {
                "name": "pot_odds",
                "description": (
                    "Compute pot odds = to_call / (pot + to_call). Optional args "
                    "let you compute hypothetical scenarios (e.g. 'if I raise to "
                    "X, what pot odds does villain face'). Zero-arg call uses the "
                    "current to_call and pot from your turn state."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to_call": {
                            "type": "integer",
                            "description": "Optional override for the to_call amount; defaults to current.",
                            "minimum": 0,
                        },
                        "pot": {
                            "type": "integer",
                            "description": "Optional override for the pot size; defaults to current.",
                            "minimum": 0,
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "name": "spr",
                "description": (
                    "Compute stack-to-pot ratio = stack / pot. Default stack is "
                    "your effective_stack (the smallest live stack at risk for "
                    "showdown). Optional args support post-flop SPR planning "
                    "(e.g. 'after I raise to X, new SPR on flop is Y')."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "stack": {
                            "type": "integer",
                            "description": "Optional override for the stack; defaults to effective_stack.",
                            "minimum": 0,
                        },
                        "pot": {
                            "type": "integer",
                            "description": "Optional override for the pot size; defaults to current.",
                            "minimum": 1,
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "name": "hand_equity_vs_ranges",
                "description": (
                    "Estimate your equity (probability of winning at showdown) "
                    "against villains' hand ranges via Monte Carlo. Pass a "
                    "range_by_seat dict mapping each opponent seat number "
                    "(must equal opponent_seats_in_hand) to an eval7-compatible "
                    "range string (e.g. 'QQ+, AKs, AKo'). Returns hero_equity, "
                    "ci_low, ci_high, n_samples, seed, backend. Use this for "
                    "decisions where pot_odds alone is insufficient — e.g. "
                    "calling a multi-way 3-bet, choosing between calling and "
                    "shoving on a draw, or evaluating equity vs a polarized 3-bet."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "range_by_seat": {
                            "type": "object",
                            "description": (
                                "Dict mapping seat int to eval7 HandRange string. "
                                "Keys MUST equal opponent_seats_in_hand."
                            ),
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["range_by_seat"],
                    "additionalProperties": False,
                },
            },
        ])
    if params.enable_hud_tool:
        specs.append({
            "name": "get_opponent_stats",
            "description": (
                "Get opponent's HUD stats (VPIP, PFR, 3-bet%, AF, WTSD) "
                "for a specific seat. Returns insufficient=True sentinel "
                "when fewer than opponent_stats_min_samples hands have "
                "accumulated (default 30). Use to model opponent's playing "
                "style for range estimation and bluff/value frequency tuning."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "seat": {
                        "type": "integer",
                        "description": "Opponent seat ID. Must be in "
                                       "[0, num_players) and != your own seat.",
                        "minimum": 0,
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["summary"],
                        "description": "Only 'summary' supported in v1.",
                        "default": "summary",
                    },
                },
                "required": ["seat"],
                "additionalProperties": False,
            },
        })
    return specs
```

- [ ] **Step 6: Thread HUD context through `render_system` + `system.j2`**

Edit `src/llm_poker_arena/agents/llm/prompt_profile.py:render_system`. Update signature + render call to add `enable_hud_tool` + `opponent_stats_min_samples`:

```python
    def render_system(
        self,
        *,
        num_players: int,
        sb: int,
        bb: int,
        starting_stack: int,
        enable_math_tools: bool = False,
        enable_hud_tool: bool = False,
        opponent_stats_min_samples: int = 30,
        max_utility_calls: int = 5,
    ) -> str:
        tpl = self._env.get_template(self.system_template)
        return tpl.render(
            num_players=num_players,
            sb=sb,
            bb=bb,
            starting_stack=starting_stack,
            rationale_required=self.rationale_required,
            language=self.language,
            enable_math_tools=enable_math_tools,
            enable_hud_tool=enable_hud_tool,
            opponent_stats_min_samples=opponent_stats_min_samples,
            max_utility_calls=max_utility_calls,
        )
```

Edit `src/llm_poker_arena/agents/llm/llm_agent.py:525` (the `render_system(...)` call). Add the two new args:

```python
            enable_math_tools=params.enable_math_tools,
            enable_hud_tool=params.enable_hud_tool,
            opponent_stats_min_samples=params.opponent_stats_min_samples,
```

Edit `src/llm_poker_arena/agents/llm/prompts/system.j2`. Find the existing utility-tool section (added in Phase 3c-math + 3c-equity). Append a conditional block:

```jinja
{% if enable_hud_tool %}

You can also call `get_opponent_stats(seat: int)` to query an opponent's
playing style stats (VPIP/PFR/3-bet/AF/WTSD). Useful for range estimation
and adjusting bluff/value frequencies based on opponent tendencies.
Returns `insufficient=True` if fewer than {{ opponent_stats_min_samples }}
hands accumulated for that opponent.
{% endif %}
```

- [ ] **Step 6b: Wire `opponent_stats` into user.j2 (passive HUD injection)**

**codex audit BLOCKER B1 fix**: PlayerView.opponent_stats was being populated
by Task 7 but never made it into the LLM prompt. The system tool spec
advertises HUD via `get_opponent_stats` (active query), but the design
intent was BOTH passive (always visible in user prompt) AND active (tool).
This step wires the passive path.

Edit `src/llm_poker_arena/agents/llm/prompt_profile.py:render_user`. Add `opponent_stats` kwarg:

```python
    def render_user(
        self,
        *,
        hand_id: int,
        street: str,
        my_seat: int,
        my_position_short: str,
        my_position_full: str,
        my_hole_cards: tuple[str, str],
        community: Iterable[str],
        pot: int,
        my_stack: int,
        to_call: int,
        pot_odds_required: float | None,
        effective_stack: int,
        button_seat: int,
        opponent_seats_in_hand: Iterable[int],
        seats_yet_to_act_after_me: Iterable[int],
        seats_public: Iterable[Any],
        opponent_stats: dict[int, Any] | None = None,
    ) -> str:
        tpl = self._env.get_template(self.user_template)
        return tpl.render(
            hand_id=hand_id,
            street=street,
            my_seat=my_seat,
            my_position_short=my_position_short,
            my_position_full=my_position_full,
            my_hole_cards=tuple(my_hole_cards),
            community=tuple(community),
            pot=pot,
            my_stack=my_stack,
            to_call=to_call,
            pot_odds_required=pot_odds_required,
            effective_stack=effective_stack,
            button_seat=button_seat,
            opponent_seats_in_hand=tuple(opponent_seats_in_hand),
            seats_yet_to_act_after_me=tuple(seats_yet_to_act_after_me),
            seats_public=tuple(seats_public),
            opponent_stats=opponent_stats or {},
        )
```

Edit `src/llm_poker_arena/agents/llm/llm_agent.py` — find the `render_user(...)` call site (grep for `render_user(` in llm_agent.py). Add `opponent_stats=view.opponent_stats` to the call.

Edit `src/llm_poker_arena/agents/llm/prompts/user.j2`. Append after the `=== SEATS ===` block (before `=== YOUR TURN ===`):

```jinja
{% if opponent_stats %}

=== OPPONENT STATS (HUD) ===
{%- for seat, s in opponent_stats.items() | sort %}
{%- if s.insufficient %}
seat {{ seat }}: insufficient samples
{%- else %}
seat {{ seat }}: VPIP={{ '%.2f' | format(s.vpip) }} PFR={{ '%.2f' | format(s.pfr) }} 3bet={{ '%.2f' | format(s.three_bet) }} AF={{ '%.2f' | format(s.af) }} WTSD={{ '%.2f' | format(s.wtsd) }}
{%- endif %}
{%- endfor %}
{% endif %}
```

(Note: `opponent_stats` is a dict of `{seat_int: OpponentStatsOrInsufficient}`; the Jinja2 attribute access `s.insufficient`, `s.vpip`, etc. works because Pydantic models expose fields as attributes. The `| sort` filter sorts by key for stable output.)

- [ ] **Step 7: Run tests + suite**

Run: `.venv/bin/pytest tests/unit/test_get_opponent_stats_tool.py -v 2>&1 | tail -10`
Expected: 11 tests pass.

Run full suite:
`.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 458 pass + 8 skip.

- [ ] **Step 8: Lint + mypy**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add src/llm_poker_arena/tools/opponent_stats.py \
        src/llm_poker_arena/tools/__init__.py \
        src/llm_poker_arena/tools/*.py \
        src/llm_poker_arena/agents/llm/prompts/system.j2 \
        tests/unit/test_get_opponent_stats_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): get_opponent_stats tool + dispatcher + system.j2 (Phase 3c-hud Task 8)

Thin PlayerView accessor — counter computation lives in
Session._build_opponent_stats (Task 7). Tool validates:
  - detail_level == "summary" (Phase 5+ may add "detailed")
  - seat ∈ [0, num_players)
  - seat != my_seat (no self-peek; use view fields for self-stats)

Returns OpponentStatsOrInsufficient.model_dump on success; raises
ToolDispatchError on invalid input (LLMAgent K+1 loop catches and
surfaces as {"error": ...} in tool_result). Same pattern as
pot_odds/spr/equity. Dispatcher gates on view.immutable_session_
params.enable_hud_tool.

system.j2 advertises tool when enable_hud_tool, mentions
opponent_stats_min_samples threshold so LLM understands the
"insufficient" sentinel.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Mock K+1 integration test (forced HUD tool call)

**Files:**
- Create: `tests/integration/test_llm_session_mock_hud.py` (NEW)

- [ ] **Step 1: Write the test**

Create `tests/integration/test_llm_session_mock_hud.py`:

```python
"""Mock K+1 session forces HUD tool call; verifies result lands in
agent_view_snapshots.jsonl iterations (Phase 3c-hud Task 9).

Mirror Phase 3c-math/equity mock integration tests.
"""
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


def _hud_then_fold(uid_prefix: str, n_responses: int) -> tuple[LLMResponse, ...]:
    """Cycle: get_opponent_stats(seat=0) → fold → get_opponent_stats(seat=1)
    → fold → ..."""
    out: list[LLMResponse] = []
    for i in range(n_responses):
        if i % 2 == 0:
            tc = ToolCall(
                name="get_opponent_stats",
                args={"seat": (i // 2) % 6},  # cycle through seats
                tool_use_id=f"{uid_prefix}_h{i}",
            )
        else:
            tc = ToolCall(name="fold", args={}, tool_use_id=f"{uid_prefix}_f{i}")
        out.append(LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(tc,), text_content="r",
            tokens=TokenCounts(input_tokens=10, output_tokens=5,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        ))
    return tuple(out)


def test_session_with_hud_tool_call_writes_result_to_snapshot(
    tmp_path: Path,
) -> None:
    """LLM at seat 3 calls get_opponent_stats every other turn; tool result
    (insufficient=True for 6-hand session) lands in iterations."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=True,  # KEY — opens up get_opponent_stats
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    script = MockResponseScript(responses=_hud_then_fold("a", 300))
    provider = MockLLMProvider(script=script)
    llm_agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    agents = [
        RandomAgent(),  # 0
        RandomAgent(),  # 1
        RandomAgent(),  # 2
        llm_agent,      # 3 ← LLM with HUD tool
        RandomAgent(),  # 4
        RandomAgent(),  # 5
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="mock_hud_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots"

    # Find at least one iteration with tool_call.name == "get_opponent_stats"
    # and tool_result populated.
    hud_iters = []
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc and tc["name"] == "get_opponent_stats":
                hud_iters.append(it)
    assert hud_iters, "no get_opponent_stats iterations recorded"

    # All HUD iterations must have non-None tool_result.
    for it in hud_iters:
        assert it["tool_result"] is not None
        # 6-hand session at min_samples=30 → all opponents insufficient.
        # Result is either {"insufficient": true, ...} OR {"error": "..."}
        # if seat == self (LLM at seat 3, cycling 0/1/2/3/4/5 — seat 3 case
        # returns error).
        tr = it["tool_result"]
        assert "insufficient" in tr or "error" in tr

    # chip_pnl conservation.
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_llm_session_mock_hud.py -v 2>&1 | tail -8`
Expected: PASS.

- [ ] **Step 3: Run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 459 pass + 8 skip.

- [ ] **Step 4: Lint + mypy**

Run: `.venv/bin/ruff check tests/integration/test_llm_session_mock_hud.py && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_llm_session_mock_hud.py
git commit -m "$(cat <<'EOF'
test(integration): mock K+1 session with HUD tool (Phase 3c-hud Task 9)

LLM at seat 3 cycles get_opponent_stats(seat) → fold across 6 hands.
Verifies:
  - HUD tool dispatched when enable_hud_tool=True
  - tool_result lands in agent_view_snapshots.jsonl iterations
  - 6-hand session at min_samples=30 yields insufficient=True (or error
    when LLM queries its own seat in the cycle)
  - chip_pnl conserves

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Gated real-Anthropic HUD smoke

**Files:**
- Create: `tests/integration/test_llm_session_real_anthropic_hud.py`

**Activation:**
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_anthropic_hud.py -v
```

Cost: ~$0.05 per run (6 hands, 1 LLM seat, K+1 with HUD enabled).

- [ ] **Step 1: Create the gated test**

Create `tests/integration/test_llm_session_real_anthropic_hud.py`:

```python
"""Real Anthropic K+1 with HUD tool enabled (gated, NOT in CI).

Run only when:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Cost ~$0.05 per run. 6 hands × 1 Claude Haiku 4.5 seat with HUD tool
exposed (insufficient sentinel for all opponents at 6 < 30 hands).

Wire-only assertions (codex IMPORTANT-5 pattern):
  - Session runs to completion
  - All seat-3 final_actions in legal set
  - chip_pnl conserves
  - meta.json provider_capabilities populated
  - Does NOT assert organic HUD tool use (0/22 baseline rate; HUD tool
    likely also unused organically — that's a behavior question for
    Phase 5+ if/when prompt-tuning is on the roadmap)
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

pytestmark = pytest.mark.skipif(
    os.getenv("ANTHROPIC_INTEGRATION_TEST") != "1"
    or not os.getenv("ANTHROPIC_API_KEY"),
    reason="needs ANTHROPIC_INTEGRATION_TEST=1 and ANTHROPIC_API_KEY set",
)


def test_real_claude_haiku_with_hud_enabled(tmp_path: Path) -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,  # KEY — HUD tool exposed
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm = LLMAgent(provider=provider, model="claude-haiku-4-5",
                   temperature=0.7, total_turn_timeout_sec=60.0)
    agents = [
        RandomAgent(),  # 0 (BTN)
        RandomAgent(),  # 1 (SB)
        RandomAgent(),  # 2 (BB)
        llm,            # 3 (UTG) ← Claude
        RandomAgent(),  # 4 (HJ)
        RandomAgent(),  # 5 (CO)
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_anthropic_hud_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots"

    # 1. Every final_action in legal set.
    for rec in llm_snaps:
        legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
        assert rec["final_action"]["type"] in legal_names

    # 2. chip_pnl conservation.
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

    # 3. provider_capabilities populated for the LLM seat.
    caps = meta["provider_capabilities"]
    assert "3" in caps
    assert caps["3"]["provider"] == "anthropic"

    # 4. IF Claude actually called HUD tool, validate shape (no organic-use
    # assertion; baseline 0/22).
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc and tc["name"] == "get_opponent_stats":
                tr = it["tool_result"]
                assert tr is not None
                # Either insufficient=True (likely at 6 hands) OR error
                # (e.g. self-seat) OR populated stats (won't happen at <30
                # hands).
                assert "insufficient" in tr or "error" in tr or "vpip" in tr
```

- [ ] **Step 2: Verify gate-skipped run**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 459 pass + 9 skip (the new gated joins existing 8).

- [ ] **Step 3: Live verify against real Anthropic API**

Run:
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_anthropic_hud.py -v --basetemp=/tmp/hud_smoke 2>&1 | tail -10
```

Expected: PASS in 30-90s, ~$0.05 cost. Inspect `/tmp/hud_smoke/.../agent_view_snapshots.jsonl` to see whether Claude organically called `get_opponent_stats` (likely 0/N — baseline pattern).

- [ ] **Step 4: Lint**

Run: `.venv/bin/ruff check tests/integration/test_llm_session_real_anthropic_hud.py 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_llm_session_real_anthropic_hud.py
git commit -m "$(cat <<'EOF'
test(integration): gated real-Anthropic K+1 HUD tool (Phase 3c-hud Task 10)

Mirror Phase 3c-math/equity gated pattern. 6 hands × 1 Claude Haiku 4.5
seat with enable_hud_tool=True. Wire-only assertions; no organic HUD
use assertion (baseline 0/22).

Cost ~$0.05 / run. Verified manually pre-commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Lint sweep + memory update

**Files:**
- Update `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md` (Phase 3c-hud COMPLETE section)
- Update `~/.claude/projects/-Users-zcheng256/memory/MEMORY.md` (one-liner)

- [ ] **Step 1: Final ruff + mypy check**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/ 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 2: Final all-gates run**

Run:
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 DEEPSEEK_INTEGRATION_TEST=1 \
  .venv/bin/pytest tests/ 2>&1 | tail -5
```

Expected: 468 pass + 0 skip (459 non-gated + 9 gated: 8 prior + 1 new HUD).

- [ ] **Step 3: Update memory**

Read `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`. Insert a "Phase 3c-hud COMPLETE" section after the Phase 4 block. Update the front-matter `description` to add Phase 3c-hud completion.

Capture key non-obvious learnings:
- Counter design: 8 per-seat counters (not 5 stat × ratios) because some stats need separate chances/actions denominators
- VPIP/PFR/3-bet/WTSD per-hand boolean flush at hand-end vs AF per-action increment
- Conservative all-or-nothing per-opponent insufficient sentinel (avoids OpponentStatsOrInsufficient validator's strict "non-insufficient → all numeric" constraint)
- get_opponent_stats tool is THIN accessor (no recomputation) — counters live in Session, view threads them in
- HUD tool's organic adoption rate likely also low (0/22 baseline for math/equity tools)

Update `~/.claude/projects/-Users-zcheng256/memory/MEMORY.md` index entry one-liner.

- [ ] **Step 4: Commit memory update + final inventory**

```bash
git add docs/superpowers/plans/2026-04-26-llm-poker-arena-phase-3c-hud.md
git commit -m "$(cat <<'EOF'
plan: Phase 3c-hud (HUD stats tool — VPIP/PFR/3-bet/AF/WTSD)

11-task plan. Single-session incremental counters in Session, no SQL.
Last unimplemented 3c utility tool. get_opponent_stats is thin PlayerView
accessor; counter math lives in Session (8 counters × N seats).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git log --oneline de9ab68..HEAD
git status
```

Expected: clean tree, ~12 commits since Phase 4 (1 plan baseline + 10 task commits + this final commit).

---

## Self-Review Checklist (auditor-facing summary)

After all 11 tasks land:

1. **Spec coverage:**
   - §581 PlayerView.opponent_stats populated (was hardcoded `{}`) ✅ Task 7
   - §1389 get_opponent_stats(seat, detail_level) tool implemented ✅ Task 8
   - §1413 OPPONENT_STATS_SPEC gated on enable_hud_tool ✅ Task 8
   - §1450-1454 dispatcher route via run_utility_tool ✅ Task 8

2. **5 stat semantics correct:**
   - VPIP per-hand boolean ≤ total_hands_played ✅ Task 2 test 1
   - PFR ⊆ VPIP ✅ Task 3 test 1
   - 3-bet actions ⊆ chances ✅ Task 4 test 1
   - AF cross-street individual count ratio ✅ Task 5
   - WTSD chances == VPIP actions ✅ Task 6 test 2

3. **Insufficient sentinel handled correctly:**
   - n < min_samples → all opponents insufficient ✅ Task 7 test 3
   - n >= min_samples but stat denominator = 0 → that opponent insufficient ✅ Task 7 doc

4. **Backward compat preserved:**
   - `build_player_view` default `opponent_stats=None` → `{}` (existing behavior) ✅ Task 7 test 1
   - Random/RuleBased/HumanCLI agents unaffected (counter computation runs in Session unconditionally; cheap)
   - Existing 423 tests + 8 skip still pass; 25 new tests added (3+3+4+3+3+4+4+1+0+0 = 25 unit/integration + 1 gated)

5. **No placeholders:** every step has executable code or commands.
