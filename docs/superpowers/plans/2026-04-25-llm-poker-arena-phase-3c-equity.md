# Phase 3c-equity: hand_equity_vs_ranges Tool + Eval7Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (inline mode chosen by user) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `hand_equity_vs_ranges` utility tool (multi-way MC equity estimation against villain ranges) to LLMAgent's K+1 ReAct loop, gated on `SessionConfig.enable_math_tools=True`. Shipping the equity tool completes the `llm_math` baseline's tool surface (pot_odds + spr from 3c-math; equity now) so we can run `llm_math vs llm_math` head-to-head sessions and observe whether multi-LLM tool usage frequency differs from the 0-organic-call baseline observed in Phase 3c-math's single-LLM test.

**Architecture:**
- New `EquityBackend` ABC in `tools/equity_backend.py` with one concrete `Eval7Backend` impl. Spec §5.2.2 defines this ABC; we ship the minimum viable subset (one method on the ABC; one impl). `EquityBackend` is coupled to eval7's `Card` type at the boundary — documented spec deviation, future `TreysBackend` would re-implement card conversion.
- New `tools/equity.py` with `hand_equity_vs_ranges(view, range_by_seat, *, n_samples=5000, seed=None) -> EquityResult` function. Multi-way MC algorithm implemented at module level (eval7 ships only HU MC; we hand-roll N-way using eval7's `evaluate()` + `HandRange.hands` as primitives, ~30 LOC). HU case = N=1 villain (degenerate dict), reuses same code path.
- New `EquityResult` Pydantic frozen dataclass in `agents/llm/types.py` (alongside existing types).
- Extend `tools/runner.py:run_utility_tool` and `utility_tool_specs` to dispatch the new tool. Stateless function pattern continues — `Eval7Backend()` instantiated per call (cheap; module function wrapper).
- Extend `prompts/system.j2` with one block describing `hand_equity_vs_ranges` API + when to use.
- LLMAgent and Session unchanged — Phase 3c-math K+1 loop already supports any utility tool name registered in `utility_names`.

**Tech Stack:**
- New dep: `eval7>=0.1.10,<0.2.0` (pre-built wheel for Python 3.12 macOS universal2 verified working pre-plan)
- Reuses Phase 3c-math's `tools/` subpackage architecture
- Pydantic 2 frozen DTOs, mypy --strict, ruff

---

## Phase 3c-equity Scope Decisions (locked via brainstorming 2026-04-25)

These decisions captured user input from a 4-question brainstorming pass. They are **not** open to re-litigation during execution; codex audit may surface secondary issues but should not reverse these primary calls.

1. **EquityBackend = eval7**: pre-built wheel installs cleanly on M-series Mac (verified `pip install eval7` produced `eval7-0.1.10-cp312-cp312-macosx_10_9_universal2.whl` from PyPI; no C compilation needed). Speed ~5M hand evaluations/sec. Treys (~50K/s) and pokerkit-built-in (~20K/s) are order-of-magnitude slower; not viable for gated multi-LLM smoke test.
2. **Multi-way only**: spec §5.2.3 main API is `hand_equity_vs_ranges(range_by_seat: dict[int, str])`. HU is the degenerate single-key case. NOT shipping the spec's HU alias `hand_equity_vs_range(villain_range: str)` — one less API surface for LLM to confuse + spec §5.2.3 already says HU is multi-way's special case.
3. **Trust eval7 raw HandRange parser**: pass LLM range strings directly to `eval7.HandRange(s)`; on `RangeStringError` wrap as `ToolDispatchError` with the original message for LLM feedback. NOT writing our own parser — eval7's syntax is industry-standard (PokerStove/Equilab compatible) and Claude has likely seen it in training. Verified during brainstorming probe: `eval7.HandRange` rejects `"100%"` natively, so the catch-all abuse vector codex IMPORTANT-3 in 3c-math worried about doesn't exist here.
4. **Minimal LLM API**: tool spec exposes ONLY `range_by_seat` (no `n_samples`, no `seed_override`). n_samples hardcoded 5000 (spec §5.2.3 default). Seed derived server-side from `view.turn_seed` for spec §11.1 reproducibility. LLM cannot tune precision — but eval7 at 5000 samples runs in ~5-15ms, so there's no latency reason for LLM to want a knob.

## Spec Inconsistencies to Reconcile (DOCUMENT, do not silently choose)

1. **Spec §5.2.2 EquityBackend ABC's Card type abstraction** — spec implies the ABC should be backend-agnostic at the Card boundary, but our `EquityBackend.evaluate(cards: tuple[eval7.Card, ...])` couples to eval7's native Card type. Justification: card conversion (CardStr → eval7.Card) inside the MC inner loop costs ~5% perf overhead (5000 iter × 6 evaluates × 7 cards = 210K conversions per equity call). For 3c-equity MVP with one backend, the coupling is acceptable. Future TreysBackend would force introducing a backend-internal Card adapter — refactor when needed. **Document in Task 1 commit.**
2. **Spec §5.2.3 LLM-callable args** — spec function signature has `n_samples=5000, seed_override=None` as kwargs, but the JSON tool input_schema we expose to LLM only has `range_by_seat`. The Python function still accepts `n_samples` + `seed_override` for testing/tuning, just not exposed to the LLM. Justification: brainstorming Q4 decision — LLM has no intuition for sample size or RNG seeding; exposing adds error surface without value. **Document in Task 4 commit.**

## Spec Items Deferred (NOT in Phase 3c-equity)

- **3c-hud** (next phase): `get_opponent_stats`, `view.opponent_stats` populated from Phase 2b SQL aggregates with time-window leak protection, `enable_hud_tool` flag wiring beyond current Phase 1 stub.
- **3e** (carried over from 3b/3c-math): `AgentDescriptor.temperature` / `agent.seed` persistence; `meta.json.retry_summary_per_seat` / `tool_usage_summary` / `total_tokens` aggregation; 1000-hand cost telemetry session.
- **n_samples LLM-callable knob** — could be added later as ablation axis (does giving LLM cost/precision control change behavior?). Phase 3e research question, not 3c-equity scope.
- **TreysBackend / pokerkit-eval backend** — defer until eval7 actually breaks somewhere or speed becomes irrelevant.
- **EquityResult `per_villain_equity: dict[seat, float]`** — could break out hero's equity-share-against-each-villain-individually instead of just hero vs combined field. Spec doesn't require it; YAGNI.

## Risks Acknowledged Up Front

- **Multi-way MC implementation is the highest risk** in this plan (~50 LOC of inner-loop logic with card-overlap edge cases). Mitigated by 5+ unit tests covering invariants: equity ∈ [0, 1], deterministic seed reproducibility, card overlap correctly excluded, HU degenerate case matches eval7's native HU MC within Monte Carlo noise (statistical equivalence test).
- **Claude may not call hand_equity_vs_ranges organically** even with multi-LLM session. Multi-way `range_by_seat` dict args are heavier than pot_odds, and Claude already chose 0/6 utility calls in 3c-math single-LLM test. Gated test follows 3c-math wire-only pattern (no frequency assertion); if 0 organic calls happen, that's data — not a test failure.
- **eval7 `HandRange.hands` API may change between versions** (currently 0.1.10). Pinned to `>=0.1.10,<0.2.0` in pyproject. If a 0.2 release breaks the API, we re-pin or refactor.
- **No backward-incompat risk**: the new tool is purely additive. `enable_math_tools=False` sessions don't see it. Existing 21 K=0 ReAct tests + 9 K+1 tests untouched.

---

## File Structure

**New files:**
- `src/llm_poker_arena/tools/equity_backend.py` — `EquityBackend` ABC + `Eval7Backend` concrete impl. ~60 LOC.
- `src/llm_poker_arena/tools/equity.py` — `hand_equity_vs_ranges()` function + multi-way MC algorithm + helpers (combo cap, range parsing). ~120 LOC.

**New tests:**
- `tests/unit/test_equity_backend.py` — Eval7Backend.evaluate basic correctness vs known eval7 outputs (e.g., AAA over KK over QQ).
- `tests/unit/test_multi_way_mc.py` — multi-way MC invariants: equity ∈ [0, 1], determinism with seed, card overlap excluded, HU=multi-way[1 villain] within MC noise of eval7 native HU MC.
- `tests/unit/test_hand_equity_vs_ranges_tool.py` — full tool integration: keys validation, range parsing, combo cap, EquityResult round-trip, ToolDispatchError on bad input.
- `tests/unit/test_run_utility_tool.py` — extend with equity dispatch test.
- `tests/unit/test_utility_tool_specs.py` — extend with equity spec assertion.
- `tests/unit/test_llm_agent_react_loop_k1.py` — extend with mock K+1 test where LLM calls hand_equity_vs_ranges.
- `tests/integration/test_llm_session_real_anthropic_math_equity.py` — gated, multi-LLM (2 Claude seats so equity has more potential signal than 3c-math's 1-LLM test). Wire-only assertions.

**Modified files:**
- `pyproject.toml` — add `eval7>=0.1.10,<0.2.0` to dependencies.
- `src/llm_poker_arena/agents/llm/types.py` — add `EquityResult` Pydantic frozen class.
- `src/llm_poker_arena/tools/__init__.py` — re-export new symbols (`hand_equity_vs_ranges`, `EquityResult` if needed externally).
- `src/llm_poker_arena/tools/runner.py` — add `hand_equity_vs_ranges` to `_ALLOWED_ARGS`, add dispatch branch in `run_utility_tool`, add tool spec to `utility_tool_specs`.
- `src/llm_poker_arena/agents/llm/prompts/system.j2` — add `hand_equity_vs_ranges` description in the `{% if enable_math_tools %}` block.

**Files NOT touched** (intentionally):
- `src/llm_poker_arena/agents/llm/llm_agent.py` — K+1 loop already dispatches any name in `utility_names`. Adding equity to `utility_tool_specs` is sufficient.
- `src/llm_poker_arena/session/session.py` — Session contract unchanged.
- `src/llm_poker_arena/storage/layer_builders.py` — `tool_result` already in IterationRecord (Phase 3c-math); EquityResult.model_dump() flows through.
- Existing pot_odds.py / spr.py — independent tools, no integration.

---

## Test Counts (cumulative, baseline = 381 pass + 6 skip after Phase 3c-math)

After each task, the expected suite counts:

| Task | New tests | Cumulative pass | Cumulative skip |
|---|---|---|---|
| 0 | 0 (deps + scaffold) | 381 | 6 |
| 1 | 3 (Eval7Backend.evaluate basic correctness) | 384 | 6 |
| 2 | 7 (MC invariants: range/determinism/different-seeds/HU equiv/seat-order-invariant [BLOCKER B1 regression]/3-way-tie-share=1/3 [BLOCKER B2 regression]/empty-pool) | 391 | 6 |
| 3 | 2 (EquityResult round-trip + range validation) | 393 | 6 |
| 4 | 7 (tool: HU + multi-way + missing-seat + extra-seat + combo cap + parse error + weighted-reject [IMPORTANT-1]) | 400 | 6 |
| 5 | 1 (dispatcher new branch test) | 401 | 6 |
| 6 | 1 (utility_tool_specs includes equity) | 402 | 6 |
| 7 | 1 (system.j2 mentions hand_equity_vs_ranges) | 403 | 6 |
| 8 | 2 (mock K+1 test calling equity + integration session asserting ≥1 success [IMPORTANT-2]) | 405 | 6 |
| 9 | 0 unit + 1 gated | 405 | 7 |
| 10 | 0 (lint cleanup) | 405 | 7 |

**Final all-gates-on**: 412 pass + 0 skip (405 non-gated + 7 gated: 6 prior + 1 new equity).

---

## Task 0: Add `eval7` dep + scaffold equity_backend.py + equity.py skeletons

**Files:**
- Modify: `pyproject.toml:11-19` (dependencies)
- Create: `src/llm_poker_arena/tools/equity_backend.py` (skeleton)
- Create: `src/llm_poker_arena/tools/equity.py` (skeleton)

- [ ] **Step 1: Add eval7 to pyproject + mypy override**

Edit `pyproject.toml`. Insert `eval7>=0.1.10,<0.2.0` between `duckdb` and `jinja2`:

```toml
dependencies = [
    "anthropic>=0.34,<1.0",
    "duckdb>=1.0,<2.0",
    "eval7>=0.1.10,<0.2.0",
    "jinja2>=3.1,<4.0",
    "matplotlib>=3.8,<4.0",
    "openai>=1.0,<2.0",
    "pokerkit>=0.7,<0.8",
    "pydantic>=2.0",
]
```

Also add eval7 to mypy overrides (eval7 lacks type stubs, like pokerkit). Add this section to pyproject.toml after the existing `[[tool.mypy.overrides]]` block for pokerkit:

```toml
[[tool.mypy.overrides]]
module = "eval7.*"
ignore_missing_imports = true
```

- [ ] **Step 2: Install the dep**

Run: `.venv/bin/pip install -e .`
Expected: `Successfully installed eval7-0.1.10 future-1.0.0` (future is eval7's only transitive dep).

Verify import:
```bash
.venv/bin/python -c "import eval7; print(eval7.HandRange('QQ+').hands[:1])"
```
Expected output: `[((Card("Qd"), Card("Qc")), 1.0)]`.

- [ ] **Step 3: Create `equity_backend.py` skeleton**

Create `src/llm_poker_arena/tools/equity_backend.py`:

```python
"""EquityBackend ABC + Eval7Backend impl (spec §5.2.2 minimal subset).

Spec defines an EquityBackend interface meant to be backend-agnostic at
the Card boundary. Phase 3c-equity ships ONE backend (eval7) and accepts
the spec deviation: EquityBackend.evaluate is typed against eval7.Card
directly, NOT abstracted to CardStr. Justification: card-string-to-eval7-Card
conversion inside the 5000-iteration MC loop costs measurable overhead
(~210K conversions per equity call). Future TreysBackend would force
introducing a backend-internal Card adapter — refactor when actually needed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import eval7


class EquityBackend(ABC):
    """spec §5.2.2: pluggable hand evaluator + (someday) range parser."""

    @abstractmethod
    def evaluate(self, cards: tuple["eval7.Card", ...]) -> int:
        """Return the hand rank (higher = stronger) for a 5-7 card hand.
        Backend-defined integer scale; only relative ordering matters."""


class Eval7Backend(EquityBackend):
    """Concrete backend wrapping eval7's C-extension hand evaluator."""

    def evaluate(self, cards: tuple["eval7.Card", ...]) -> int:
        import eval7
        return int(eval7.evaluate(list(cards)))


__all__ = ["EquityBackend", "Eval7Backend"]
```

- [ ] **Step 4: Create `equity.py` skeleton**

Create `src/llm_poker_arena/tools/equity.py`:

```python
"""hand_equity_vs_ranges multi-way Monte Carlo equity tool (spec §5.2.3).

Phase 3c-equity skeleton — implementations land in Tasks 2 and 4.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llm_poker_arena.engine.views import PlayerView


def hand_equity_vs_ranges(
    view: "PlayerView",
    range_by_seat: dict[int, str],
    *,
    n_samples: int = 5000,
    seed: int | None = None,
) -> dict[str, Any]:
    """Compute hero equity vs villain ranges via multi-way Monte Carlo.

    spec §5.2.3 main API. range_by_seat keys MUST equal
    view.opponent_seats_in_hand (Task 4 enforces). Returns EquityResult
    dump (dict).
    """
    raise NotImplementedError(
        "Phase 3c-equity Tasks 2-4 implement multi-way MC + tool wrapping."
    )


__all__ = ["hand_equity_vs_ranges"]
```

- [ ] **Step 5: Sanity-run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 381 pass + 6 skip (no test changes; new files not yet imported by tests).

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/ && .venv/bin/mypy --strict src/llm_poker_arena/tools/`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/llm_poker_arena/tools/equity_backend.py src/llm_poker_arena/tools/equity.py
git commit -m "$(cat <<'EOF'
chore(deps): add eval7 + scaffold equity_backend/equity skeletons (Phase 3c-equity Task 0)

eval7 0.1.10 ships pre-built wheels for Python 3.12 macOS universal2 +
Linux x86_64 — no C compilation needed for our M-series dev/CI
environments. Pinned >=0.1.10,<0.2.0 to bound ABI risk.

Spec §5.2.2 EquityBackend ABC + Eval7Backend impl skeleton; Phase
3c-equity will fill in evaluate() + multi-way MC algorithm. Spec
deviation: EquityBackend.evaluate is typed against eval7.Card (not
abstracted CardStr) — card conversion overhead inside the MC loop
isn't worth abstracting until we actually have a 2nd backend.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Implement `Eval7Backend.evaluate` + tests

**Files:**
- Modify: `src/llm_poker_arena/tools/equity_backend.py` (Eval7Backend already in skeleton — verify it works)
- Test: `tests/unit/test_equity_backend.py` (NEW)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_equity_backend.py`:

```python
"""Eval7Backend basic correctness — relative hand ordering.

eval7.evaluate returns higher integers for stronger hands. We assert the
ordering of well-known holdem hand ranks rather than specific values
(eval7's exact ranking constants are an implementation detail).
"""
from __future__ import annotations

import eval7

from llm_poker_arena.tools.equity_backend import Eval7Backend


def _cards(*names: str) -> tuple[eval7.Card, ...]:
    return tuple(eval7.Card(n) for n in names)


def test_eval7_backend_evaluate_higher_for_stronger_hand() -> None:
    backend = Eval7Backend()
    # AAA full vs straight on same board.
    aces_full = backend.evaluate(_cards("Ah", "Ad", "As", "Ac", "Kh", "Kd", "2c"))
    straight = backend.evaluate(_cards("Th", "Jh", "Qh", "Kh", "Ad", "5c", "2c"))
    assert aces_full > straight


def test_eval7_backend_evaluate_pair_beats_high_card() -> None:
    backend = Eval7Backend()
    pair = backend.evaluate(_cards("As", "Ad", "Kh", "Qc", "Jd", "9s", "7c"))
    high = backend.evaluate(_cards("As", "Kc", "Qd", "Jh", "9s", "7c", "3d"))
    assert pair > high


def test_eval7_backend_evaluate_returns_int() -> None:
    backend = Eval7Backend()
    rank = backend.evaluate(_cards("As", "Ks", "Qs", "Js", "Ts", "2c", "3d"))
    assert isinstance(rank, int)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_equity_backend.py -v`
Expected: 3 tests pass (Eval7Backend skeleton was already complete in Task 0; this task verifies it).

- [ ] **Step 3: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/equity_backend.py tests/unit/test_equity_backend.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/equity_backend.py tests/unit/test_equity_backend.py`
Expected: clean. (eval7 mypy override added preemptively in Task 0 step 1, so untyped imports already silent.)

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_equity_backend.py
git commit -m "$(cat <<'EOF'
test(tools): Eval7Backend basic correctness (Phase 3c-equity Task 1)

Three relative-ordering tests on eval7.evaluate via Eval7Backend wrapper
— assert hand-rank monotonicity (AAA full > straight, pair > high card)
without coupling to eval7's specific rank integer values.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Multi-way MC algorithm in `equity.py`

**Files:**
- Modify: `src/llm_poker_arena/tools/equity.py` (add `_multi_way_equity_mc()` private function)
- Test: `tests/unit/test_multi_way_mc.py` (NEW)

**Why the most consequential task in this plan**: ~30 LOC of MC inner loop, easy to get wrong on card-overlap edge cases. 5 invariant tests cover the failure surface.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_multi_way_mc.py`:

```python
"""Multi-way MC equity invariants. The algorithm runs rejection sampling:
  - Sample one combo INDEPENDENTLY from each villain's range
  - Reject the WHOLE attempt if any card overlap (codex BLOCKER B1 fix)
  - Sample remaining board cards
  - Evaluate hero + each villain; multi-way tie share = 1/N (codex
    BLOCKER B2 fix)

Tests verify:
  1. Equity is in [0, 1]
  2. Same seed → identical equity (determinism for spec §11.1)
  3. Different seeds → different equity (sanity that MC is actually random)
  4. HU degenerate case matches eval7's native HU MC within MC noise
  5. Seat order invariant (BLOCKER B1 regression)
  6. 3-way all-tie hero share = 1/3 (BLOCKER B2 regression)
  7. Empty villain pool (max_attempts trips) → graceful (0.0, 0.0, 0)
"""
from __future__ import annotations

import eval7
import pytest

from llm_poker_arena.tools.equity import _multi_way_equity_mc
from llm_poker_arena.tools.equity_backend import Eval7Backend


def _cards(*names: str) -> tuple[eval7.Card, ...]:
    return tuple(eval7.Card(n) for n in names)


def test_multi_way_mc_equity_in_unit_interval() -> None:
    """AKs vs QQ+ HU preflop. Equity should be a valid probability."""
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    villain_pools = [tuple(eval7.HandRange("QQ+").hands)]
    backend = Eval7Backend()
    eq, var, valid = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                            n_samples=1000, seed=42)
    assert 0.0 <= eq <= 1.0
    assert var >= 0.0  # variance non-negative
    assert valid == 1000  # rejection sampling converges to target


def test_multi_way_mc_deterministic_with_seed() -> None:
    """Same (hero, board, ranges, seed) → identical result. spec §11.1."""
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    villain_pools = [tuple(eval7.HandRange("QQ+, AKs").hands)]
    backend = Eval7Backend()
    eq_a, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                       n_samples=2000, seed=42)
    eq_b, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                       n_samples=2000, seed=42)
    assert eq_a == eq_b


def test_multi_way_mc_different_seeds_differ() -> None:
    """Sanity: MC is actually using the seed (not constant)."""
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    villain_pools = [tuple(eval7.HandRange("QQ+").hands)]
    backend = Eval7Backend()
    eq_a, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                       n_samples=500, seed=1)
    eq_b, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                       n_samples=500, seed=2)
    # MC noise at N=500 ≈ 2.2% SE; two seeds should differ noticeably.
    assert abs(eq_a - eq_b) > 0.001


def test_multi_way_mc_hu_matches_eval7_native_within_mc_noise() -> None:
    """Our HU code path (1 villain in dict) should match eval7's native HU
    MC equity within statistical noise. 95% CI at N=10000 ≈ ±1%."""
    hero_eval7 = list(_cards("As", "Ks"))
    villain_range = eval7.HandRange("QQ+")
    eval7_eq = eval7.py_hand_vs_range_monte_carlo(
        hero_eval7, villain_range, [], 10000,
    )

    hero = tuple(hero_eval7)
    board: tuple[eval7.Card, ...] = ()
    villain_pools = [tuple(villain_range.hands)]
    backend = Eval7Backend()
    our_eq, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                         n_samples=10000, seed=42)
    # Two independent MC samples of same true equity; difference < ±2%
    # (loose bound — the eval7 native MC has its own seed we can't control).
    assert abs(our_eq - eval7_eq) < 0.02


def test_multi_way_mc_seat_order_invariant() -> None:
    """Codex audit BLOCKER B1 regression: rejection sampling MUST be order-
    independent. Swapping seats for the same multiset of ranges must yield
    statistically equivalent equity (within MC noise). Old sequential algorithm
    leaked ~2.2pp bias on this test.
    """
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    pool_qq = tuple(eval7.HandRange("QQ+").hands)
    pool_aks = tuple(eval7.HandRange("AKs, AKo").hands)
    backend = Eval7Backend()

    # Same ranges, different seat order:
    #   - order A: villain1=QQ+, villain2=AKs/o
    #   - order B: villain1=AKs/o, villain2=QQ+
    eq_a, _, _ = _multi_way_equity_mc(hero, board, [pool_qq, pool_aks], backend,
                                       n_samples=10000, seed=42)
    eq_b, _, _ = _multi_way_equity_mc(hero, board, [pool_aks, pool_qq], backend,
                                       n_samples=10000, seed=42)
    # SE at N=10000 ≈ 0.005 → 95% CI ≈ ±0.01. Two independent seeds give
    # different MC noise; assert difference < 0.015 (loose 3-SE bound).
    # Old sequential algorithm gave ~0.022 difference (codex repro).
    assert abs(eq_a - eq_b) < 0.015, (
        f"order-dependent bias detected: eq_a={eq_a:.4f}, eq_b={eq_b:.4f} "
        f"(diff={abs(eq_a-eq_b):.4f}). rejection sampling should be invariant "
        f"to seat ordering."
    )


def test_multi_way_mc_three_way_tie_assigns_one_third_share() -> None:
    """Codex audit BLOCKER B2 regression: in N-way ties, hero's share is
    1/N, NOT 0.5 (which is HU-only). Test sets up a guaranteed all-tie
    scenario: 3 players all hold the same straight (board provides A high
    straight to all because hero+villains have low cards that don't beat
    the straight).

    Constructed scenario: board = AhKhQhJhTh (royal flush ON board). Every
    player ties on the royal — hero share should be 1/3 with 2 villains.
    """
    backend = Eval7Backend()
    hero = _cards("2c", "2d")  # irrelevant — board is royal
    board = _cards("Ah", "Kh", "Qh", "Jh", "Th")
    # Villains hold any non-overlapping low cards.
    pool_v1 = (((eval7.Card("3c"), eval7.Card("3d")), 1.0),)
    pool_v2 = (((eval7.Card("4c"), eval7.Card("4d")), 1.0),)
    eq, _, valid = _multi_way_equity_mc(
        hero, board, [pool_v1, pool_v2], backend,
        n_samples=200, seed=42,
    )
    assert valid > 0
    # All 3 players use the royal on board → 3-way tie every iteration.
    # Hero's share = 1/3.
    assert eq == pytest.approx(1.0 / 3.0, abs=0.01)


def test_multi_way_mc_skips_iterations_when_villain_pool_empty() -> None:
    """If hero blocks the entire villain pool (e.g., hero=AsKs blocks all of
    villain "AsKs" range), MC iterations skip and equity converges to 0
    (no successful sample). NOT a crash."""
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    # Villain range with ONLY AsKs combo, which hero blocks.
    villain_pools = [tuple(eval7.HandRange("AsKs").hands)]
    backend = Eval7Backend()
    eq, _, valid = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                         n_samples=100, seed=42)
    # No villain combo survivable → max_attempts trips without producing
    # any valid sample → returns (0.0, 0.0, 0). Caller (hand_equity_vs_ranges)
    # surfaces as ToolDispatchError; here we just verify the algo returns
    # gracefully without crashing or returning garbage.
    assert eq == 0.0
    assert valid == 0  # rejection-sampled to exhaustion, all rejected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_multi_way_mc.py -v 2>&1 | tail -8`
Expected: FAIL — `ImportError: cannot import name '_multi_way_equity_mc' from 'llm_poker_arena.tools.equity'`.

- [ ] **Step 3: Implement `_multi_way_equity_mc`**

Edit `src/llm_poker_arena/tools/equity.py`. Replace the file with:

```python
"""hand_equity_vs_ranges multi-way Monte Carlo equity tool (spec §5.2.3).

Phase 3c-equity: implementation. eval7 ships only HU MC primitives
(`py_hand_vs_range_monte_carlo`); we hand-roll the N-way MC algorithm
on top of eval7.evaluate() + HandRange.hands. ~50 LOC including
rejection-sampling correctness machinery.

Algorithm (REJECTION SAMPLING — codex audit BLOCKER B1 fix):
  1. Sample one combo INDEPENDENTLY from each villain's range (no
     conditioning on previously-sampled villains).
  2. Reject the WHOLE attempt if any card overlap occurs (hero ↔ villain,
     board ↔ villain, or villain ↔ villain).
  3. Sample remaining board cards from the unused deck.
  4. Evaluate hero + each villain. Multi-way tie accounting (codex audit
     BLOCKER B2 fix): hero's share = 1 / N if N players tie for best
     hand (HU=0.5 is just N=2 special case); 0 if hero doesn't tie for
     best. Equity = sum(shares) / valid_samples.
  5. Continue until `valid_samples == n_samples` OR `attempts >= max_attempts`
     (10× n_samples cap on pathological setups).

Why rejection (not sequential conditioning): sequential filtering biases
toward villain combos that don't block later villains. Codex demonstrated
empirically that swapping seat order changes equity by ~2.2pp under the
old algorithm. Rejection sampling draws from the true joint distribution.

Determinism: caller passes `seed`; we use `random.Random(seed)` for all
sampling. Same (hero, board, ranges, seed) → identical equity result
(spec §11.1).

CI calculation (multi-way correctness): each sample contributes a share
∈ {0, 1/N, 2/N, ...}, NOT a Bernoulli outcome. We track sum_x2 to compute
sample variance directly. For HU + no ties, this reduces to the standard
Bernoulli p(1-p)/n formula.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

import eval7

if TYPE_CHECKING:
    from llm_poker_arena.engine.views import PlayerView
    from llm_poker_arena.tools.equity_backend import EquityBackend

# Type alias for a villain combo as returned by eval7.HandRange.hands:
# (combo, weight) where combo = (Card, Card). Phase 3c-equity rejects
# non-1.0 weights at parse time (codex audit IMPORTANT-1) — see
# hand_equity_vs_ranges below.
_RangeCombo = tuple[tuple[eval7.Card, eval7.Card], float]


def _multi_way_equity_mc(
    hero: tuple[eval7.Card, ...],
    board: tuple[eval7.Card, ...],
    villain_pools: list[tuple[_RangeCombo, ...]],
    backend: "EquityBackend",
    *,
    n_samples: int,
    seed: int,
) -> tuple[float, float, int]:
    """Run N-way MC via rejection sampling; return (equity, share_variance,
    valid_samples).

    equity = sum_of_hero_shares / valid_samples (each share in {0, 1/N, ...,
    1} where N = #players tying for best hand).

    share_variance is the SAMPLE variance of hero shares — used by caller
    to compute CI correctly for multi-way ties (Bernoulli p(1-p) is wrong
    when ties yield fractional shares).

    valid_samples is the count of iterations that produced a valid card
    configuration. Rejection sampling continues until valid_samples ==
    n_samples, capped at max_attempts = 10*n_samples to bound pathological
    cases. If max_attempts trips with valid_samples == 0, returns
    (0.0, 0.0, 0) — caller raises ToolDispatchError.
    """
    rng = random.Random(seed)
    full_deck: list[eval7.Card] = []
    for r in eval7.ranks:
        for s in eval7.suits:
            full_deck.append(eval7.Card(r + s))

    hero_list = list(hero)
    board_list = list(board)
    hero_board_set: set[eval7.Card] = set(hero_list) | set(board_list)
    n_board_to_deal = 5 - len(board_list)

    valid_samples = 0
    share_sum = 0.0
    share_sq_sum = 0.0
    max_attempts = max(n_samples * 10, 100)
    attempts = 0

    while valid_samples < n_samples and attempts < max_attempts:
        attempts += 1
        # 1. Sample INDEPENDENTLY from each villain pool (codex BLOCKER B1).
        sampled_villains = [
            rng.choice(pool)[0]  # (combo, weight) → combo
            for pool in villain_pools
        ]
        # 2. Reject the WHOLE attempt on any overlap.
        all_villain_cards = [c for v in sampled_villains for c in v]
        if len(set(all_villain_cards)) != len(all_villain_cards):
            continue  # villain ↔ villain overlap
        if any(c in hero_board_set for c in all_villain_cards):
            continue  # hero/board ↔ villain overlap
        # 3. Sample remaining board cards.
        used = hero_board_set | set(all_villain_cards)
        remaining_deck = [c for c in full_deck if c not in used]
        if len(remaining_deck) < n_board_to_deal:
            continue  # shouldn't happen but safe
        extra_board = rng.sample(remaining_deck, n_board_to_deal)
        full_board = board_list + extra_board
        # 4. Evaluate; multi-way tie accounting (codex BLOCKER B2).
        hero_score = backend.evaluate(tuple(hero_list + full_board))
        villain_scores = [
            backend.evaluate(tuple(list(v) + full_board))
            for v in sampled_villains
        ]
        all_scores = [hero_score] + villain_scores
        best = max(all_scores)
        if hero_score == best:
            n_at_best = sum(1 for s in all_scores if s == best)
            share = 1.0 / n_at_best
        else:
            share = 0.0
        share_sum += share
        share_sq_sum += share * share
        valid_samples += 1

    if valid_samples == 0:
        return 0.0, 0.0, 0
    mean = share_sum / valid_samples
    # Sample variance: E[X²] - E[X]². For binary {0,1} shares (no ties),
    # this reduces to mean*(1-mean) — matches Bernoulli.
    variance = max(0.0, (share_sq_sum / valid_samples) - mean * mean)
    return mean, variance, valid_samples


def hand_equity_vs_ranges(
    view: "PlayerView",
    range_by_seat: dict[int, str],
    *,
    n_samples: int = 5000,
    seed: int | None = None,
) -> dict[str, Any]:
    """Compute hero equity vs villain ranges via multi-way Monte Carlo.

    spec §5.2.3 main API. Task 4 implements full validation + EquityResult
    return shape; this stub raises pending wiring.
    """
    raise NotImplementedError(
        "Phase 3c-equity Task 4 implements hand_equity_vs_ranges wrapping."
    )


__all__ = ["hand_equity_vs_ranges"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_multi_way_mc.py -v 2>&1 | tail -10`
Expected: 7 tests pass.

If `test_multi_way_mc_hu_matches_eval7_native_within_mc_noise` fails with delta > 0.02, the MC algorithm has a bug (most likely: card overlap not properly excluded, or rejection sampling not converging).

If `test_multi_way_mc_seat_order_invariant` fails (BLOCKER B1 regression), the algorithm reverted to sequential conditional sampling — order-dependent bias.

If `test_multi_way_mc_three_way_tie_assigns_one_third_share` fails (BLOCKER B2 regression), the tie accounting is HU-only (`0.5` instead of `1/N`).

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/equity.py tests/unit/test_multi_way_mc.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/equity.py tests/unit/test_multi_way_mc.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/tools/equity.py tests/unit/test_multi_way_mc.py
git commit -m "$(cat <<'EOF'
feat(tools): multi-way MC equity algorithm (Phase 3c-equity Task 2)

eval7 ships only HU MC API; multi-way (≥2 villains) requires hand-rolled
N-way Monte Carlo. ~30 LOC inner loop using eval7.evaluate + HandRange.hands
as primitives. Card-overlap-aware: each iteration filters villain pools to
combos disjoint from hero+board+earlier-sampled-villains; skips
impossible draws.

Determinism via random.Random(seed) — caller passes seed derived from
view.turn_seed (spec §11.1). Five invariant tests: equity ∈ [0,1],
same-seed reproducibility, different-seed divergence, HU degenerate
case matches eval7 native HU MC within MC noise, empty-pool no-crash.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `EquityResult` Pydantic frozen class

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/types.py` (append `EquityResult`)
- Test: `tests/unit/test_llm_types.py` (append round-trip test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_llm_types.py`:

```python
def test_equity_result_round_trip() -> None:
    from llm_poker_arena.agents.llm.types import EquityResult

    er = EquityResult(
        hero_equity=0.4523,
        ci_low=0.4385,
        ci_high=0.4661,
        n_samples=5000,
        seed=12345,
        backend="eval7",
    )
    blob = er.model_dump_json()
    er2 = EquityResult.model_validate_json(blob)
    assert er2 == er
    assert er2.backend == "eval7"


def test_equity_result_validates_equity_range() -> None:
    """hero_equity must be in [0, 1]."""
    from pydantic import ValidationError

    from llm_poker_arena.agents.llm.types import EquityResult

    with pytest.raises(ValidationError):
        EquityResult(hero_equity=1.5, ci_low=0.0, ci_high=1.0,
                     n_samples=5000, seed=0, backend="eval7")
    with pytest.raises(ValidationError):
        EquityResult(hero_equity=-0.1, ci_low=0.0, ci_high=1.0,
                     n_samples=5000, seed=0, backend="eval7")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_llm_types.py::test_equity_result_round_trip -v`
Expected: FAIL — `ImportError: cannot import name 'EquityResult'`.

- [ ] **Step 3: Add `EquityResult` to types.py**

Edit `src/llm_poker_arena/agents/llm/types.py`. Append after `ObservedCapability`:

```python
class EquityResult(BaseModel):
    """spec §5.2.3 + §7.4: multi-way MC equity tool return.

    Hero's equity (win + 0.5 * tie probability) vs the dictionary of
    villain ranges, with 95% normal-approximation CI and forensic
    metadata (n_samples, seed, backend) for reproducibility.
    """

    model_config = _frozen()

    hero_equity: float = Field(ge=0.0, le=1.0)
    ci_low: float = Field(ge=0.0, le=1.0)
    ci_high: float = Field(ge=0.0, le=1.0)
    n_samples: int = Field(gt=0)
    seed: int
    backend: str
```

Verify `Field` is imported at top of types.py. If not, add:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_llm_types.py -v 2>&1 | tail -5`
Expected: 19 prior + 2 new = 21 pass.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py && .venv/bin/mypy --strict src/llm_poker_arena/agents/llm/types.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py
git commit -m "$(cat <<'EOF'
feat(types): EquityResult Pydantic frozen DTO (Phase 3c-equity Task 3)

spec §5.2.3 + §7.4 result shape. Pydantic Field validators enforce
hero_equity / ci_low / ci_high ∈ [0, 1] and n_samples > 0. Used by
hand_equity_vs_ranges (Task 4) as the structured return; flows through
LLMAgent's IterationRecord.tool_result via .model_dump().

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `hand_equity_vs_ranges` tool wrapper + validation

**Files:**
- Modify: `src/llm_poker_arena/tools/equity.py` (replace `hand_equity_vs_ranges` stub with full impl)
- Test: `tests/unit/test_hand_equity_vs_ranges_tool.py` (NEW)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_hand_equity_vs_ranges_tool.py`:

```python
"""hand_equity_vs_ranges full tool integration tests.

Covers spec §5.2.3 strict validation (keys must equal opponent_seats_in_hand),
range parsing via eval7.HandRange (passes through ToolDispatchError on
RangeStringError), combo cap enforcement (codex-style abuse defense), and
EquityResult shape.
"""
from __future__ import annotations

import pytest

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools.equity import hand_equity_vs_ranges
from llm_poker_arena.tools.runner import ToolDispatchError


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _view(*, opponent_seats: tuple[int, ...] = (0, 1, 2, 4, 5),
          community: tuple[str, ...] = ()) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Ks"), community=community,
        pot=250, sidepots=(), my_stack=9_750,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=100 / 350,
        effective_stack=9_750,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                           position_full="x", stack=10_000,
                           invested_this_hand=0, invested_this_round=0,
                           status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=opponent_seats,
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="fold", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def test_equity_hu_returns_equityresult_dict() -> None:
    """HU degenerate case: dict with single key matching the only villain."""
    v = _view(opponent_seats=(0,))
    result = hand_equity_vs_ranges(v, {0: "QQ+"}, seed=42)
    # Dict with EquityResult dump shape.
    assert set(result.keys()) >= {"hero_equity", "ci_low", "ci_high",
                                    "n_samples", "seed", "backend"}
    assert 0.0 <= result["hero_equity"] <= 1.0
    assert result["ci_low"] <= result["hero_equity"] <= result["ci_high"]
    # n_samples reflects ACTUAL valid samples (typically equals configured
    # 5000 since AsKs vs QQ+ has no card overlap; could be slightly less
    # in pathological setups). Assert == 5000 for this clean HU case.
    assert result["n_samples"] == 5000
    assert result["seed"] == 42
    assert result["backend"] == "eval7"


def test_equity_multi_way_returns_equityresult_dict() -> None:
    """3-way: hero + 2 villains."""
    v = _view(opponent_seats=(0, 4))
    result = hand_equity_vs_ranges(v, {0: "QQ+", 4: "AKs"}, seed=42)
    assert 0.0 <= result["hero_equity"] <= 1.0


def test_equity_missing_seat_raises() -> None:
    """spec §5.2.3: range_by_seat keys MUST equal opponent_seats_in_hand."""
    v = _view(opponent_seats=(0, 1, 4))
    with pytest.raises(ToolDispatchError, match="must equal"):
        hand_equity_vs_ranges(v, {0: "QQ+"}, seed=42)  # missing seats 1, 4


def test_equity_extra_seat_raises() -> None:
    v = _view(opponent_seats=(0,))
    with pytest.raises(ToolDispatchError, match="must equal"):
        # Extra seat 4 not in opponent_seats.
        hand_equity_vs_ranges(v, {0: "QQ+", 4: "AKs"}, seed=42)


def test_equity_combo_cap_500_per_range_raises() -> None:
    """Defense against absurdly broad ranges. spec doesn't mandate this cap;
    plan adds it as a safety rail."""
    v = _view(opponent_seats=(0,))
    # eval7 rejects "100%" syntactically, but very-broad valid ranges still
    # exist. Construct one near the cap. "22+" = all pairs = 78 combos.
    # "22+, AKs" = 82 combos. To cross 500 we need most of the deck. The
    # widest reasonable range "22+, A2s+, K2s+, Q2s+, J2s+, T2s+, 92s+, A2o+,
    # K2o+, Q2o+, J2o+" approaches 1000+. Test with one well over 500.
    huge_range = ("22+, A2s+, K2s+, Q2s+, J2s+, T2s+, 92s+, A2o+, "
                  "K2o+, Q2o+, J2o+, T2o+")
    with pytest.raises(ToolDispatchError, match="combo cap"):
        hand_equity_vs_ranges(v, {0: huge_range}, seed=42)


def test_equity_invalid_range_string_raises_with_eval7_message() -> None:
    """eval7 RangeStringError → ToolDispatchError; original message preserved
    so LLM can self-correct."""
    v = _view(opponent_seats=(0,))
    with pytest.raises(ToolDispatchError, match="parse"):
        hand_equity_vs_ranges(v, {0: "garbage notation here"}, seed=42)


def test_equity_weighted_range_rejected() -> None:
    """Codex audit IMPORTANT-1 fix: eval7 supports weighted syntax like
    '40%(KK)' which our MC silently mishandles (rng.choice ignores weights).
    Plan rejects non-1.0 weights at parse time."""
    v = _view(opponent_seats=(0,))
    with pytest.raises(ToolDispatchError, match="weighted"):
        hand_equity_vs_ranges(v, {0: "40%(KK), AA"}, seed=42)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_hand_equity_vs_ranges_tool.py -v 2>&1 | tail -10`
Expected: 6 tests fail with `NotImplementedError: Phase 3c-equity Task 4 implements hand_equity_vs_ranges wrapping`.

- [ ] **Step 3: Implement `hand_equity_vs_ranges`**

Edit `src/llm_poker_arena/tools/equity.py`. Replace the `hand_equity_vs_ranges` stub:

```python
import math

# Combo cap per villain range — defense against absurdly broad ranges
# (e.g., LLM passes "all reasonable hands" → MC samples become noise).
# spec doesn't mandate this; plan adds as safety rail. eval7 syntactically
# rejects "100%" but very broad valid ranges (~80-1000+ combos) can still
# happen. 500 is a generous-but-not-unbounded threshold.
_MAX_COMBOS_PER_RANGE = 500


def hand_equity_vs_ranges(
    view: "PlayerView",
    range_by_seat: dict[int, str],
    *,
    n_samples: int = 5000,
    seed: int | None = None,
) -> dict[str, Any]:
    """Compute hero equity vs villain ranges via multi-way Monte Carlo.

    spec §5.2.3 main API. Returns EquityResult.model_dump() — a dict ready
    for IterationRecord.tool_result.

    Validation (raises ToolDispatchError):
      - range_by_seat.keys() must equal view.opponent_seats_in_hand
      - each range string must parse via eval7.HandRange
      - each parsed range must have 0 < combos <= 500 (combo cap)

    Determinism: caller passes seed; defaults to view.turn_seed if None.
    """
    from llm_poker_arena.tools.equity_backend import Eval7Backend
    from llm_poker_arena.tools.runner import ToolDispatchError

    # 1. Strict key validation (spec §5.2.3).
    expected = set(view.opponent_seats_in_hand)
    provided = set(range_by_seat.keys())
    if provided != expected:
        missing = expected - provided
        extra = provided - expected
        raise ToolDispatchError(
            f"range_by_seat keys {sorted(provided)} must equal live opponent "
            f"seats {sorted(expected)}. Missing: {sorted(missing)}, "
            f"extra: {sorted(extra)}."
        )

    # 2. Parse ranges via eval7. Wrap RangeStringError as ToolDispatchError.
    villain_pools: list[tuple[Any, ...]] = []
    for seat, range_str in sorted(range_by_seat.items()):
        try:
            parsed = eval7.HandRange(range_str)
        except eval7.rangestring.RangeStringError as e:
            raise ToolDispatchError(
                f"failed to parse range for seat {seat}: {range_str!r} — "
                f"{e!s}. Use eval7 HandRange syntax (e.g. 'QQ+, AKs+, AKo')."
            ) from e
        # 3. Combo cap.
        n_combos = len(parsed.hands)
        if n_combos == 0:
            raise ToolDispatchError(
                f"range for seat {seat} parses to 0 combos: {range_str!r}"
            )
        if n_combos > _MAX_COMBOS_PER_RANGE:
            raise ToolDispatchError(
                f"range for seat {seat} parses to {n_combos} combos "
                f"(combo cap = {_MAX_COMBOS_PER_RANGE}); narrow the range."
            )
        # 3b. Codex audit IMPORTANT-1 fix: eval7 supports weighted syntax
        # like "40%(KK)" returning combos with non-1.0 weights. The MC
        # algorithm uses rng.choice() (uniform), which silently drops
        # weight info. For 3c-equity MVP, REJECT non-1.0 weights instead
        # of silently mishandling. system.j2 doesn't advertise weighted
        # syntax; if Claude tries it, error feedback teaches not to.
        for _combo, weight in parsed.hands:
            if weight != 1.0:
                raise ToolDispatchError(
                    f"range for seat {seat} contains weighted combo "
                    f"(weight={weight}); weighted ranges (e.g. '40%(KK)') "
                    f"are not supported in this version. Use unweighted "
                    f"syntax like 'QQ+, AKs'."
                )
        villain_pools.append(tuple(parsed.hands))

    # 4. Convert hero + community to eval7.Card.
    hero = tuple(eval7.Card(c) for c in view.my_hole_cards)
    board = tuple(eval7.Card(c) for c in view.community)

    # 5. Determine seed (spec §11.1: deterministic from view.turn_seed).
    effective_seed = seed if seed is not None else view.turn_seed

    # 6. Multi-way MC (rejection sampling — codex BLOCKER B1; multi-way
    # tie accounting — codex BLOCKER B2).
    backend = Eval7Backend()
    equity, share_variance, valid_samples = _multi_way_equity_mc(
        hero, board, villain_pools, backend,
        n_samples=n_samples, seed=effective_seed,
    )

    # 7. Edge case: max_attempts cap tripped without producing a single
    # valid sample (hero blocks the entire villain pool, etc). Surface as
    # ToolDispatchError so LLM gets actionable feedback.
    if valid_samples == 0:
        raise ToolDispatchError(
            "MC produced 0 valid samples — hero or board cards block "
            "every combo in at least one villain range. Adjust the range."
        )

    # 8. 95% CI from sample variance (multi-way correctness — codex NIT-1).
    # SE_of_mean = sqrt(sample_variance / n). For HU + no ties, this
    # reduces to sqrt(p(1-p)/n) — matches Bernoulli. For multi-way ties,
    # uses the actual fractional-share variance.
    se = math.sqrt(share_variance / valid_samples) if valid_samples > 0 else 0.0
    ci_half = 1.96 * se
    ci_low = max(0.0, equity - ci_half)
    ci_high = min(1.0, equity + ci_half)

    # 9. Build EquityResult (Pydantic validates equity ∈ [0, 1]).
    # With rejection sampling, valid_samples == n_samples (configured)
    # in non-pathological cases — n_samples field semantic preserved
    # (codex NIT-1 resolution: rejection-to-target).
    from llm_poker_arena.agents.llm.types import EquityResult
    return EquityResult(
        hero_equity=equity,
        ci_low=ci_low,
        ci_high=ci_high,
        n_samples=valid_samples,
        seed=effective_seed,
        backend="eval7",
    ).model_dump(mode="json")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_hand_equity_vs_ranges_tool.py -v 2>&1 | tail -10`
Expected: 6 tests pass.

- [ ] **Step 5: Sanity-run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 400 pass + 6 skip (393 after T0-3 + 7 hand_equity tests).

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/equity.py tests/unit/test_hand_equity_vs_ranges_tool.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/equity.py tests/unit/test_hand_equity_vs_ranges_tool.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/tools/equity.py tests/unit/test_hand_equity_vs_ranges_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): hand_equity_vs_ranges with strict validation (Phase 3c-equity Task 4)

spec §5.2.3 main API. Returns EquityResult.model_dump() — dict ready
for IterationRecord.tool_result.

Validation gates:
  - range_by_seat.keys() must equal view.opponent_seats_in_hand
    (spec §5.2.3 strict; missing/extra surfaces with clear message)
  - each range parses via eval7.HandRange; RangeStringError → ToolDispatchError
    with original message preserved for LLM self-correction
  - combo cap 500 per range (defense against very-broad-range abuse;
    eval7 rejects "100%" syntactically but other broad ranges can hit ~80-1000+)

Default n_samples=5000 (spec §5.2.3); seed defaults to view.turn_seed
for spec §11.1 reproducibility. LLM-callable kwarg surface (Q4 decision)
exposes ONLY range_by_seat — Task 6 input_schema reflects this.

95% CI computed via normal approximation p ± 1.96*sqrt(p(1-p)/n).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Wire `hand_equity_vs_ranges` into dispatcher

**Files:**
- Modify: `src/llm_poker_arena/tools/runner.py:_ALLOWED_ARGS` + `run_utility_tool` body
- Test: `tests/unit/test_run_utility_tool.py` (append dispatch test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_run_utility_tool.py`:

```python
def test_dispatch_hand_equity_vs_ranges() -> None:
    """run_utility_tool dispatches the new equity tool. Validates the dict
    flows through the normal dispatch path (extras-rejection, type-validation
    DON'T apply to dict-typed args — equity has its own validation in Task 4)."""
    v = _view()
    result = run_utility_tool(v, "hand_equity_vs_ranges",
                              {"range_by_seat": {0: "QQ+", 1: "AKs",
                                                  2: "JJ+", 4: "TT+",
                                                  5: "QQ+"}})
    assert "hero_equity" in result
    assert 0.0 <= result["hero_equity"] <= 1.0
    assert result["n_samples"] == 5000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_run_utility_tool.py::test_dispatch_hand_equity_vs_ranges -v`
Expected: FAIL — `ToolDispatchError: Unknown utility tool: hand_equity_vs_ranges`.

- [ ] **Step 3: Add equity dispatch branch**

Edit `src/llm_poker_arena/tools/runner.py`. Modify `_ALLOWED_ARGS`:

```python
_ALLOWED_ARGS: dict[str, frozenset[str]] = {
    "pot_odds": frozenset({"to_call", "pot"}),
    "spr": frozenset({"stack", "pot"}),
    "hand_equity_vs_ranges": frozenset({"range_by_seat"}),
}
```

Modify `run_utility_tool` to handle equity. Replace the dispatch tail:

```python
def run_utility_tool(
    view: PlayerView, name: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to the registered utility tool. Returns `{"value": float}` for
    pot_odds/spr; richer dicts (EquityResult.model_dump()) for equity tools.
    Raises `ToolDispatchError` on unknown tool name, extra args, or args
    type/value validation failure.

    Codex audit IMPORTANT-3 fix: extra args are REJECTED (not silently
    dropped). The tool spec input_schema declares `additionalProperties: False`
    — silently dropping would let the model rely on undefined behavior.

    NB: hand_equity_vs_ranges takes a dict-typed `range_by_seat` arg; the
    int-only validation below applies to pot_odds/spr (which take int args).
    Equity validates its own dict shape internally (Task 4).
    """
    from llm_poker_arena.tools.equity import hand_equity_vs_ranges
    from llm_poker_arena.tools.pot_odds import pot_odds
    from llm_poker_arena.tools.spr import spr

    if name not in _ALLOWED_ARGS:
        raise ToolDispatchError(f"Unknown utility tool: {name}")

    allowed = _ALLOWED_ARGS[name]
    extra = set(args) - allowed
    if extra:
        raise ToolDispatchError(
            f"{name} received unexpected args {sorted(extra)}; "
            f"allowed: {sorted(allowed)}"
        )

    if name == "pot_odds":
        for k, v in args.items():
            _validate_int_arg(f"{name}.{k}", v)
        return {"value": pot_odds(view, **args)}
    if name == "spr":
        for k, v in args.items():
            _validate_int_arg(f"{name}.{k}", v)
        return {"value": spr(view, **args)}
    # name == "hand_equity_vs_ranges"
    range_by_seat = args.get("range_by_seat")
    if not isinstance(range_by_seat, dict):
        raise ToolDispatchError(
            f"hand_equity_vs_ranges.range_by_seat must be a dict; "
            f"got {type(range_by_seat).__name__}"
        )
    # Coerce JSON-decoded string keys to int (Anthropic tool args may arrive
    # with string keys from JSON, but spec §5.2.3 expects seat: int).
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_run_utility_tool.py::test_dispatch_hand_equity_vs_ranges -v`
Expected: PASS.

- [ ] **Step 5: Sanity-run full dispatcher tests + suite**

Run: `.venv/bin/pytest tests/unit/test_run_utility_tool.py -v 2>&1 | tail -5`
Expected: prior 10 + 1 new = 11 pass.

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 401 pass + 6 skip.

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/runner.py tests/unit/test_run_utility_tool.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/runner.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/tools/runner.py tests/unit/test_run_utility_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): dispatcher routes hand_equity_vs_ranges (Phase 3c-equity Task 5)

run_utility_tool now handles "hand_equity_vs_ranges". The dict-typed
range_by_seat arg is incompatible with pot_odds/spr's int-validation
(_validate_int_arg) — equity branch does its own type-shape coercion
(string keys → int seats from JSON-decoded args; values must be str
ranges). Equity-internal validation (key set, range parse, combo cap)
lives in equity.hand_equity_vs_ranges (Task 4).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add `hand_equity_vs_ranges` to `utility_tool_specs`

**Files:**
- Modify: `src/llm_poker_arena/tools/runner.py:utility_tool_specs`
- Test: `tests/unit/test_utility_tool_specs.py` (append assertion)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_utility_tool_specs.py`:

```python
def test_specs_includes_hand_equity_vs_ranges_when_enabled() -> None:
    """Phase 3c-equity adds hand_equity_vs_ranges to utility_tool_specs."""
    v = _view(enable_math_tools=True)
    specs = utility_tool_specs(v)
    names = {s["name"] for s in specs}
    assert "hand_equity_vs_ranges" in names
    equity_spec = next(s for s in specs if s["name"] == "hand_equity_vs_ranges")
    schema = equity_spec["input_schema"]
    assert schema["type"] == "object"
    # spec §5.2.3 + Q4 minimal API: only range_by_seat is exposed.
    assert "range_by_seat" in schema["properties"]
    assert schema["required"] == ["range_by_seat"]
    # range_by_seat is a dict mapping seat (additionalProperties string).
    rbs = schema["properties"]["range_by_seat"]
    assert rbs["type"] == "object"
    assert rbs["additionalProperties"]["type"] == "string"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_utility_tool_specs.py::test_specs_includes_hand_equity_vs_ranges_when_enabled -v`
Expected: FAIL — `assert 'hand_equity_vs_ranges' in {'pot_odds', 'spr'}`.

- [ ] **Step 3: Add equity to utility_tool_specs**

Edit `src/llm_poker_arena/tools/runner.py:utility_tool_specs`. Append after the spr spec:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_utility_tool_specs.py -v 2>&1 | tail -5`
Expected: 4 prior + 1 new = 5 pass.

- [ ] **Step 5: Sanity-run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 402 pass + 6 skip.

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/runner.py tests/unit/test_utility_tool_specs.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/runner.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/tools/runner.py tests/unit/test_utility_tool_specs.py
git commit -m "$(cat <<'EOF'
feat(tools): utility_tool_specs advertises hand_equity_vs_ranges (Phase 3c-equity Task 6)

Anthropic tool spec exposes ONLY range_by_seat (Q4 minimal API decision):
n_samples and seed_override are server-side defaults, not LLM-tunable.
additionalProperties=false on the input_schema so extras get rejected
upstream by the dispatcher (codex IMPORTANT-3 from 3c-math).

Description tells LLM when equity adds value over pot_odds — multi-way
3-bet calls, draw shove vs call, equity vs polarized ranges.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update `system.j2` to mention `hand_equity_vs_ranges`

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/prompts/system.j2`
- Test: `tests/unit/test_llm_agent_react_loop.py` (append render assertion)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_llm_agent_react_loop.py`:

```python
def test_system_prompt_mentions_hand_equity_vs_ranges_when_enabled() -> None:
    """Phase 3c-equity: system.j2 lists hand_equity_vs_ranges in the
    UTILITY TOOLS block when enable_math_tools=True."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    captured_systems: list[str | None] = []

    class Capturing(MockLLMProvider):
        async def complete(self, **kw: Any) -> LLMResponse:
            captured_systems.append(kw.get("system"))
            return await super().complete(**kw)

    script = MockResponseScript(responses=(
        _resp(ToolCall(name="fold", args={}, tool_use_id="t1")),
    ))
    provider = Capturing(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    params_with_math = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )
    view_with_math = PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
        seats_public=_seats(), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=legal, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params_with_math,
    )
    asyncio.run(agent.decide(view_with_math))
    sys_text = captured_systems[0]
    assert sys_text is not None
    assert "hand_equity_vs_ranges" in sys_text
    # Check it tells LLM about the eval7 syntax briefly.
    assert "QQ+" in sys_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py::test_system_prompt_mentions_hand_equity_vs_ranges_when_enabled -v`
Expected: FAIL — `assert 'hand_equity_vs_ranges' in <system prompt without it>`.

- [ ] **Step 3: Update `system.j2`**

Edit `src/llm_poker_arena/agents/llm/prompts/system.j2`. Inside the `{% if enable_math_tools %}` block, after the `spr(stack?, pot?)` line:

```jinja
- hand_equity_vs_ranges(range_by_seat) — estimate your win probability vs villain ranges via Monte Carlo. Pass a dict mapping each opponent seat number (must match opponent_seats_in_hand exactly) to an eval7-compatible range string. Examples of range syntax: 'QQ+' (queens or better pairs), 'AKs+' (just AKs since A is top), 'JJ-77' (pairs from 77 to JJ inclusive), 'AdKd' (specific suited combo), 'QQ+, AKs, AKo' (comma-separated union). Returns {"hero_equity": float, "ci_low": float, "ci_high": float, "n_samples": int, ...}.
```

And update the WHEN TO USE section:

```jinja
WHEN TO USE TOOLS
- Use pot_odds when comparing different bet sizes (the current pot_odds_required only covers calling; tools cover hypothetical raise/shove sizing).
- Use spr to plan post-flop commitment when considering a preflop raise that would change your effective_stack vs pot ratio.
- Use hand_equity_vs_ranges when your decision turns on equity vs a specific villain range — typical scenarios: facing a 3-bet, deciding between call and shove on a draw, or evaluating a multi-way pot. Skip when villain ranges are too uncertain to estimate (Random opponents have no informative range).
- Skip tools entirely when your decision is obvious (premium hand vs strong fold equity, blatant fold vs marginal scenario).
- After at most {{ max_utility_calls }} utility tool calls per turn, you must commit an action.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v 2>&1 | tail -5`
Expected: prior + 1 new = passes.

- [ ] **Step 5: Sanity-run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 403 pass + 6 skip.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check tests/unit/test_llm_agent_react_loop.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/prompts/system.j2 tests/unit/test_llm_agent_react_loop.py
git commit -m "$(cat <<'EOF'
feat(prompt): system.j2 advertises hand_equity_vs_ranges (Phase 3c-equity Task 7)

UTILITY TOOLS block now lists hand_equity_vs_ranges with brief eval7
range syntax examples (QQ+, AKs+, JJ-77, AdKd, comma-union). WHEN TO
USE block adds guidance: equity tool valuable for facing 3-bets, draw
shove/call decisions, multi-way evaluation. Explicitly tells LLM to
skip equity vs Random opponents (no informative range).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Mock K+1 integration test calling equity

**Files:**
- Modify: `tests/unit/test_llm_agent_react_loop_k1.py` (append)
- Modify: `tests/integration/test_llm_session_mock_k1.py` (extend)

- [ ] **Step 1: Write the failing test (unit-level K+1 with equity)**

Append to `tests/unit/test_llm_agent_react_loop_k1.py`:

```python
def test_k1_equity_call_then_action() -> None:
    """LLM calls hand_equity_vs_ranges, then commits. IterationRecord
    chain has 2 entries: equity iteration with tool_result containing
    hero_equity field; action iteration with tool_result=None."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    # Single villain (HU) so the call is simple.
    view = _view(legal)  # opponent_seats=(0,1,2,4,5) by default

    # Use one villain only — simpler test setup. Override opponent_seats.
    from llm_poker_arena.engine.views import (
        ActionToolSpec as _ATS,  # noqa
    )
    # Build a HU-ish view: opponent_seats=(0,) only
    params = _params(max_utility_calls=5)
    hu_view = PlayerView(
        my_seat=3, my_hole_cards=("As", "Ks"), community=(),
        pot=250, sidepots=(), my_stack=9_750,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=100/350, effective_stack=9_750,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                           position_full="x", stack=10_000,
                           invested_this_hand=0, invested_this_round=0,
                           status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0,),
        action_order_this_street=(3, 0),
        seats_yet_to_act_after_me=(0,),
        already_acted_this_street=(), hand_history=(),
        legal_actions=legal, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params,
    )

    script = MockResponseScript(responses=(
        _resp(ToolCall(
            name="hand_equity_vs_ranges",
            args={"range_by_seat": {0: "QQ+, AKs"}},
            tool_use_id="tu_eq",
        )),
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu_fold")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(hu_view))
    assert result.final_action == Action(tool_name="fold", args={})
    assert len(result.iterations) == 2
    eq_iter, action_iter = result.iterations
    assert eq_iter.tool_call is not None
    assert eq_iter.tool_call.name == "hand_equity_vs_ranges"
    assert eq_iter.tool_result is not None
    assert "hero_equity" in eq_iter.tool_result
    assert 0.0 <= eq_iter.tool_result["hero_equity"] <= 1.0
    assert action_iter.tool_result is None
    assert result.tool_usage_error_count == 0
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop_k1.py::test_k1_equity_call_then_action -v`
Expected: PASS (all wiring from Tasks 0-7 in place).

- [ ] **Step 3: Extend integration mock K+1 test to verify equity flows through Session**

Append to `tests/integration/test_llm_session_mock_k1.py`:

```python
def test_session_with_equity_tool_call_writes_full_result_to_snapshot(
    tmp_path: Path,
) -> None:
    """End-to-end: mock LLM calls hand_equity_vs_ranges; the EquityResult
    dict (hero_equity + CI + n_samples + seed + backend) lands in
    agent_view_snapshots.jsonl iterations[i].tool_result.

    Uses a HU-style mock script to keep the equity dict minimal."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True, enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )

    # Mock script alternating equity → fold. Codex audit IMPORTANT-2 fix:
    # provide range_by_seat covering ALL 5 villains. Seat 3 is UTG (button=0,
    # SB=1, BB=2, UTG=3, HJ=4, CO=5) — UTG is FIRST to act preflop, so on
    # every hand's preflop turn 1 the live opponent_seats_in_hand is exactly
    # {0,1,2,4,5} (all opponents still in). Mock equity dict matches → call
    # succeeds → ≥1 success guaranteed per hand. After UTG folds in turn 2,
    # seat 3 is out for that hand; next hand restarts.
    def _equity_call(uid: str) -> LLMResponse:
        return LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(ToolCall(
                name="hand_equity_vs_ranges",
                args={"range_by_seat": {0: "22+", 1: "22+", 2: "22+",
                                         4: "22+", 5: "22+"}},
                tool_use_id=uid,
            ),),
            text_content="checking equity",
            tokens=TokenCounts(input_tokens=10, output_tokens=5,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        )

    def _fold(uid: str) -> LLMResponse:
        return LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
            text_content="folding",
            tokens=TokenCounts(input_tokens=10, output_tokens=5,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        )

    # Cycle: equity → fold → equity → fold ...
    responses = []
    for i in range(150):
        responses.append(_equity_call(f"eq_{i}"))
        responses.append(_fold(f"f_{i}"))
    script = MockResponseScript(responses=tuple(responses))
    provider = MockLLMProvider(script=script)
    llm_agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    agents = [
        RandomAgent(),  # 0
        RandomAgent(),  # 1
        RandomAgent(),  # 2
        llm_agent,      # 3
        RandomAgent(),  # 4
        RandomAgent(),  # 5
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="mock_k1_equity")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps

    # Codex audit IMPORTANT-2 fix: assert at least one SUCCESSFUL equity
    # iteration with full EquityResult shape. Mock now provides all 5 villain
    # ranges (preflop UTG always has 5 live opponents), so seat 3's first
    # turn each hand is a guaranteed match. ≥1 success across 6 hands.
    success_eq_iters = []
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc and tc["name"] == "hand_equity_vs_ranges":
                tr = it.get("tool_result")
                if tr and "hero_equity" in tr:
                    success_eq_iters.append(it)
    assert success_eq_iters, (
        "no successful equity iterations — mock provides all 5 villains as "
        "{0,1,2,4,5} which is the guaranteed preflop UTG live opponent set "
        "for seat 3. If 0 successes, MC dispatch is broken OR opponent "
        "topology unexpected."
    )
    # Each successful equity iteration carries the full EquityResult shape.
    sample = success_eq_iters[0]["tool_result"]
    assert "ci_low" in sample
    assert "ci_high" in sample
    assert "n_samples" in sample
    assert "seed" in sample
    assert sample["backend"] == "eval7"
```

**Note**: the integration test acknowledges that mock equity calls will frequently fail (key mismatch with live opponent_seats) and asserts only that AT LEAST one succeeds. This is a realistic test of the wire — the alternative (always-aligned mock) would require dynamic mock response generation which is complex. Let the failure case be exercised by `tool_usage_error_count`.

- [ ] **Step 4: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_llm_session_mock_k1.py -v 2>&1 | tail -8`
Expected: 2 prior tests pass + 1 new test passes.

If new test fails with `assert success_eq_iters` empty (after codex IMPORTANT-2 fix), preflop UTG opponent_seats unexpectedly differs from {0,1,2,4,5} — investigate engine seat-rotation logic.

- [ ] **Step 5: Sanity-run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 405 pass + 6 skip.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check tests/unit/test_llm_agent_react_loop_k1.py tests/integration/test_llm_session_mock_k1.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_llm_agent_react_loop_k1.py tests/integration/test_llm_session_mock_k1.py
git commit -m "$(cat <<'EOF'
test(integration): K+1 calls hand_equity_vs_ranges + result lands in snapshots (Phase 3c-equity Task 8)

Two new tests:
- Unit: K+1 ReAct mock script with equity → fold; assert IterationRecord
  chain has equity iteration with hero_equity in tool_result, action
  iteration with tool_result=None. Validates dispatcher → equity → MC
  → IterationRecord wire.

- Integration: 6-hand mock session cycling equity → fold. Codex audit
  IMPORTANT-2 fix: mock now provides ALL 5 villain ranges
  ({0,1,2,4,5}: "22+") so seat 3's UTG preflop turn (always 5 live
  opponents) is a guaranteed key match. Asserts ≥1 SUCCESSFUL equity
  iteration with full EquityResult shape (hero_equity, ci_low, ci_high,
  n_samples, seed, backend=eval7).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Gated real-Anthropic K+1 multi-LLM smoke test

**Files:**
- Create: `tests/integration/test_llm_session_real_anthropic_math_equity.py`

**Activation:**
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_anthropic_math_equity.py -v
```

Cost: ~$0.04-0.08 per run (2 Claude Haiku seats × 6 hands × K+1 with equity overhead).

**Why 2 LLM seats**: Phase 3c-math gated test was 1 LLM + 5 Random. Claude organic 0/6 calls. With 2 LLM seats, the equity tool actually has informative villain ranges to estimate against (the other LLM is structurally rational, not random). Whether Claude realizes this is research data; test doesn't enforce.

- [ ] **Step 1: Create the gated test**

Create `tests/integration/test_llm_session_real_anthropic_math_equity.py`:

```python
"""Real Anthropic K+1 with equity tool, multi-LLM (gated, NOT in CI).

Run only when:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Costs ~$0.04-0.08 per run with Claude Haiku 4.5 × 2 seats, 6 hands,
math tools (pot_odds + spr + hand_equity_vs_ranges) enabled.

Assertions are wire-correctness only (mirrors 3c-math gated test
following codex audit IMPORTANT-5):
  - Session runs to completion without crash
  - All seat-1 and seat-3 final_actions are in the legal set
  - meta.json provider_capabilities populated for both LLM seats
  - chip_pnl conserves
  - IF utility iterations appear (any of pot_odds/spr/equity), their
    tool_result has the expected shape

Frequency / behavior assertions belong in DuckDB analysis post-session.
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


def test_real_claude_haiku_two_llm_seats_with_equity_tool(tmp_path: Path) -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider_a = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    provider_b = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm_a = LLMAgent(provider=provider_a, model="claude-haiku-4-5",
                     temperature=0.7, total_turn_timeout_sec=60.0)
    llm_b = LLMAgent(provider=provider_b, model="claude-haiku-4-5",
                     temperature=0.7, total_turn_timeout_sec=60.0)
    agents = [
        RandomAgent(),  # seat 0 (BTN)
        llm_a,          # SB ← Claude
        RandomAgent(),  # BB
        llm_b,          # UTG ← Claude
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_anthropic_math_equity_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_seats = {1, 3}
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] in llm_seats]
    assert llm_snaps, "no LLM seat snapshots"

    # 1. Every final_action must be in the legal set (or default_safe_action).
    for rec in llm_snaps:
        final = rec["final_action"]
        legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
        assert final["type"] in legal_names, (
            f"seat {rec['seat']} final action {final!r} not in legal set {legal_names}"
        )

    # 2. IF any utility iteration appears (pot_odds, spr, OR equity),
    #    validate its shape.
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc and tc["name"] in ("pot_odds", "spr", "hand_equity_vs_ranges"):
                assert it["tool_result"] is not None, (
                    f"utility iteration without tool_result — dispatch broken "
                    f"({tc['name']})"
                )
                # Each tool has its own result shape; verify minimally.
                if tc["name"] in ("pot_odds", "spr"):
                    assert "value" in it["tool_result"] or "error" in it["tool_result"]
                elif tc["name"] == "hand_equity_vs_ranges":
                    tr = it["tool_result"]
                    if "error" not in tr:
                        assert "hero_equity" in tr
                        assert tr["backend"] == "eval7"

    # 3. chip_pnl conservation (no censor / fallback regression on infra).
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

    # 4. Provider capabilities populated for BOTH LLM seats (3b regression).
    caps = meta["provider_capabilities"]
    assert "1" in caps and caps["1"]["provider"] == "anthropic"
    assert "3" in caps and caps["3"]["provider"] == "anthropic"
```

- [ ] **Step 2: Verify gate-skipped run still works**

Run: `.venv/bin/pytest tests/ -q --no-header -x 2>&1 | tail -3`
Expected: 405 pass + 7 skip (the new gated joins the existing 6).

- [ ] **Step 3: Live verify against real Anthropic API**

Run:
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_anthropic_math_equity.py -v --basetemp=/tmp/anthropic_equity_smoke 2>&1 | tail -10
```

Expected: PASS in 90-300s (2 LLMs make ~2× API calls vs 3c-math gated test). Cost ~$0.04-0.08.

After PASS, inspect `/tmp/anthropic_equity_smoke/.../agent_view_snapshots.jsonl` to count organic equity calls. This is the research data we want — if 0 calls happen even with 2 LLMs, prompt or scenario design needs revisit (Phase 3e research question).

- [ ] **Step 4: Lint**

Run: `.venv/bin/ruff check tests/integration/test_llm_session_real_anthropic_math_equity.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_llm_session_real_anthropic_math_equity.py
git commit -m "$(cat <<'EOF'
test(integration): gated real-Anthropic K+1 multi-LLM with equity (Phase 3c-equity Task 9)

Mirrors 3c-math gated pattern but uses 2 LLM seats (vs 1 LLM + 5 Random
in 3c-math). With 2 Claude seats, the equity tool theoretically has
informative villain ranges to estimate against (the other LLM is
structurally rational, not random). Whether Claude organically uses the
tool is research data — gated test asserts wire correctness only:
  - no crash, legal final_actions for both LLM seats
  - meta.json.provider_capabilities populated for seats 1 and 3
  - chip_pnl conserves
  - IF utility iters appear, their tool_result has expected shape per tool
    (value for pot_odds/spr; hero_equity+ci+backend for equity)

Cost ~$0.04-0.08 / run. Verified manually pre-commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Lint sweep + memory update

**Files:**
- Touch any source file flagged by final ruff/mypy
- Update `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`

- [ ] **Step 1: Final ruff check on all changed files**

Run: `.venv/bin/ruff check src/ tests/`
Expected: clean. Fix any drift inline.

- [ ] **Step 2: Final mypy strict on all changed files**

Run: `.venv/bin/mypy --strict src/ tests/`
Expected: clean. Fix any drift inline. Common issues:
- eval7 lacks type stubs → already handled in Task 1 via mypy override
- Module-level `import eval7` in equity.py is needed at runtime; if mypy strict complains about untyped import, the override should cover it

- [ ] **Step 3: Final test run with all gates flipped**

Run:
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 DEEPSEEK_INTEGRATION_TEST=1 \
  .venv/bin/pytest tests/ 2>&1 | tail -10
```

Expected: 412 pass + 0 skip (405 non-gated + 7 gated: 1 new equity smoke + 6 from prior phases).

- [ ] **Step 4: Update memory**

Read `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`. Insert a new "Phase 3c-equity COMPLETE" block at the top of the status section (replaces or sits above current "Phase 3c-math COMPLETE" pointer):

```markdown
**Status as of 2026-04-25 (latest)**: **Phase 3c-equity COMPLETE** at HEAD `<sha>`. 408 tests pass with all gates on (401 unit/non-gated + 7 gated: 2 Anthropic K=0/probe + 1 K+1 math + 1 K+1 math equity multi-LLM + 2 DeepSeek + 1 multi-provider); 401 + 7 skip in default CI mode. ruff + mypy --strict clean.
```

(See Task 10 plan section for full memory entry template.)

- [ ] **Step 5: Final inventory**

Run: `git log --oneline 79025af^..HEAD && git status`

(Where `79025af` is the Phase 3c-math plan baseline commit. Replace with the Phase 3c-equity plan baseline SHA after Task 0 commits.)

Expected: clean tree. Phase 3c-equity adds 11 commits (1 plan baseline + 10 task commits). Memory file is outside the repo.

---

## Self-Review Checklist (auditor-facing summary)

After all 10 tasks land, the following statements must hold:

1. **Spec coverage:**
   - §5.2.2 EquityBackend ABC + Eval7Backend impl shipped (with Card-type coupling deviation documented) ✓
   - §5.2.3 hand_equity_vs_ranges main API with strict key validation ✓
   - §5.2.3 default n_samples=5000 honored ✓
   - §5.2.3 deterministic seed from view.turn_seed ✓
   - §5.3 utility_tool_specs gated on enable_math_tools (already from 3c-math) ✓
   - §5.4 dispatch via run_utility_tool (already from 3c-math) ✓
   - §6 system prompt includes equity tool description ✓
   - §7.4 EquityResult dump persisted in IterationRecord.tool_result ✓
   - §11.1 deterministic equity result for same (view, range_by_seat, seed) ✓
2. **Brainstorming decisions honored:**
   - eval7 backend ✓
   - multi-way only API, no HU alias ✓
   - trust eval7 raw HandRange parser ✓
   - minimal LLM API: only range_by_seat ✓
3. **Type consistency:**
   - `EquityResult` Pydantic name same in types.py and equity.py
   - `_multi_way_equity_mc` name same in equity.py and tests
   - `EquityBackend.evaluate(cards: tuple[eval7.Card, ...]) -> int` signature consistent
4. **No placeholders:** every step has executable code or commands.
5. **Cross-task integration:** Task 4 depends on Task 2 (multi-way MC) + Task 3 (EquityResult). Task 5 depends on Task 4. Task 6 depends on Task 5. Task 8 depends on Tasks 5+6+7. Task 9 depends on all of 0-8.
6. **Codex audit findings to expect** (pre-fill for codex prompt round): equity-specific risks the audit might catch — combo cap threshold (500) might be too high or too low; HU degenerate path matches eval7 native MC within how many SE; the integration test "≥1 success" assertion may flake; tool_usage_error_count behavior on equity dispatch errors (should fire just like pot_odds bad args); JSON args coercion (string-keys-to-int) may have edge cases.
